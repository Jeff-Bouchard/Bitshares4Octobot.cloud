"""BitShares DEX for OctoBot — setup menu.

    setup.bat        (Windows)
    ./setup.sh       (everything else)

A numbered menu and plain input(), no raw terminal mode, so cmd.exe,
PowerShell, Windows Terminal and Git Bash all behave the same way.

No dependencies of its own: the chain checks talk to public BitShares nodes
over ordinary HTTPS with urllib, and anything needing OctoBot or ccxt is run
by OctoBot's own interpreter rather than this one.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import install  # noqa: E402  — same folder, holds the real steps

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "setup.json")

NODES = [
    "https://api.bts.mobi",
    "https://node.xbts.io/ws",
    "https://api.dex.trading",
    "https://public.xbts.io/ws",
]

OK, BAD, SKIP = "ok", "bad", "skip"
MARK = {OK: "[ ok ]", BAD: "[FAIL]", SKIP: "[ -- ]"}


# --------------------------------------------------------------- plumbing ---

def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
    except OSError:
        pass


def ask(prompt, default=""):
    try:
        answer = input("%s%s: " % (prompt, (" [%s]" % default) if default else "")).strip()
    except EOFError:
        return default
    return answer or default


def confirm(prompt, default=True):
    answer = ask("%s (%s)" % (prompt, "Y/n" if default else "y/N"),
                 "y" if default else "n").lower()
    return answer.startswith("y")


def rpc(api, method, params, timeout=12):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "call",
                       "params": [api, method, params]}).encode()
    last = None
    for node in NODES:
        try:
            request = urllib.request.Request(
                node, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read())
            if "error" in payload:
                raise RuntimeError(str(payload["error"])[:120])
            return payload["result"], node
        except Exception as err:
            last = err
    raise RuntimeError("no BitShares node answered (%s)" % last)


def http(url, token=None, timeout=10):
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(200)
    except urllib.error.HTTPError as err:
        return err.code, err.read(200)
    except Exception as err:
        return None, str(err).encode()


def find_octobot(state):
    if state.get("octobot") and os.path.isdir(state["octobot"]):
        return state["octobot"]
    for candidate in (os.getcwd(), os.path.dirname(HERE),
                      os.path.join(os.path.expanduser("~"), "OctoBot"), r"C:\OctoBot"):
        if os.path.isdir(os.path.join(candidate, "tentacles")):
            return candidate
    return ""


def find_bridge(state):
    if state.get("bridge") and os.path.isdir(state["bridge"]):
        return state["bridge"]
    for root in (os.getcwd(), os.path.dirname(HERE), os.path.expanduser("~")):
        candidate = os.path.join(root, "bitshares-ccxt-bridge")
        if os.path.isfile(os.path.join(candidate, "package.json")):
            return candidate
    return ""


def bridge_env(bridge):
    values = {}
    path = os.path.join(bridge, ".env") if bridge else ""
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    values[key.strip()] = value.strip()
    return values


# ------------------------------------------------------------------ setup ---

class Setup:
    def __init__(self):
        self.state = load_state()
        self.octobot = find_octobot(self.state)
        self.python = self.state.get("python") or (install.venv_python(self.octobot)
                                                   if self.octobot else "")
        self.bridge = find_bridge(self.state)
        self.results = {}

    def persist(self):
        self.state.update({"octobot": self.octobot, "python": self.python,
                           "bridge": self.bridge})
        save_state(self.state)

    def bot_run(self, code):
        """Run code with OctoBot's interpreter, inside the OctoBot folder.
        Tentacles are found relative to the working directory, so the cwd
        matters as much as the interpreter."""
        if not self.python or not self.octobot:
            return 1, "", "OctoBot folder or interpreter not set"
        return install.run(self.python, code, cwd=self.octobot)

    # -- checks -------------------------------------------------------------

    def check_octobot_folder(self):
        if not self.octobot:
            return BAD, "not set — press o to install, or f to point at an existing one"
        if not os.path.isdir(self.octobot):
            return BAD, "no such folder: %s" % self.octobot
        if not os.path.isdir(os.path.join(self.octobot, "tentacles")):
            return BAD, "%s has no tentacles folder — not an OctoBot install" % self.octobot
        return OK, self.octobot

    def check_python(self):
        if not self.python or not os.path.isfile(self.python):
            return BAD, "no interpreter — press o to install OctoBot"
        status, version, err = install.run(self.python, "import sys;print(sys.version.split()[0])")
        if status:
            return BAD, (err or version)[:70]
        if tuple(int(p) for p in version.split(".")[:2]) < install.MIN_PYTHON:
            return BAD, "%s — OctoBot 2.1.1 needs %d.%d or newer" % ((version,) + install.MIN_PYTHON)
        return OK, "%s  %s" % (version, self.python)

    def check_octobot_installed(self):
        status, out, _ = install.run(self.python, "import octobot;print(octobot.VERSION)") \
            if self.python else (1, "", "")
        if status:
            return BAD, "OctoBot is not installed in that interpreter"
        return OK, "OctoBot %s" % out

    def fix_install_octobot(self):
        target = self.octobot or ask("  install OctoBot where",
                                     os.path.join(os.path.expanduser("~"), "OctoBot"))
        try:
            self.python = install.install_octobot(target)
        except SystemExit as err:
            print("  %s" % err)
            return
        self.octobot = os.path.abspath(target)
        self.persist()

    def check_tentacle(self):
        if not self.octobot:
            return SKIP, "no OctoBot folder yet"
        folder = os.path.join(self.octobot, "tentacles", "Trading", "Exchange", "bitshares_dex")
        if not os.path.isdir(folder):
            return BAD, "not installed"
        index = os.path.join(self.octobot, "tentacles", "Trading", "Exchange", "__init__.py")
        try:
            with open(index, "r", encoding="utf-8") as handle:
                listed = "bitshares_dex" in handle.read()
        except OSError:
            listed = False
        if not listed:
            return BAD, "folder present but missing from OctoBot's tentacle index"
        try:
            with open(os.path.join(folder, "metadata.json"), "r", encoding="utf-8") as handle:
                version = json.load(handle).get("version", "?")
        except Exception:
            version = "?"
        return OK, "version %s, in the tentacle index" % version

    def fix_tentacle(self):
        try:
            install.install_tentacle(self.octobot, self.python)
        except SystemExit as err:
            print("  %s" % err)

    def check_resolution(self):
        """The question that actually matters: does OctoBot pick our exchange
        class for the name 'bitshares_dex'?"""
        code = (
            "import octobot_tentacles_manager.api as tm\n"
            "tm.load_tentacles(verbose=False)\n"
            "import octobot_trading.exchanges.util.exchange_util as eu\n"
            "cfg = tm.get_tentacles_setup_config()\n"
            "print(eu.get_rest_exchange_class('bitshares_dex', cfg, None).__name__)\n")
        status, out, err = self.bot_run(code)
        if status:
            return BAD, (err.splitlines() or [""])[-1][:70]
        if out == "DefaultRestExchange":
            return BAD, "falls back to the generic class — the tentacle is not active"
        return OK, "OctoBot uses %s" % out

    def check_chain(self):
        try:
            buckets, node = rpc("history", "get_market_history_buckets", [])
            return OK, "%s, candle sizes %s" % (node.split("//")[1], buckets)
        except Exception as err:
            return BAD, str(err)[:70]

    def check_assets(self):
        try:
            assets, _ = rpc("database", "lookup_asset_symbols", [["XBTSX.NESS", "XBTSX.NCH"]])
            missing = [n for n, a in zip(("XBTSX.NESS", "XBTSX.NCH"), assets) if not a]
            if missing:
                return BAD, "not found on chain: %s" % ", ".join(missing)
            return OK, "  ".join("%s %s" % (a["symbol"], a["id"]) for a in assets)
        except Exception as err:
            return BAD, str(err)[:70]

    def check_prices(self):
        try:
            ticker, _ = rpc("database", "get_ticker", ["BTS", "XBTSX.NESS"])
            bid, ask = float(ticker["highest_bid"]), float(ticker["lowest_ask"])
            spread = (ask - bid) / bid * 100 if bid else 0
            return OK, "NESS/BTS bid %s ask %s  spread %.0f%%" % (
                ticker["highest_bid"], ticker["lowest_ask"], spread)
        except Exception as err:
            return BAD, str(err)[:70]

    def check_exchange(self):
        """Drive the exchange exactly as OctoBot will, through the tentacle."""
        code = (
            "import asyncio, octobot_tentacles_manager.api as tm\n"
            "tm.load_tentacles(verbose=False)\n"
            "import ccxt.async_support as ca\n"
            "async def main():\n"
            "    ex = ca.bitshares_dex()\n"
            "    try:\n"
            "        m = await ex.load_markets()\n"
            "        t = await ex.fetch_ticker('NESS/BTS')\n"
            "        print(len(m), t['last'], len(ex.timeframes))\n"
            "    finally:\n"
            "        await ex.close()\n"
            "asyncio.run(main())\n")
        status, out, err = self.bot_run(code)
        if status:
            return BAD, (err.splitlines() or [""])[-1][:70]
        parts = out.split()
        if len(parts) < 3:
            return BAD, out[:70]
        return OK, "%s markets, NESS/BTS last %s BTS, %s candle sizes" % tuple(parts[:3])

    def check_profiles(self):
        if not self.octobot:
            return SKIP, "no OctoBot folder yet"
        profiles = install.find_profiles(self.octobot)
        if not profiles:
            return BAD, "no profile.json found under user/profiles"
        enabled = []
        for path in profiles:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                continue
            config = data.get("config", data)
            if config.get("exchanges", {}).get("bitshares_dex", {}).get("enabled"):
                enabled.append(os.path.basename(os.path.dirname(path)))
        if not enabled:
            return BAD, "%d profiles, none with bitshares_dex enabled" % len(profiles)
        return OK, "enabled in: %s" % ", ".join(enabled)

    def fix_profiles(self):
        profiles = install.find_profiles(self.octobot)
        if not profiles:
            print("  no profiles found under user/profiles")
            return
        names = [os.path.basename(os.path.dirname(p)) for p in profiles]
        default = "arbitrage_trading" if "arbitrage_trading" in names else names[0]
        print("  profiles: %s" % ", ".join(names))
        print("  Enabling an exchange in a profile is per profile, not global.")
        chosen = ask("  which one (or 'all')", default)
        if chosen.strip().lower() == "all":
            targets = profiles
        else:
            wanted = {n.strip() for n in chosen.split(",")}
            targets = [p for p, n in zip(profiles, names) if n in wanted]
            if not targets:
                print("  no profile called %r" % chosen)
                return
        for path in targets:
            install.patch_profile(path)

    def check_node(self):
        node = shutil.which("node")
        if not node:
            return BAD, "not installed — only needed to place real orders"
        version = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip()
        try:
            major = int(version.lstrip("v").split(".")[0])
        except ValueError:
            return BAD, "cannot read version %r" % version
        return (OK, version) if major >= 20 else (BAD, "%s — 20 or newer is needed" % version)

    def fix_node(self):
        install.ensure_node()

    def check_bridge_built(self):
        if not self.bridge:
            return SKIP, "not set up — optional, only needed to place real orders"
        if not os.path.isfile(os.path.join(self.bridge, "package.json")):
            return BAD, "not the bridge repo: %s" % self.bridge
        problems = []
        if not os.path.isfile(os.path.join(self.bridge, "node_modules", "btsdex", "lib", "index.js")):
            problems.append("btsdex/lib missing, needs npm ci")
        if not os.path.isfile(os.path.join(self.bridge, "dist", "rest", "server.js")):
            problems.append("not built")
        return (BAD, "; ".join(problems)) if problems else (OK, self.bridge)

    def fix_bridge_built(self):
        target = self.bridge or ask("  put the bridge where",
                                    os.path.join(os.path.expanduser("~"), "bitshares-ccxt-bridge"))
        try:
            self.bridge = install.clone_bridge(target)
            install.ensure_node()
            install.harden_bridge(self.bridge, build=True)
        except SystemExit as err:
            print("  %s" % err)
        self.persist()

    def check_bridge_hardened(self):
        if not self.bridge:
            return SKIP, ""
        source = os.path.join(self.bridge, "src", "rest", "server.ts")
        if not os.path.isfile(source):
            return BAD, "server.ts not found"
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()
        missing = []
        if "BRIDGE_TOKEN" not in text:
            missing.append("no password on the trading port")
        if "BIND_HOST" not in text:
            missing.append("listening on every network interface")
        if missing:
            return BAD, "; ".join(missing)
        token = bridge_env(self.bridge).get("BRIDGE_TOKEN", "")
        if not token:
            return BAD, "patched, but BRIDGE_TOKEN is empty in .env"
        return OK, "loopback only, password set (%d characters)" % len(token)

    def fix_bridge_hardened(self):
        install.harden_bridge(self.bridge, build=True)
        account = ask("  BitShares account for the bot (blank to leave .env alone)")
        wif = ""
        if account:
            print("  Use a SECOND account holding only what the bot trades with.")
            print("  BitShares cannot limit a key to orders-only, so the limit is the balance.")
            if confirm("  Store its active key now?", False):
                try:
                    import getpass
                    wif = getpass.getpass("  active key (hidden): ").strip()
                except Exception:
                    wif = ""
        install.write_bridge_env(self.bridge, account or None, wif or None)

    def check_bridge_running(self):
        if not self.bridge:
            return SKIP, ""
        values = bridge_env(self.bridge)
        port = values.get("PORT", "8787")
        token = values.get("BRIDGE_TOKEN", "")
        url = "http://127.0.0.1:%s/markets" % port
        status, _ = http(url, token)
        if status is None:
            return BAD, "nothing answering on 127.0.0.1:%s — run start-bridge.bat" % port
        if status == 401:
            return BAD, "401 using the .env password — the running process has a different one"
        if status != 200:
            return BAD, "HTTP %s" % status
        if not token:
            return BAD, "up on %s but with NO password — anyone reaching the port can trade" % port
        unauth, _ = http(url)
        if unauth != 401:
            return BAD, "password is set but an unauthenticated request got HTTP %s" % unauth
        return OK, "up on %s, unauthenticated requests refused" % port

    # -- the table ----------------------------------------------------------

    def items(self):
        return [
            ("OctoBot folder", self.check_octobot_folder, self.fix_install_octobot),
            ("Python 3.12+", self.check_python, self.fix_install_octobot),
            ("OctoBot installed", self.check_octobot_installed, self.fix_install_octobot),
            ("BitShares tentacle", self.check_tentacle, self.fix_tentacle),
            ("OctoBot uses it", self.check_resolution, self.fix_tentacle),
            ("Chain reachable", self.check_chain, None),
            ("NESS / NCH assets", self.check_assets, None),
            ("Live prices", self.check_prices, None),
            ("Exchange end to end", self.check_exchange, self.fix_tentacle),
            ("Trading profile", self.check_profiles, self.fix_profiles),
            ("Node.js 20+", self.check_node, self.fix_node),
            ("Signing bridge built", self.check_bridge_built, self.fix_bridge_built),
            ("Bridge locked down", self.check_bridge_hardened, self.fix_bridge_hardened),
            ("Bridge running", self.check_bridge_running, None),
        ]

    def run_all(self):
        print("\nchecking...")
        self.results = {}
        for index, (name, check, _fix) in enumerate(self.items(), 1):
            try:
                self.results[index] = check()
            except Exception as err:
                self.results[index] = (BAD, "check raised: %s" % str(err)[:60])

    def show(self):
        print("\n  BitShares DEX for OctoBot — setup\n")
        for index, (name, _check, fix) in enumerate(self.items(), 1):
            status, detail = self.results.get(index, (SKIP, "not checked"))
            flag = "*" if (status == BAD and fix) else " "
            print("  %2d%s %s %-21s %s" % (index, flag, MARK[status], name, detail))
        bad = sum(1 for status, _ in self.results.values() if status == BAD)
        print("\n     * = this one can fix itself.   %d failing." % bad)
        print("""
   o  install OctoBot        f  point at an OctoBot folder
   p  set OctoBot's python   b  point at the bridge      n  install Node.js
   a  fix everything marked *    r  re-check    q  quit""")

    def fix_one(self, index):
        name, check, fix = self.items()[index - 1]
        status, detail = check()
        print("\n  %s %s: %s" % (MARK[status], name, detail))
        if status == OK:
            return
        if fix is None:
            print("  nothing automatic for this one.")
            if name == "Bridge running":
                print("  start it yourself: start-bridge.bat in %s" % (self.bridge or "the bridge folder"))
            return
        if confirm("  fix it now?"):
            fix()
            status, detail = check()
            print("  %s %s" % (MARK[status], detail))
            self.results[index] = (status, detail)

    def fix_all(self):
        already = []
        for index, (name, check, fix) in enumerate(self.items(), 1):
            if fix is None:
                continue
            status, _ = self.results.get(index, check())
            if status != BAD or fix in already:
                continue
            print("\n>> %s" % name)
            fix()
            already.append(fix)
        self.run_all()


def main():
    setup = Setup()
    setup.run_all()
    while True:
        setup.show()
        choice = ask("\n  choice").lower()
        if choice in ("q", "quit", "exit"):
            setup.persist()
            print("  saved to setup.json\n")
            return
        if choice == "r":
            setup.run_all()
        elif choice == "a":
            setup.fix_all()
        elif choice == "o":
            setup.octobot = ask("  install OctoBot where",
                                setup.octobot or os.path.join(os.path.expanduser("~"), "OctoBot"))
            setup.fix_install_octobot()
            setup.run_all()
        elif choice == "f":
            setup.octobot = os.path.abspath(ask("  OctoBot folder", setup.octobot))
            setup.python = install.venv_python(setup.octobot) or setup.python
            setup.persist()
            setup.run_all()
        elif choice == "p":
            setup.python = os.path.abspath(ask("  path to OctoBot's python", setup.python))
            setup.persist()
            setup.run_all()
        elif choice == "b":
            setup.bridge = os.path.abspath(ask("  bridge folder", setup.bridge))
            setup.persist()
            setup.run_all()
        elif choice == "n":
            install.ensure_node()
            setup.run_all()
        elif choice.isdigit() and 1 <= int(choice) <= len(setup.items()):
            setup.fix_one(int(choice))
            setup.persist()
        else:
            print("  ?")


if __name__ == "__main__":
    main()
