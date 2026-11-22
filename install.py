"""BitShares DEX for OctoBot — the install steps.

Normally driven by setup.py (the menu). Usable directly:

    python install.py --octobot "C:\\OctoBot"
    python install.py --octobot "C:\\OctoBot" --bridge "C:\\src\\bitshares-ccxt-bridge"

Everything it writes lives inside the OctoBot folder you point it at, or
inside the bridge folder. Nothing goes into Python's site-packages and no
OctoBot file is edited by hand.
"""

import argparse
import glob
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TENTACLE_SRC = os.path.join(HERE, "tentacle", "reference_tentacles")
TENTACLE_NAME = "bitshares_dex"
BRIDGE_REPO = "https://github.com/Jeff-Bouchard/bitshares-ccxt-bridge.git"
MIN_PYTHON = (3, 12)  # OctoBot 2.1.1 declares requires_python >=3.12

CURRENCIES = {
    "BitShares": {"enabled": True, "pairs": ["BTS/USDT"]},
    "NESS": {"enabled": True, "pairs": ["NESS/BTS"]},
    "NCH": {"enabled": True, "pairs": ["NCH/BTS"]},
}


def say(label, value=""):
    print("  %-14s %s" % (label, value))


def run(python, code, cwd=None):
    try:
        result = subprocess.run([python, "-c", code], capture_output=True, text=True,
                                cwd=cwd, timeout=300)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as err:
        return 1, "", str(err)


# --- locating things ---------------------------------------------------------

def venv_python(octobot_dir):
    """The interpreter inside <octobot_dir>/venv, if there is one."""
    for parts in (("venv", "Scripts", "python.exe"), ("venv", "bin", "python"),
                  (".venv", "Scripts", "python.exe"), (".venv", "bin", "python")):
        candidate = os.path.join(octobot_dir, *parts)
        if os.path.isfile(candidate):
            return candidate
    return ""


def octobot_cli(python):
    """The OctoBot console script next to a given interpreter."""
    folder = os.path.dirname(python)
    for name in ("OctoBot.exe", "OctoBot", "octobot.exe", "octobot"):
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate):
            return candidate
    return ""


def base_pythons():
    """Interpreters new enough to host OctoBot, best first."""
    found = []
    if sys.version_info[:2] >= MIN_PYTHON:
        found.append(sys.executable)
    for name in ("python3.14", "python3.13", "python3.12", "python3", "python"):
        path = shutil.which(name)
        if path and path not in found:
            found.append(path)
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            for flag in ("-3.14", "-3.13", "-3.12", "-3"):
                probe = subprocess.run([launcher, flag, "-c", "import sys;print(sys.executable)"],
                                       capture_output=True, text=True)
                if probe.returncode == 0 and probe.stdout.strip() not in found:
                    found.append(probe.stdout.strip())
    good = []
    for path in found:
        status, out, _ = run(path, "import sys;print('%d.%d' % sys.version_info[:2])")
        if status == 0:
            try:
                if tuple(int(part) for part in out.split(".")) >= MIN_PYTHON:
                    good.append(path)
            except ValueError:
                pass
    return good


# --- step 1: OctoBot itself --------------------------------------------------

def install_octobot(target, base=None):
    """Make a venv under `target` and pip install OctoBot into it.

    OctoBot 2.1.1 and its OctoBot-* dependencies install as pure Python — no
    Cython step and no MSVC Build Tools, despite several of them shipping as
    source distributions. The only hard requirement is a new enough
    interpreter.
    """
    print("\n[1] OctoBot")
    candidates = base_pythons() if base is None else [base]
    if not candidates:
        raise SystemExit(
            "No Python %d.%d+ found. OctoBot 2.1.1 requires it — the installation docs\n"
            "still say 3.10, which was true of OctoBot 2.0. Install a current Python from\n"
            "python.org, ticking 'Add python.exe to PATH'." % MIN_PYTHON)
    base = candidates[0]
    say("base python", base)

    target = os.path.abspath(target)
    os.makedirs(target, exist_ok=True)
    venv = os.path.join(target, "venv")
    python = os.path.join(venv, "Scripts", "python.exe") if os.name == "nt" \
        else os.path.join(venv, "bin", "python")
    if not os.path.isfile(python):
        say("venv", venv)
        if subprocess.run([base, "-m", "venv", venv]).returncode:
            raise SystemExit("could not create a virtual environment at %s" % venv)
    subprocess.run([python, "-m", "pip", "install", "-q", "--upgrade", "pip", "setuptools", "wheel"])

    say("pip install", "OctoBot — several hundred MB, give it a few minutes")
    if subprocess.run([python, "-m", "pip", "install", "--upgrade", "OctoBot"]).returncode:
        raise SystemExit("pip install OctoBot failed")
    status, out, err = run(python, "import octobot;print(octobot.VERSION)")
    if status:
        raise SystemExit("OctoBot did not import after installing: %s" % (err or out))
    say("installed", "OctoBot %s" % out)

    cli = octobot_cli(python)
    if not cli:
        raise SystemExit("OctoBot installed but its console script is missing from %s"
                         % os.path.dirname(python))
    if not os.path.isdir(os.path.join(target, "tentacles")):
        say("tentacles", "downloading the official set — this also takes a few minutes")
        subprocess.run([cli, "tentacles", "--install", "--all"], cwd=target)
    return python


# --- step 2: the tentacle ----------------------------------------------------

def install_tentacle(octobot_dir, python):
    """Install the BitShares tentacle through OctoBot's own installer.

    The tentacle is packed into the layout OctoBot expects
    (reference_tentacles/Trading/Exchange/...) and handed to
    `OctoBot tentacles --install --location <zip>`. Using the real installer
    rather than copying files means OctoBot regenerates its own tentacle
    index, so the exchange is registered the same way every official one is.
    """
    print("\n[2] BitShares tentacle")
    if not os.path.isdir(TENTACLE_SRC):
        raise SystemExit("tentacle sources missing at %s" % TENTACLE_SRC)
    cli = octobot_cli(python)
    if not cli:
        raise SystemExit("cannot find the OctoBot console script next to %s" % python)

    with tempfile.TemporaryDirectory() as temp:
        package = os.path.join(temp, "bitshares-dex-tentacle.zip")
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for root, _dirs, files in os.walk(TENTACLE_SRC):
                for name in files:
                    if "__pycache__" in root:
                        continue
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, os.path.dirname(TENTACLE_SRC))
                    archive.write(full, rel)
        say("packed", os.path.basename(package))
        result = subprocess.run([cli, "tentacles", "--install", "--all", "--location", package],
                                cwd=octobot_dir, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("tentacle install failed:\n%s" % (result.stderr or result.stdout)[-600:])

    folder = os.path.join(octobot_dir, "tentacles", "Trading", "Exchange", TENTACLE_NAME)
    if not os.path.isdir(folder):
        raise SystemExit("installer reported success but %s is not there" % folder)
    say("installed", folder)
    return folder


# --- step 3: the profile -----------------------------------------------------

def find_profiles(octobot_dir):
    return sorted(glob.glob(os.path.join(octobot_dir, "user", "profiles", "*", "profile.json")))


def patch_profile(path):
    print("\n[3] profile")
    with open(path, "r", encoding="utf-8") as handle:
        profile = json.load(handle)
    config = profile.get("config", profile)

    shutil.copyfile(path, path + ".bak")
    exchanges = config.setdefault("exchanges", {})
    exchanges.setdefault("bitshares_dex", {})["enabled"] = True
    currencies = config.setdefault("crypto-currencies", {})
    for name, entry in CURRENCIES.items():
        currencies.setdefault(name, entry)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=2)
        handle.write("\n")
    say("profile", path)
    say("exchanges", ", ".join(sorted(exchanges)))
    say("pairs", ", ".join(p for e in currencies.values() for p in e.get("pairs", [])))


# --- step 4: Node and the signing bridge (optional) --------------------------

def ensure_node():
    node = shutil.which("node")
    if node:
        version = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip()
        try:
            if int(version.lstrip("v").split(".")[0]) >= 20:
                return node
        except ValueError:
            pass
        say("node", "%s is too old, 20 or newer is needed" % version)
    if os.name == "nt" and shutil.which("winget"):
        say("node", "installing via winget")
        subprocess.run(["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS",
                        "--accept-source-agreements", "--accept-package-agreements"])
        print("  Node installed. Close this window, open a new one so PATH refreshes,")
        print("  then run setup again.")
        return None
    say("node", "not found — get Node 20 or newer from nodejs.org")
    return None


def clone_bridge(target):
    target = os.path.abspath(target)
    if os.path.isfile(os.path.join(target, "package.json")):
        say("bridge", "already at %s" % target)
        return target
    git = shutil.which("git")
    if not git:
        raise SystemExit("git not found — install Git for Windows")
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    say("git clone", BRIDGE_REPO)
    if subprocess.run([git, "clone", "--depth", "1", BRIDGE_REPO, target]).returncode:
        raise SystemExit("clone failed")
    return target


GATE_ANCHOR = """const app = express();
app.use(cors());
app.use(express.json());"""

GATE = GATE_ANCHOR + """

// --- lock the door -------------------------------------------------------
// Every route below this one can move money. Without BRIDGE_TOKEN set the
// server still starts, and says on stdout that it is open.
const bridgeToken = process.env.BRIDGE_TOKEN ? String(process.env.BRIDGE_TOKEN).trim() : '';
if (!bridgeToken) {
  console.warn('[startup] BRIDGE_TOKEN is not set: anyone who can reach this port can trade.');
}
app.use((req, res, next) => {
  if (!bridgeToken) return next();
  const header = String(req.headers.authorization || '');
  const offered = header.startsWith('Bearer ') ? header.slice(7).trim() : '';
  if (offered !== bridgeToken) {
    return res.status(401).json({ error: 'unauthorized: missing or wrong bearer token' });
  }
  next();
});"""

BIND_ANCHOR = """app.listen(port, () => {
  console.log(`BitShares CCXT REST API running on port ${port}`);
});"""

BIND = """// express's app.listen(port) with no host binds every interface, which puts
// the signer on your LAN and on any VPN you join.
const host = process.env.BIND_HOST || '127.0.0.1';
app.listen(Number(port), host, () => {
  console.log(`BitShares CCXT REST API running on ${host}:${port}`);
});"""


def harden_bridge(bridge, build=True):
    print("\n[4] bridge")
    source = os.path.join(bridge, "src", "rest", "server.ts")
    if not os.path.isfile(source):
        raise SystemExit("no src/rest/server.ts under %s — is that the bridge repo?" % bridge)

    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    original = text
    changed = []

    if "BRIDGE_TOKEN" in text:
        say("token gate", "already present")
    elif GATE_ANCHOR in text:
        text = text.replace(GATE_ANCHOR, GATE, 1)
        changed.append("token gate")
    else:
        say("token gate", "SKIPPED — express setup is not where expected, add it by hand")

    if "BIND_HOST" in text:
        say("bind", "already loopback")
    elif BIND_ANCHOR in text:
        text = text.replace(BIND_ANCHOR, BIND, 1)
        changed.append("loopback bind")
    else:
        say("bind", "SKIPPED — listen() is not where expected, add it by hand")

    if text != original:
        shutil.copyfile(source, source + ".bak")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(text)
        say("patched", ", ".join(changed) + "   (backup: server.ts.bak)")

    if not build:
        return
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        say("build", "npm not found — run `npm ci && npm run build` yourself")
        return
    # The committed node_modules ships btsdex without its lib/ folder, so the
    # server dies at startup unless the tree is rebuilt from the lockfile.
    if not os.path.isfile(os.path.join(bridge, "node_modules", "btsdex", "lib", "index.js")):
        say("npm ci", "the committed node_modules is incomplete, rebuilding")
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=bridge)
    result = subprocess.run([npm, "run", "build"], cwd=bridge, capture_output=True, text=True)
    say("build", "ok" if result.returncode == 0 else "FAILED: " + (result.stderr or result.stdout)[-200:])


def write_bridge_env(bridge, account=None, wif=None):
    print("\n[5] token and launcher")
    path = os.path.join(bridge, ".env")
    values = {}
    order = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    order.append(("raw", line.rstrip("\n")))
                    continue
                key, _, value = stripped.partition("=")
                values[key.strip()] = value.strip()
                order.append(("key", key.strip()))

    reused = bool(values.get("BRIDGE_TOKEN"))
    token = values.get("BRIDGE_TOKEN") or secrets.token_urlsafe(32)
    values["BRIDGE_TOKEN"] = token
    if account:
        values["BTS_ACCOUNT"] = account
        values["BTS_VIEW_ONLY"] = "false" if wif else "true"
    if wif:
        values["BTS_WIF"] = wif
    values.setdefault("PORT", "8787")
    values.setdefault("BTS_NODE", "wss://node.xbts.io/ws")

    written = set()
    out = []
    for kind, value in order:
        if kind == "raw":
            out.append(value)
        elif value not in written:
            out.append("%s=%s" % (value, values[value]))
            written.add(value)
    for key in values:
        if key not in written:
            out.append("%s=%s" % (key, values[key]))

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out).rstrip() + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    say("BRIDGE_TOKEN", "reused the existing one" if reused else "generated")
    if os.name == "nt":
        subprocess.run(["icacls", path, "/inheritance:r", "/grant:r",
                        "%s:F" % os.environ.get("USERNAME", "")], capture_output=True)
        say("acl", ".env restricted to you")

    port = values.get("PORT", "8787")
    with open(os.path.join(bridge, "start-bridge.bat"), "w", encoding="utf-8") as handle:
        handle.write('@echo off\r\ncd /d "%~dp0"\r\nnode dist\\rest\\server.js\r\n')
    sh_path = os.path.join(bridge, "start-bridge.sh")
    with open(sh_path, "w", encoding="utf-8") as handle:
        handle.write('#!/usr/bin/env bash\ncd "$(dirname "$0")"\nexec node dist/rest/server.js\n')
    try:
        os.chmod(sh_path, 0o755)
    except OSError:
        pass
    say("launcher", "start-bridge.bat / start-bridge.sh")
    return token, port


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--octobot", required=True, help="OctoBot folder (holds tentacles/ and user/)")
    parser.add_argument("--python", help="OctoBot's python; defaults to <octobot>/venv")
    parser.add_argument("--install-octobot", action="store_true",
                        help="create the venv and pip install OctoBot first")
    parser.add_argument("--bridge", help="path to a bitshares-ccxt-bridge clone, for live trading")
    parser.add_argument("--account", help="BitShares account the bridge trades as")
    parser.add_argument("--wif", help="that account's active key. Omit to stay read-only.")
    parser.add_argument("--profile", action="append",
                        help="profile name or profile.json path to enable BitShares in; "
                             "repeatable. Default: arbitrage_trading if it exists.")
    parser.add_argument("--all-profiles", action="store_true",
                        help="enable it in every profile instead")
    args = parser.parse_args()

    octobot_dir = os.path.abspath(args.octobot)
    python = args.python or venv_python(octobot_dir)
    if args.install_octobot or not python:
        python = install_octobot(octobot_dir)

    install_tentacle(octobot_dir, python)

    found = find_profiles(octobot_dir)
    names = {os.path.basename(os.path.dirname(p)): p for p in found}
    if args.all_profiles:
        profiles = found
    elif args.profile:
        profiles = [names.get(p, p) for p in args.profile]
    elif "arbitrage_trading" in names:
        profiles = [names["arbitrage_trading"]]
    else:
        profiles = found[:1]
    for profile in profiles:
        if os.path.isfile(profile):
            patch_profile(profile)
        else:
            print("  no such profile: %s" % profile)

    token = port = None
    if args.bridge:
        bridge = clone_bridge(args.bridge)
        ensure_node()
        harden_bridge(bridge)
        token, port = write_bridge_env(bridge, args.account, args.wif)

    print("\ndone.\n")
    if token:
        print("Start the bridge with start-bridge.bat, then set these two in the")
        print("environment OctoBot runs under:")
        print("    BITSHARES_CCXT_BRIDGE_URL=http://127.0.0.1:%s" % port)
        print("    BRIDGE_TOKEN=%s" % token)
    else:
        print("No bridge configured, so no private key is on this machine and nothing")
        print("listens on a port. Prices and candles come straight off the chain and")
        print("OctoBot's paper-trading mode works as it is.")


if __name__ == "__main__":
    main()
