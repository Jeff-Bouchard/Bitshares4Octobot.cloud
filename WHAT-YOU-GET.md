# What this is, in plain language

This adds the **BitShares DEX** — a decentralised exchange that runs on the
BitShares blockchain — to **OctoBot**, the open-source trading bot. After
installing, BitShares appears in OctoBot next to KuCoin, Binance and the rest,
and you can trade XBTSX.NESS, XBTSX.NCH and BTS from the same bot, with the
same strategies, at the same time as your other exchanges.

There is no company behind this exchange. It is a blockchain. Nobody holds your
coins, nobody asks for your identity, and nobody can freeze you out of it.

## How to install it

Open **Git Bash** in this folder (right-click the folder, "Git Bash Here") and
run:

```
./wizard.sh
```

On Mac or Linux it is the same line in any terminal. One bash script, nothing
Windows-only, nothing to install first except Git for Windows if you do not
already have it: https://git-scm.com/download/win

### How it finds OctoBot

In this order, and nothing else:

1. a folder you pass with `--octobot`
2. an OctoBot that is **running right now** - it asks the operating system for
   the process list and reads the path the program was started from
3. this folder, and the one above it
4. `$HOME/OctoBot`
5. it asks you
6. it offers to download and install OctoBot for you

It does **not** go rummaging through your home folder, Desktop, Downloads or
Documents. An earlier version did, and that was wrong.

If OctoBot is answering but the wizard cannot work out where it lives, it
stops and asks. It will not install a second copy on top of a working one.

### Starting it afterwards

The wizard adds a shortcut, so you do not have to remember any of this:

- **Windows:** Start Menu, under **BitShares OctoBot**. Two entries - one
  starts OctoBot, one opens the dashboard if it is already running.
- **Mac:** `~/Applications/BitShares OctoBot.command`
- **Linux:** your applications menu, **BitShares OctoBot**

All of them run the same `start-octobot.sh` the wizard leaves in your OctoBot
folder: it starts OctoBot if it is not running, waits for it, and opens the
screen in your browser.

### Where to look afterwards

1. Open **http://localhost:5001** in your browser - that is OctoBot's screen.
2. Go to **Profile**, the configuration page.
3. Scroll the exchange cards. One of them is titled **BitShares**.

If OctoBot was already running while you installed, close it and start it
again. Plug-ins are read at startup.

---

## Where it gets installed

Entirely inside **your own OctoBot folder**, as a *tentacle* — that is
OctoBot's own word for a plug-in, and OctoBot ships about seventy of them
already. Ours sits beside them:

```
YourOctoBot/
  tentacles/
    Trading/
      Exchange/
        kucoin/              <- shipped with OctoBot
        binance/             <- shipped with OctoBot
        bitshares_dex/       <- this
```

That means:

- **Nothing is installed system-wide.** Your Python installation is untouched.
- **No OctoBot file is edited by hand.** It is installed by OctoBot's own
  plug-in installer, the same one that installs the official exchanges.
- **It survives OctoBot updates.** Running `tentacles --install --all` to
  refresh the official plug-ins leaves this one in place — tested.
- **Uninstalling is deleting a folder.** Nothing else is left behind.

If you run several OctoBots, each one has its own copy and its own settings.

---

## What you get without giving up anything

Install it and do nothing else, and OctoBot can already see the BitShares
market: prices, order books, candles and recent trades, for

```
NESS/BTS    NCH/BTS    BTS/USDT    NESS/USDT    NCH/USDT    BTS/BTC
```

All of it is read **straight from a BitShares node over ordinary HTTPS**. No
account. No API key. No private key anywhere on your computer. Nothing
listening on a network port. You can run OctoBot's paper-trading mode against
real live market data and watch what a strategy *would* have done, risking
nothing at all.

That is the sensible place to start, and for a lot of people it is where to
stay for a few weeks.

## What you need to actually place orders

Blockchain orders have to be signed with your private key, and that is the one
part that cannot be done by just reading. For real trading you also run a
small local program — the **signing bridge** — that holds the key and signs
orders for OctoBot. The installer can fetch, build and lock it down for you.

Two things it does, which matter:

- It listens on **127.0.0.1 only**, so it is reachable from your own computer
  and from nowhere else — not your home network, not a VPN you join.
- It requires a **password** on every request, generated during install. Other
  programs on your machine cannot simply ask it to trade.

Use a **second BitShares account** holding only what the bot trades with, and
keep your main holdings in an account whose key never touches that computer.
BitShares cannot restrict a key to "orders only", so the thing that limits your
losses is the balance sitting behind the key. Choose that number deliberately.

---

## Where BTS actually trades, and what that means

This matters before you plan an arbitrage run.

**Binance delisted BTS on 7 December 2023.** The announcement was "cease
trading on all trading pairs"; BTS/USDT went with it. There is no Binance leg
to arbitrage against any more.

Volumes as reported by CoinLore at the time of writing:

| Venue | Pair | 24h volume |
|---|---|---|
| MEXC | BTS/USDT | about $59,500 |
| Gate | BTS/USDT | about $4,600 |
| **BitShares DEX** | **BTS/XBTSX.USDT** | **about $15** |
| XBTS | BTS/CNY | about $98 |

That last row is measured straight from the chain, not from a tracker:
15,770 BTS changed hands in 24 hours at 0.000947 USDT each.

OctoBot already ships MEXC and Gate plug-ins, so the pairing that actually
exists is **MEXC or Gate against the BitShares DEX**, not Binance.

And read that table the right way round. The thin side is the DEX, by roughly
four thousand to one. An arbitrage bot does not create depth; it takes it. If
you send a meaningful order into a book doing $15 a day, you are not
capturing a spread, you are the spread.

Which points at the more realistic use. You are not a passing arbitrageur on
this venue - it is your own ecosystem's exchange. **Quoting** those books
(OctoBot ships `market_making_trading_mode` and
`staggered_orders_trading_mode`) puts depth where there is none. The
arbitrage mode is the right tool once there is a book worth arbitraging.

## Honest limits

**The NESS and NCH markets are near-empty.** Both show zero 24-hour volume on
chain right now, NESS/BTS quotes a 21% spread, and over ninety days the chain
holds two daily candles for NESS/BTS and one for NCH/BTS. Indicators need
candles that do not exist yet.

**Limit orders only.** The BitShares DEX has no "market order" - every order
names its price. OctoBot strategies that want to buy at whatever the price is
will refuse rather than guess.

**Candle sizes are fixed by the chain**: 1m, 5m, 15m, 1h, 4h, 1d, 1w. Ask for
30m and you get a clear error rather than quietly wrong data.

**Candles are sparse.** The chain only records a candle for periods in which
somebody traded, so quiet markets have gaps. Nothing here invents the missing
bars; a visible hole is better than a made-up price.

**No live feed.** There is no websocket, so OctoBot polls for updates rather
than being pushed them.

## On a phone

**The bot itself does not run on Android.** OctoBot needs a set of Python
libraries — numpy, pyarrow, cryptography, coincurve, web3 — that have no
ready-made builds for Android, so every one of them would have to be compiled
on the handset. (This is a reading of the dependency list, not something tested
on a device.)

**What works from a phone is everything else.** OctoBot serves a web interface
on port 5001 that works fine in a phone browser, so the normal arrangement is:
the bot runs on a computer that stays on, and you watch and control it from
your phone. There is also an official OctoBot app on Google Play and the App
Store, though the public version is aimed at their cloud service rather than at
your own bot.

For looking at the BitShares market itself — prices, order book, NESS and NCH
balances — a phone works directly, because the chain answers over plain HTTPS
with no server in between.

---

## Running it alongside KuCoin

That is the point of the exercise, and it works: one OctoBot, both exchanges,
one strategy. Verified in a real run:

```
Starting OctoBot with simulated trader on bitshares_dex[spot], kucoin[spot]
trading NESS/BTS, NCH/BTS, BTC/USDT, BTS/USDT with ArbitrageTradingMode
Loaded 6 [bitshares_dex] markets
Starting on listening for NESS/BTS arbitrage opportunities on bitshares_dex
```

Two things are set **per OctoBot, not per exchange**, and they surprise people:

1. **Paper trading or real trading is one switch for the whole bot.** You
   cannot have KuCoin live and BitShares on paper at the same time. If you want
   that, run two OctoBots.
2. **A pair has to exist on both venues** for the arbitrage mode to compare
   anything. NESS/BTS exists only on BitShares, so there is no second price to
   compare it with; the pair both venues share is BTS/USDT. Note that KuCoin's
   USDT and BitShares' XBTSX.USDT are not the same token — one is Tether, the
   other is a gateway's claim on Tether — so part of any gap between them is
   the risk of that gateway, not free money.
