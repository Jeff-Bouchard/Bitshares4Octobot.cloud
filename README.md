# BitShares DEX for OctoBot — technical notes
# Jeff Bouchard for Privateness.network xbtsx.ness and .nch nov 2026
Plain-language version for users: **WHAT-YOU-GET.md**.

## Install

```
./wizard.sh
```

Bash only, run through Git Bash on Windows. No PowerShell, no `.bat`, no jq.
ASCII source with LF endings, because a non-ASCII byte in a script is decoded
by the terminal code page and that is how the previous version died.

It finds OctoBot by asking the OS for the process list and reading the path a
running OctoBot was started from, then this folder, then `$HOME/OctoBot`, then
you. No filesystem sweep. If nothing is found it offers to install OctoBot:
`python -m venv` plus `pip install OctoBot` when a Python 3.12+ is present,
otherwise the standalone binary from the OctoBot-Binary releases.

### How the tentacle is installed, and why it matters

Through OctoBot's own installer:
`OctoBot tentacles --install --all --location bitshares_dex_tentacle.zip`.
That zip ships prebuilt in this package, because Git Bash has no `zip` command
to make one with.

The installer path is not cosmetic. Copying the folder in by hand and adding
the import to the generated index gets the plug-in **loaded but not switched
on**: OctoBot keeps a per-profile activation map in
`user/profiles/*/tentacles_config.json`, and a class missing from it is
treated as inactive. Measured on a clean install with no prior history:

```
BitsharesDex activated = False   ->  resolves to ConfigurableDefaultCCXTRestExchange
BitsharesDex activated = True    ->  resolves to BitsharesDex
```

The hand-copy path is kept as a fallback for when no OctoBot program can be
found, and it now writes that activation flag itself when Python is available,
and says plainly that it could not when Python is absent.

### Shortcuts

After a successful install the wizard writes `start-octobot.sh` into the
OctoBot folder and registers it with the desktop:

| Platform | Where | How it is made |
|---|---|---|
| Windows | Start Menu / BitShares OctoBot | a `.lnk` targeting `bash.exe -lc "<launcher>"`, plus a plain-text `.url` for the dashboard |
| macOS | `~/Applications/BitShares OctoBot.command` | copy of the launcher |
| Linux | `~/.local/share/applications` | `.desktop` entry |

The `.lnk` is written by `tools_mklnk.py`, a stdlib implementation of
MS-SHLLINK (the published Shell Link Binary File Format): header, a LinkInfo
with a local base path, and the string section. No COM, no WScript, no
PowerShell. If Python is not available the `.url` is still written, it just
cannot start OctoBot on its own.

### What was tested, and where

Tested on bash 5.2 on Linux against real OctoBot 2.1.1 and live BitShares
nodes. Four separate runs:

**Fresh install from nothing** - the wizard created `/root/OctoBot` itself
(venv, `pip install OctoBot`, standard tentacles), with no OctoBot present
beforehand.

**Clean room** - tentacle folder deleted, index entry stripped, and all 19
`BitsharesDex` activation entries cleared, then:

```
Installed with OctoBot's own plug-in installer.
[ok]   OctoBot loads it and uses the BitShares exchange class.
[ok]   Profile arbitrage_trading now uses: binance, bitshares_dex, coinbase, kucoin
[ok]   OctoBot is up.
[ok]   BitShares is on the configuration screen. Checked, not assumed.
[ok]   Applications menu: "BitShares OctoBot"
```

**Process detection** - no `--octobot` argument, OctoBot already running:
`Found it from the running process.`

**Shortcuts** - the Linux path end to end: `.desktop` entry written, launcher
written, OctoBot killed, then the launcher run exactly as the shortcut runs
it. It started OctoBot from cold and reported `OctoBot is running at
http://127.0.0.1:5001`.

The `.lnk` was generated with the exact arguments the Windows branch passes,
then read back with LnkParse3, an independent third-party parser, which
recovered the target, arguments, working directory, name and `DRIVE_FIXED`
correctly. That is evidence the bytes conform to the format. It is **not**
evidence that Windows Explorer opens it, which cannot be tested here.

**Not tested:** Windows Explorer actually opening the generated `.lnk`; Git
Bash on Windows specifically; the packaged `OctoBot_windows_x64.exe`, either
as an install target or as a download; and the standalone-binary download
path, because GitHub release downloads are blocked from the machine this was
built on. The asset names used (`OctoBot_windows_x64.exe`, `OctoBot_linux_x64`,
`OctoBot_linux_arm64`, `OctoBot_osx`) come from reading the OctoBot-Binary
repository, not from a download that succeeded here.

### The diagnostic menu (any platform)

```
./setup.sh
```

Fourteen checks, each fixing itself where it can. `o` installs OctoBot from
scratch, `f` points at an existing one, `p` sets its interpreter, `b` sets up
the signing bridge, `n` installs Node, `a` fixes everything marked `*`.

Scriptable equivalent:

```
python install.py --octobot "C:\OctoBot"
python install.py --octobot "C:\OctoBot" --install-octobot \
                  --bridge "C:\src\bitshares-ccxt-bridge" \
                  --account octobot-trading --wif 5xxxx \
                  --profile arbitrage_trading
```

Requires **Python 3.12 or newer**. OctoBot 2.1.1 declares
`requires_python >=3.12`; the installation docs still say 3.10, which was true
of OctoBot 2.0. There is no compilation step: OctoBot and its OctoBot-\*
dependencies install as pure Python despite shipping as source distributions.

## Why a tentacle rather than a site-packages hook

OctoBot resolves an exchange in two places, both of which run after tentacles
are loaded:

```python
# octobot_trading/exchanges/connectors/ccxt/ccxt_client_util.py
getattr(async_ccxt, exchange_name)          # the ccxt class

# octobot_trading/exchanges/util/exchange_util.py
get_rest_exchange_class(name, tentacles_setup_config, ...)   # the OctoBot class
```

`load_tentacles()` does `import tentacles`, which cascades through the
generated `tentacles/Trading/Exchange/__init__.py` into each tentacle package.
So `bitshares_dex/__init__.py` is the right place to attach the ccxt class to
`ccxt.async_support` and `ccxt.exchanges`, and the tentacle's own
`BitsharesDex(RestExchange)` is what makes OctoBot pick a named implementation
rather than its generic fallback.

The practical consequence is that nothing outside the OctoBot folder is
touched — no site-packages write, no `.pth`, no edit to an OctoBot file.

Installation goes through OctoBot's own installer
(`tentacles --install --location <zip>`) with the package laid out as
`reference_tentacles/Trading/Exchange/bitshares_dex/`, so OctoBot regenerates
its tentacle index itself.

## Verified

Against OctoBot 2.1.1 on Python 3.13 with the official tentacles installed, and
against live BitShares nodes:

```
BitShares tentacle    version 1.0.0, in the tentacle index
OctoBot uses it       OctoBot uses BitsharesDex
Chain reachable       api.bts.mobi, candle sizes [60,300,900,3600,14400,86400,604800]
NESS / NCH assets     XBTSX.NESS 1.3.6041   XBTSX.NCH 1.3.6181
Live prices           NESS/BTS bid 0.18559 ask 0.224589960980422929  spread 21%
Exchange end to end   6 markets, NESS/BTS last 0.185000000185 BTS, 7 candle sizes
Trading profile       enabled in: arbitrage_trading
```

And in a real OctoBot run:

```
Starting OctoBot with simulated trader on bitshares_dex[spot], kucoin[spot]
  trading NESS/BTS, NCH/BTS, BTC/USDT, BTS/USDT with ArbitrageTradingMode
CCXTConnector[bitshares_dex] Loaded 6 [bitshares_dex] markets
ArbitrageModeProducer Starting on listening for NESS/BTS arbitrage opportunities
```

Zero errors from the exchange across that run. Running the official
`tentacles --install --all` afterwards leaves the tentacle installed and still
listed in the regenerated index.

Not tested: a remote machine being refused by the bridge's loopback bind (the
container used here has only a loopback interface), and anything on Android.

## Data path

Everything readable comes from the chain over HTTPS JSON-RPC — public
BitShares nodes accept the API addressed by name, so there is no websocket
handshake and no session:

| call | chain method |
|---|---|
| `fetch_markets` | `lookup_asset_symbols` |
| `fetch_ticker` | `get_ticker` |
| `fetch_order_book` | `get_order_book` |
| `fetch_trades` | `get_trade_history` |
| `fetch_ohlcv` | `get_market_history` |

Orders and balances are the only calls that need the signing bridge, and they
raise `NotSupported` with an explanation when it is not configured.

**Orientation.** `get_ticker(A, B)`, `get_order_book(A, B)` and
`get_trade_history(A, B)` all price in **A per one B** — first argument per one
of the second. ccxt's `NESS/BTS` means the opposite, BTS per NESS, so the quote
asset is passed first throughout. Getting this backwards is a factor of several
hundred on these markets. `get_trade_history` additionally takes its time range
as `(stop, start)`, newest boundary first.

Nodes are tried in order until one answers: api.bts.mobi, node.xbts.io,
api.dex.trading, public.xbts.io.

## Configuration

`options` on the exchange, overridable from OctoBot's exchange settings:

```
assets   NESS -> XBTSX.NESS, NCH -> XBTSX.NCH, USDT -> XBTSX.USDT,
         BTC -> XBTSX.BTC, ETH -> XBTSX.ETH, BTS -> BTS
symbols  NESS/BTS, NCH/BTS, BTS/USDT, NESS/USDT, NCH/USDT, BTS/BTC
```

Environment, read by the exchange itself so no key passes through OctoBot's
config files:

```
BITSHARES_CCXT_BRIDGE_URL   http://127.0.0.1:8787   (enables order placing)
BRIDGE_TOKEN                the bridge password
BITSHARES_GRAPHENE_NODES    comma-separated, overrides the node list
```

## Files

```
setup.py / setup.sh               the diagnostic menu (needs Python)
tools_mklnk.py                    writes the Windows .lnk (MS-SHLLINK)
bitshares_dex_tentacle.zip        the prebuilt plug-in package
install.py                        the steps, usable on its own
tentacle/reference_tentacles/Trading/Exchange/bitshares_dex/
    __init__.py                   ccxt registration + exports BitsharesDex
    bitshares_dex_exchange.py     the OctoBot RestExchange subclass
    ccxt_bitshares_dex.py         the async ccxt exchange
    graphene.py                   BitShares JSON-RPC client (aiohttp)
    metadata.json                 tentacle version and name
```
