"""Async ccxt exchange for the BitShares DEX, served by bitshares-ccxt-bridge.

Why this file exists
--------------------
OctoBot never touches synchronous ccxt for REST. octobot_trading resolves an
exchange with:

    ccxt_client_util.ccxt_exchange_class_factory(name)
        -> getattr(ccxt.async_support, name)

(octobot_trading/exchanges/connectors/ccxt/ccxt_client_util.py). Every call it
then makes is awaited. The original octobot_shim subclasses the *synchronous*
ccxt.Exchange and registers itself on the plain `ccxt` module, so OctoBot's
lookup raises AttributeError before anything else can happen — the exchange is
invisible no matter how the tentacles are configured.

This class is the async counterpart. Once registered on ccxt.async_support,
OctoBot resolves it, finds no dedicated tentacle, and falls back to
DefaultRestExchange, which drives it through the generic ccxt connector.
"""

import os

import ccxt.async_support as ccxt_async
from .graphene import GrapheneClient

from ccxt.base.errors import (
    ArgumentsRequired,
    BadRequest,
    AuthenticationError,
    ExchangeError,
    InsufficientFunds,
    InvalidOrder,
    NotSupported,
    OrderNotFound,
)

DEFAULT_BRIDGE_URL = "http://localhost:8787"


def bridge_url() -> str:
    return os.environ.get("BITSHARES_CCXT_BRIDGE_URL", DEFAULT_BRIDGE_URL).rstrip("/")


class bitshares_dex(ccxt_async.Exchange):
    """The class name, describe()['id'] and the ccxt.async_support attribute
    must all be the identical string. OctoBot looks the exchange up by name in
    three separate places and a mismatch fails silently in at least one of
    them."""

    def describe(self):
        base = bridge_url()
        return self.deep_extend(
            super().describe(),
            {
                "id": "bitshares_dex",
                "name": "BitShares DEX",
                "countries": [],
                "rateLimit": 250,
                "version": "1",
                "certified": False,
                "pro": False,
                "urls": {
                    # Display only, but octobot_trading.get_exchange_details
                    # indexes urls['logo'], ['www'] and ['api'] directly and
                    # raises KeyError if any is missing.
                    "logo": "https://ex.xbts.io/favicon.ico",
                    "www": "https://bitshares.org",
                    "doc": ["https://github.com/Jeff-Bouchard/bitshares-ccxt-bridge"],
                    "api": {"public": base, "private": base},
                },
                "has": {
                    "CORS": False,
                    "spot": True,
                    "margin": False,
                    "swap": False,
                    "future": False,
                    "option": False,
                    "fetchMarkets": True,
                    "fetchCurrencies": True,
                    "fetchTicker": True,
                    "fetchTickers": True,
                    "fetchOrderBook": True,
                    "fetchTrades": True,
                    "fetchOHLCV": True,
                    "fetchBalance": True,
                    "fetchTradingFees": True,
                    "createOrder": True,
                    "cancelOrder": True,
                    "fetchOrder": True,
                    "fetchOpenOrders": True,
                    "fetchMyTrades": True,
                    # Explicit False: OctoBot probes these and a missing key
                    # reads as "maybe".
                    "createMarketOrder": False,
                    "fetchClosedOrders": False,
                    "fetchOrders": False,
                    "fetchDepositAddress": False,
                    "fetchLedger": False,
                    "fetchPositions": False,
                    "withdraw": False,
                },
                # Real resolutions, served by the chain rather than by XBTS.
                # get_market_history_buckets() on a live node returns exactly
                # these seven bucket sizes; nothing else is available.
                "timeframes": {
                    "1m": 60,
                    "5m": 300,
                    "15m": 900,
                    "1h": 3600,
                    "4h": 14400,
                    "1d": 86400,
                    "1w": 604800,
                },
                # The bridge holds the BitShares key. There is no per-client
                # credential, and ccxt would otherwise raise before every
                # private call.
                "requiredCredentials": {
                    "apiKey": False,
                    "secret": False,
                    "uid": False,
                    "login": False,
                    "password": False,
                    "twofa": False,
                    "privateKey": False,
                    "walletAddress": False,
                    "token": False,
                },
                "options": {
                    "account": os.environ.get("BTS_ACCOUNT"),
                    # OHLCV straight from a Graphene node. Turning this off
                    # puts you back on XBTS, which only ever returns 1d.
                    "useGraphene": True,
                    # Read everything from the chain. The Node bridge is only
                    # needed to sign orders, so market data, and therefore
                    # simulator mode, needs nothing installed but this package.
                    "useBridge": bool(os.environ.get("BITSHARES_CCXT_BRIDGE_URL")),
                    # ccxt symbol -> on-chain asset. XBTSX.* are the XBTS
                    # gateway's wrapped assets; BTS is the native one.
                    "assets": {
                        "BTS": "BTS",
                        "NESS": "XBTSX.NESS",
                        "NCH": "XBTSX.NCH",
                        "USDT": "XBTSX.USDT",
                        "BTC": "XBTSX.BTC",
                        "ETH": "XBTSX.ETH",
                    },
                    "symbols": [
                        "NESS/BTS",
                        "NCH/BTS",
                        "BTS/USDT",
                        "NESS/USDT",
                        "NCH/USDT",
                        "BTS/BTC",
                    ],
                    "grapheneNodes": [
                        node.strip()
                        for node in os.environ.get("BITSHARES_GRAPHENE_NODES", "").split(",")
                        if node.strip()
                    ]
                    or None,
                    # 'auto' | 'direct' | 'inverted' — see _detect_orientation.
                    "priceOrientation": "auto",
                    "confirmOrderPriceOrientation": False,
                },
            },
        )

    # ------------------------------------------------------------ transport --

    def sign(self, path, api="public", method="GET", params={}, headers=None, body=None):
        url = self.urls["api"][api] + "/" + self.implode_params(path, params)
        query = self.omit(params, self.extract_params(path))
        headers = dict(headers or {})
        if method in ("GET", "DELETE"):
            if query:
                url += "?" + self.urlencode(query)
        else:
            body = self.json(query)
            headers["Content-Type"] = "application/json"
        token = os.environ.get("BRIDGE_TOKEN", "").strip()
        if token:
            headers["Authorization"] = "Bearer " + token
        return {"url": url, "method": method, "headers": headers or None, "body": body}

    def handle_errors(self, code, reason, url, method, headers, body, response, request_headers, request_body):
        if response is None or not isinstance(response, dict):
            return
        error = self.safe_string(response, "error")
        if error is None:
            return
        feedback = self.id + " " + str(error)
        lowered = error.lower()
        # "No account configured" is what the bridge returns in view-only mode.
        # It has to surface as AuthenticationError, not ExchangeError, or
        # fetch_balance never reaches its public-balance fallback.
        if (
            "view-only" in lowered
            or "login" in lowered
            or "unauthor" in lowered
            or "no account" in lowered
            or "not logged" in lowered
        ):
            raise AuthenticationError(feedback)
        if "insufficient" in lowered:
            raise InsufficientFunds(feedback)
        if "not found" in lowered or "unknown order" in lowered:
            raise OrderNotFound(feedback)
        if "required" in lowered or "invalid" in lowered:
            raise InvalidOrder(feedback)
        raise ExchangeError(feedback)

    async def call(self, path, api="public", method="GET", params={}):
        return await self.fetch2(path, api, method, params)

    # -------------------------------------------------------------- public ---

    def _asset(self, code):
        return self.safe_string(self.safe_value(self.options, "assets", {}), code, code)

    async def _graphene_markets(self):
        client = self._graphene()
        symbols = self.safe_value(self.options, "symbols", [])
        wanted = []
        for symbol in symbols:
            base, _, quote = symbol.partition("/")
            wanted.append(self._asset(base))
            wanted.append(self._asset(quote))
        resolved = await client.assets(sorted(set(wanted)))

        result = []
        for symbol in symbols:
            base, _, quote = symbol.partition("/")
            base_asset, quote_asset = self._asset(base), self._asset(quote)
            if base_asset not in resolved or quote_asset not in resolved:
                continue
            base_id, base_precision = resolved[base_asset]
            quote_id, quote_precision = resolved[quote_asset]
            result.append(
                self.safe_market_structure(
                    {
                        "id": base_asset + "_" + quote_asset,
                        "symbol": symbol,
                        "base": base,
                        "quote": quote,
                        "baseId": base_id,
                        "quoteId": quote_id,
                        "active": True,
                        "type": "spot",
                        "spot": True,
                        "margin": False,
                        "swap": False,
                        "future": False,
                        "option": False,
                        "contract": False,
                        "taker": 0.001,
                        "maker": 0.001,
                        "precision": {"amount": base_precision, "price": quote_precision},
                        "limits": {
                            "amount": {"min": None, "max": None},
                            "price": {"min": None, "max": None},
                            "cost": {"min": None, "max": None},
                            "leverage": {"min": None, "max": None},
                        },
                        "info": {
                            "baseAsset": base_asset,
                            "quoteAsset": quote_asset,
                            "basePrecision": base_precision,
                            "quotePrecision": quote_precision,
                        },
                    }
                )
            )
        return result

    async def fetch_markets(self, params={}):
        if not self.safe_bool(self.options, "useBridge", False):
            return await self._graphene_markets()
        raw = await self.call("markets", "public", "GET", params)
        result = []
        for market in raw:
            symbol = self.safe_string(market, "symbol")
            if symbol is None:
                continue
            result.append(
                self.safe_market_structure(
                    {
                        "id": self.safe_string(market, "id"),
                        "symbol": symbol,
                        "base": self.safe_string(market, "base"),
                        "quote": self.safe_string(market, "quote"),
                        "baseId": self.safe_string(market, "baseId"),
                        "quoteId": self.safe_string(market, "quoteId"),
                        "active": self.safe_bool(market, "active", True),
                        "type": "spot",
                        "spot": True,
                        "margin": False,
                        "swap": False,
                        "future": False,
                        "option": False,
                        "contract": False,
                        "taker": self.safe_number(market, "taker", 0.001),
                        "maker": self.safe_number(market, "maker", 0.001),
                        "precision": {
                            "amount": self.safe_integer(market.get("precision", {}), "amount", 8),
                            "price": self.safe_integer(market.get("precision", {}), "price", 8),
                        },
                        "limits": {
                            "amount": {"min": None, "max": None},
                            "price": {"min": None, "max": None},
                            "cost": {"min": None, "max": None},
                            "leverage": {"min": None, "max": None},
                        },
                        "info": self.safe_value(market, "info", market),
                    }
                )
            )
        return result

    async def fetch_currencies(self, params={}):
        if not self.safe_bool(self.options, "useBridge", False):
            return None
        try:
            return await self.call("currencies", "public", "GET", params)
        except ExchangeError:
            return None

    def parse_ticker(self, ticker, market=None):
        symbol = self.safe_string(ticker, "symbol")
        timestamp = self.safe_integer(ticker, "timestamp")
        return self.safe_ticker(
            {
                "symbol": self.safe_symbol(None, market) if symbol is None else symbol,
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "bid": self.safe_number(ticker, "bid"),
                "ask": self.safe_number(ticker, "ask"),
                "last": self.safe_number(ticker, "last"),
                "close": self.safe_number(ticker, "last"),
                "baseVolume": self.safe_number(ticker, "baseVolume"),
                "quoteVolume": self.safe_number(ticker, "quoteVolume"),
                "percentage": self.safe_number(ticker, "percentage"),
                "info": self.safe_value(ticker, "info", ticker),
            },
            market,
        )

    def _detect_orientation(self, raw):
        """Decide whether the bridge quotes price as quote-per-base or its
        reciprocal, using the bridge's own volume fields as the referee.

        For a ccxt symbol BASE/QUOTE, price must be quote per base, and
        quoteVolume / baseVolume is a volume-weighted price in exactly those
        units. Measured on BTS/USDT:

            quoteVolume / baseVolume = 0.00157663
            1 / last                 = 0.00157207
            last                     = 636.10

        The reported price is the reciprocal of the exchange's own volume
        ratio, and matches the chain's own buckets once flipped. Rather than
        hardcode that, this compares both readings and picks the closer one.
        """
        configured = self.safe_string(self.options, "priceOrientation", "auto")
        if configured in ("direct", "inverted"):
            return configured
        last = self.safe_number(raw, "last")
        base_volume = self.safe_number(raw, "baseVolume")
        quote_volume = self.safe_number(raw, "quoteVolume")
        if not last or not base_volume or not quote_volume:
            return "direct"
        implied = quote_volume / base_volume
        direct_error = abs(last / implied - 1)
        inverted_error = abs((1 / last) / implied - 1)
        return "inverted" if inverted_error < direct_error else "direct"

    async def fetch_ticker(self, symbol, params={}):
        await self.load_markets()
        market = self.market(symbol)
        if not self.safe_bool(self.options, "useBridge", False):
            info = self.safe_value(market, "info", {})
            raw = await self._graphene().ticker(
                self.safe_string(info, "baseAsset", market["base"]),
                self.safe_string(info, "quoteAsset", market["quote"]),
            )
            # Already quote-per-base: get_ticker was called with the quote
            # asset first. Nothing to flip.
            return self.parse_ticker(
                {
                    "symbol": market["symbol"],
                    "timestamp": self.parse8601(self.safe_string(raw, "time") + "Z"),
                    "last": self.safe_number(raw, "latest"),
                    "bid": self.safe_number(raw, "highest_bid"),
                    "ask": self.safe_number(raw, "lowest_ask"),
                    "baseVolume": self.safe_number(raw, "quote_volume"),
                    "quoteVolume": self.safe_number(raw, "base_volume"),
                    "percentage": self.safe_number(raw, "percent_change"),
                    "info": raw,
                },
                market,
            )
        raw = await self.call("ticker", "public", "GET", self.extend({"symbol": market["symbol"]}, params))
        orientation = self._detect_orientation(raw)
        self.options["detectedPriceOrientation"] = orientation
        if orientation == "inverted":
            raw = dict(raw)
            for field in ("last", "bid", "ask"):
                value = self.safe_number(raw, field)
                raw[field] = (1 / value) if value else value
            # Inverting reverses the book: the best price to sell at becomes
            # the best price to buy at.
            raw["bid"], raw["ask"] = raw.get("ask"), raw.get("bid")
        return self.parse_ticker(raw, market)

    async def fetch_tickers(self, symbols=None, params={}):
        await self.load_markets()
        symbols = self.symbols if symbols is None else symbols
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = await self.fetch_ticker(symbol, params)
            except ExchangeError:
                continue
        return result

    async def fetch_order_book(self, symbol, limit=None, params={}):
        await self.load_markets()
        market = self.market(symbol)
        if not self.safe_bool(self.options, "useBridge", False):
            info = self.safe_value(market, "info", {})
            raw = await self._graphene().order_book(
                self.safe_string(info, "baseAsset", market["base"]),
                self.safe_string(info, "quoteAsset", market["quote"]),
                limit or 25,
            )
            book = {"bids": [], "asks": [], "timestamp": None}
            for side in ("bids", "asks"):
                for entry in self.safe_value(raw, side, []) or []:
                    price = self.safe_number(entry, "price")
                    # entry["quote"] is the amount in the ccxt base currency;
                    # entry["base"] is what it costs in the quote currency.
                    amount = self.safe_number(entry, "quote")
                    if price is not None and amount is not None:
                        book[side].append([price, amount])
            book["bids"].sort(key=lambda row: row[0], reverse=True)
            book["asks"].sort(key=lambda row: row[0])
            return self.parse_order_book(book, market["symbol"], None, "bids", "asks")
        request = {"symbol": market["symbol"]}
        if limit is not None:
            request["limit"] = limit
        raw = await self.call("orderbook", "public", "GET", self.extend(request, params))
        timestamp = self.safe_integer(raw, "timestamp")
        return self.parse_order_book(raw, market["symbol"], timestamp, "bids", "asks")

    async def fetch_trades(self, symbol, since=None, limit=None, params={}):
        await self.load_markets()
        market = self.market(symbol)
        if not self.safe_bool(self.options, "useBridge", False):
            base_asset, quote_asset = self._graphene_symbols(market)
            raw = await self._graphene().trades(base_asset, quote_asset, limit or 50, since)
            trades = []
            for entry in raw or []:
                timestamp = self.parse8601(self.safe_string(entry, "date") + "Z")
                trades.append(self.safe_trade({
                    "id": self.safe_string(entry, "sequence"),
                    "order": None,
                    "timestamp": timestamp,
                    "datetime": self.iso8601(timestamp),
                    "symbol": market["symbol"],
                    "type": "limit",
                    "side": self.safe_string(entry, "type"),
                    "takerOrMaker": None,
                    "price": self.safe_string(entry, "price"),
                    "amount": self.safe_string(entry, "amount"),
                    "cost": self.safe_string(entry, "value"),
                    "fee": None,
                    "info": entry,
                }, market))
            trades.sort(key=lambda row: row["timestamp"] or 0)
            return trades
        request = {"symbol": market["symbol"]}
        if limit is not None:
            request["limit"] = limit
        raw = await self.call("trades", "public", "GET", self.extend(request, params))
        return self.parse_trades(raw, market, since, limit)

    # ------------------------------------------------------- graphene ---

    def _require_bridge(self, what):
        if not self.safe_bool(self.options, "useBridge", False):
            raise NotSupported(
                "%s: %s needs the signing bridge. Start bitshares-ccxt-bridge and set "
                "BITSHARES_CCXT_BRIDGE_URL, or run OctoBot in trader-simulator mode, "
                "which never calls it." % (self.id, what)
            )

    def _graphene(self):
        client = self.safe_value(self.options, "_grapheneClient")
        if client is None:
            client = GrapheneClient(self.safe_value(self.options, "grapheneNodes"))
            self.options["_grapheneClient"] = client
        return client

    def _graphene_symbols(self, market):
        """Recover the real Graphene asset names for a market.

        The bridge reports BTS/USDT, but on-chain the quote asset is
        XBTSX.USDT. XBTS's own market URL carries both, in quote_base order:
        .../market/XBTSX.USDT_BTS
        """
        info = self.safe_value(market, "info", {})
        base_asset = self.safe_string(info, "baseAsset")
        quote_asset = self.safe_string(info, "quoteAsset")
        if base_asset and quote_asset:
            return base_asset, quote_asset
        url = self.safe_string(info, "url", "")
        tail = url.rsplit("/", 1)[-1]
        if "_" in tail:
            quote_asset, base_asset = tail.split("_", 1)
            return base_asset, quote_asset
        return self._asset(market["base"]), self._asset(market["quote"])

    async def fetch_ohlcv(self, symbol, timeframe="1h", since=None, limit=None, params={}):
        await self.load_markets()
        market = self.market(symbol)
        seconds = self.safe_integer(self.timeframes, timeframe)
        if seconds is None:
            raise BadRequest(
                "%s does not support %s — the chain only buckets %s"
                % (self.id, timeframe, ", ".join(self.timeframes.keys()))
            )
        if self.safe_bool(self.options, "useGraphene", True):
            base_asset, quote_asset = self._graphene_symbols(market)
            return await self._graphene().ohlcv(base_asset, quote_asset, seconds, since, limit)

        # XBTS path. It ignores `timeframe` entirely and answers with daily
        # candles, so anything below 1d would be silently wrong resolution.
        if timeframe != "1d":
            raise NotSupported(
                "%s: useGraphene is off and the XBTS backend only returns daily candles; "
                "%s would be daily data mislabelled" % (self.id, timeframe)
            )
        raw = await self.call("ohlcv", "public", "GET", self.extend({"symbol": market["symbol"]}, params))
        candles = []
        for row in raw:
            if isinstance(row, list) and len(row) >= 6:
                candles.append([int(row[0])] + [float(v) for v in row[1:6]])
        if since is not None:
            candles = [c for c in candles if c[0] >= since]
        if limit is not None:
            candles = candles[-int(limit):]
        return candles

    async def fetch_trading_fees(self, params={}):
        if not self.safe_bool(self.options, "useBridge", False):
            # BitShares market fees are per-asset on chain; 0.1% is the common
            # XBTS default and is what the simulator should assume.
            return {
                symbol: {"info": {}, "symbol": symbol, "maker": 0.001, "taker": 0.001}
                for symbol in self.symbols
            }
        return await self.call("tradingFees", "public", "GET", params)

    # ------------------------------------------------------------- private ---

    def parse_balance(self, response):
        result = {"info": response}
        entries = response
        if isinstance(response, dict):
            entries = self.safe_value(response, "balances", response)
        if isinstance(entries, dict):
            entries = [
                {"currency": code, "free": value, "total": value}
                for code, value in entries.items()
                if not isinstance(value, (dict, list))
            ]
        for entry in entries or []:
            code = self.safe_string_2(entry, "currency", "asset")
            if code is None:
                continue
            free = self.safe_string_2(entry, "free", "available")
            total = self.safe_string_2(entry, "total", "balance")
            account = self.account()
            account["free"] = free if free is not None else total
            account["total"] = total if total is not None else free
            account["used"] = self.safe_string(entry, "used")
            result[self.safe_currency_code(code)] = account
        return self.safe_balance(result)

    async def fetch_balance(self, params={}):
        self._require_bridge("fetch_balance")
        try:
            raw = await self.call("balance", "private", "GET", params)
        except AuthenticationError:
            account = self.safe_string(params, "account") or self.safe_string(self.options, "account")
            if not account:
                raise ArgumentsRequired(
                    self.id
                    + " fetch_balance needs the bridge logged in, or params['account'] / BTS_ACCOUNT for the public balance"
                )
            raw = await self.call("balancePublic", "public", "GET", {"account": account})
        return self.parse_balance(raw)

    async def fetch_open_orders(self, symbol=None, since=None, limit=None, params={}):
        await self.load_markets()
        request = {}
        if symbol is not None:
            request["symbol"] = self.market(symbol)["symbol"]
        if since is not None:
            request["since"] = since
        if limit is not None:
            request["limit"] = limit
        raw = await self.call("openOrders", "private", "GET", self.extend(request, params))
        market = self.market(symbol) if symbol is not None else None
        return self.parse_orders(raw, market, since, limit)

    async def fetch_order(self, id, symbol=None, params={}):
        raw = await self.call("order/" + str(id), "private", "GET", params)
        return self.parse_order(raw)

    async def fetch_my_trades(self, symbol=None, since=None, limit=None, params={}):
        await self.load_markets()
        request = {}
        if symbol is not None:
            request["symbol"] = self.market(symbol)["symbol"]
        raw = await self.call("myTrades", "private", "GET", self.extend(request, params))
        market = self.market(symbol) if symbol is not None else None
        return self.parse_trades(raw, market, since, limit)

    async def create_order(self, symbol, type, side, amount, price=None, params={}):
        self._require_bridge("create_order")
        if type != "limit":
            raise NotSupported(self.id + " only supports limit orders — the DEX has no market order primitive")
        if price is None:
            raise ArgumentsRequired(self.id + " create_order requires a price for limit orders")
        await self.load_markets()
        market = self.market(symbol)
        if (
            self.safe_string(self.options, "detectedPriceOrientation") == "inverted"
            and not self.safe_bool(self.options, "confirmOrderPriceOrientation", False)
        ):
            raise NotSupported(
                self.id
                + " refuses to place an order: the bridge reports prices as the reciprocal of the ccxt "
                + "BASE/QUOTE convention, so it is unknown which way round it expects an order price. "
                + "Fix the bridge, or set options['confirmOrderPriceOrientation'] = True once you have "
                + "checked by hand which orientation /order takes."
            )
        body = {
            "symbol": market["symbol"],
            "type": type,
            "side": side,
            "amount": float(amount),
            "price": float(price),
            "params": self.omit(params, []),
        }
        raw = await self.call("order", "private", "POST", body)
        return self.parse_order(raw, market)

    async def cancel_order(self, id, symbol=None, params={}):
        self._require_bridge("cancel_order")
        raw = await self.call("order", "private", "DELETE", self.extend({"id": str(id)}, params))
        return self.parse_order(raw)

    async def sign_in(self, params={}):
        account = self.safe_string(params, "account") or self.safe_string(self.options, "account")
        secret = self.safe_string(params, "keyOrPassword")
        if not account or not secret:
            raise ArgumentsRequired(self.id + " sign_in requires params['account'] and params['keyOrPassword']")
        return await self.call(
            "login",
            "private",
            "POST",
            {
                "account": account,
                "keyOrPassword": secret,
                "isPassword": self.safe_bool(params, "isPassword", False),
                "node": self.safe_string(params, "node"),
            },
        )

    # -------------------------------------------------------------- parsers --

    def parse_order(self, order, market=None):
        if not isinstance(order, dict):
            return self.safe_order({"info": order}, market)
        timestamp = self.safe_integer(order, "timestamp")
        return self.safe_order(
            {
                "id": self.safe_string_2(order, "id", "orderId"),
                "clientOrderId": self.safe_string(order, "clientOrderId"),
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "symbol": self.safe_string(order, "symbol"),
                "type": self.safe_string(order, "type", "limit"),
                "side": self.safe_string(order, "side"),
                "price": self.safe_string(order, "price"),
                "amount": self.safe_string(order, "amount"),
                "filled": self.safe_string(order, "filled"),
                "remaining": self.safe_string(order, "remaining"),
                "status": self.safe_string(order, "status"),
                "info": order,
            },
            market,
        )

    def parse_trade(self, trade, market=None):
        timestamp = self.safe_integer(trade, "timestamp")
        return self.safe_trade(
            {
                "id": self.safe_string(trade, "id"),
                "order": self.safe_string(trade, "order"),
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "symbol": self.safe_string(trade, "symbol", market["symbol"] if market else None),
                "side": self.safe_string(trade, "side"),
                "price": self.safe_string(trade, "price"),
                "amount": self.safe_string(trade, "amount"),
                "cost": self.safe_string(trade, "cost"),
                "info": trade,
            },
            market,
        )
