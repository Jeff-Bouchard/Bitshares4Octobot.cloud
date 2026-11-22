"""Minimal async Graphene (BitShares) websocket client.

Exists for one reason: the bridge's OHLCV comes from XBTS, which ignores the
requested timeframe and always answers with daily candles. The chain itself
does not have that limitation. A live node reports:

    get_market_history_buckets() -> [60, 300, 900, 3600, 14400, 86400, 604800]

so 1m / 5m / 15m / 1h / 4h / 1d / 1w are all available on-chain.

aiohttp only — it is already a hard dependency of ccxt.async_support, so this
adds nothing to the install.

Call convention
---------------
Graphene's JSON-RPC takes params as [api_id, method, args_array]. API ids are
obtained from the login API, which is always id 1:

    [1, "database", []] -> database api id
    [1, "history",  []] -> history api id

Passing the three elements in any other order, or args as anything other than
an array, fails with:

    Assert Exception: args.size() == 3 && args[2].is_array()
"""

import asyncio
import time

import aiohttp

DEFAULT_NODES = [
    "wss://api.bts.mobi",
    "wss://node.xbts.io/ws",
    "wss://api.dex.trading",
    "wss://btsws.roelandp.nl/ws",
    "wss://public.xbts.io/ws",
    "wss://dex.iobanker.com/ws",
]


class GrapheneError(Exception):
    pass


class GrapheneClient:
    """One short-lived websocket per batch of calls, with node failover."""

    def __init__(self, nodes=None, timeout=10):
        self.nodes = list(nodes) if nodes else list(DEFAULT_NODES)
        self.timeout = timeout
        self._asset_cache = {}
        self._buckets = None
        self._lock = asyncio.Lock()

    async def _call(self, ws, api_id, method, args):
        await ws.send_json({"method": "call", "params": [api_id, method, args], "jsonrpc": "2.0", "id": 1})
        msg = await ws.receive_json(timeout=self.timeout)
        if "error" in msg:
            raise GrapheneError(str(msg["error"])[:300])
        return msg.get("result")

    async def _with_node(self, fn):
        last = None
        for node in self.nodes:
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout + 5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(node, timeout=self.timeout) as ws:
                        database = await self._call(ws, 1, "database", [])
                        history = await self._call(ws, 1, "history", [])
                        return await fn(ws, database, history)
            except Exception as err:  # node down, 503, handshake refused
                last = err
                continue
        raise GrapheneError("no Graphene node answered: %r" % (last,))

    async def buckets(self):
        if self._buckets is not None:
            return self._buckets

        async def run(ws, _database, history):
            return await self._call(ws, history, "get_market_history_buckets", [])

        self._buckets = await self._with_node(run)
        return self._buckets

    async def assets(self, symbols):
        """Resolve Graphene symbols to (id, precision). Cached per process."""
        missing = [s for s in symbols if s not in self._asset_cache]
        if missing:

            async def run(ws, database, _history):
                return await self._call(ws, database, "lookup_asset_symbols", [missing])

            for symbol, asset in zip(missing, await self._with_node(run)):
                if asset:
                    self._asset_cache[symbol] = (asset["id"], int(asset["precision"]))
        return {s: self._asset_cache[s] for s in symbols if s in self._asset_cache}

    async def ticker(self, base_symbol, quote_symbol):
        """get_ticker(A, B) prices in A per one B, so the ccxt BASE/QUOTE
        orientation is obtained by passing the quote asset first."""

        async def run(ws, database, _history):
            return await self._call(ws, database, "get_ticker", [quote_symbol, base_symbol])

        return await self._with_node(run)

    async def order_book(self, base_symbol, quote_symbol, limit=25):
        """Same orientation rule as ticker. Entry['quote'] is the amount in the
        ccxt base currency, entry['base'] the amount in the quote currency."""

        async def run(ws, database, _history):
            return await self._call(ws, database, "get_order_book", [quote_symbol, base_symbol, int(limit)])

        return await self._with_node(run)

    async def trades(self, base_symbol, quote_symbol, limit=50, since_ms=None):
        """Recent market trades, priced quote per base like everything else.

        get_trade_history takes (stop, start) in that order — the newest
        boundary first — which is the reverse of what the name suggests.
        Its `amount` is in the second asset passed and `value` in the first,
        so with the quote asset passed first the amount is already in the ccxt
        base currency and the value is the cost in the quote currency.
        """
        stop = time.time()
        start = (since_ms / 1000.0) if since_ms else (stop - 30 * 86400)
        fmt = "%Y-%m-%dT%H:%M:%S"

        async def run(ws, database, _history):
            return await self._call(
                ws, database, "get_trade_history",
                [quote_symbol, base_symbol,
                 time.strftime(fmt, time.gmtime(stop)),
                 time.strftime(fmt, time.gmtime(start)),
                 int(limit or 50)],
            )

        return await self._with_node(run)

    async def ohlcv(self, base_symbol, quote_symbol, bucket_seconds, since_ms=None, limit=None):
        """Return ccxt-shaped [[ms, o, h, l, c, v], …] priced as quote per base.

        Graphene orders a market's key by asset id, not by the caller's idea of
        base and quote, so the returned amounts have to be re-oriented against
        what was asked for. Amounts are integers scaled by asset precision.
        """
        resolved = await self.assets([base_symbol, quote_symbol])
        if base_symbol not in resolved or quote_symbol not in resolved:
            raise GrapheneError("unknown asset: %s or %s" % (base_symbol, quote_symbol))
        base_id, base_precision = resolved[base_symbol]
        quote_id, quote_precision = resolved[quote_symbol]

        span = bucket_seconds * (int(limit) if limit else 500)
        start = (since_ms / 1000.0) if since_ms else (time.time() - span)
        stop = time.time()
        fmt = "%Y-%m-%dT%H:%M:%S"
        start_str = time.strftime(fmt, time.gmtime(start))
        stop_str = time.strftime(fmt, time.gmtime(stop))

        async def run(ws, _database, history):
            return await self._call(
                ws,
                history,
                "get_market_history",
                [base_id, quote_id, int(bucket_seconds), start_str, stop_str],
            )

        raw = await self._with_node(run)
        candles = []
        for bucket in raw or []:
            key = bucket.get("key", {})
            # The chain put the lower asset id in key["base"]; that may or may
            # not be the base the caller asked for.
            flipped = key.get("base") != base_id
            scale_a, scale_b = (quote_precision, base_precision) if flipped else (base_precision, quote_precision)

            def price(side):
                amount_a = int(bucket[side + "_base"]) / (10 ** scale_a)
                amount_b = int(bucket[side + "_quote"]) / (10 ** scale_b)
                if amount_a == 0 or amount_b == 0:
                    return None
                return (amount_a / amount_b) if flipped else (amount_b / amount_a)

            values = {side: price(side) for side in ("open", "high", "low", "close")}
            if any(v is None for v in values.values()):
                continue
            high, low = values["high"], values["low"]
            if flipped:  # inverting a price swaps which extreme is which
                high, low = low, high

            volume_field = "quote_volume" if flipped else "base_volume"
            volume = int(bucket.get(volume_field, 0)) / (10 ** base_precision)

            opened = time.strptime(key["open"], "%Y-%m-%dT%H:%M:%S")
            candles.append(
                [
                    int(time.mktime(opened) - time.timezone) * 1000,
                    values["open"],
                    high,
                    low,
                    values["close"],
                    volume,
                ]
            )
        candles.sort(key=lambda c: c[0])
        if limit:
            candles = candles[-int(limit):]
        return candles
