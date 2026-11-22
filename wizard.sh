#!/usr/bin/env bash
#
# BitShares for OctoBot - guided setup.
#
#   ./wizard.sh
#
# Bash only. Runs in Git Bash on Windows and in any bash on Linux or macOS.
# No PowerShell, no .bat, no zip, no jq. Python is used when it is already
# there and skipped when it is not.
#
# ASCII only, on purpose: a non-ASCII character in a script is decoded
# differently depending on the terminal code page, which is a stupid way to
# break an installer.
#
# How it looks for OctoBot, in this order, and nothing else:
#   1. a --octobot folder you pass in
#   2. an OctoBot that is running right now, found by asking the OS for its
#      process list and reading the path it was started from
#   3. this folder and the one above it
#   4. $HOME/OctoBot
#   5. it asks you
#   6. it offers to download and install OctoBot
#
# It does not walk your home directory, Desktop, Downloads or Documents.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TENTACLE_SRC="$HERE/tentacle/reference_tentacles/Trading/Exchange/bitshares_dex"
TENTACLE_ZIP="$HERE/bitshares_dex_tentacle.zip"
WEB_URL="http://127.0.0.1:5001"
TENTACLE_VERSION="1.0.0"
TENTACLE_ORIGIN="PrivateNess-BitShares-Tentacle"
BINARY_BASE="https://github.com/Drakkar-Software/OctoBot-Binary/releases/latest/download"

BOT_DIR=""
BOT_CLI=""
BOT_PY=""
AUTO=0
PROFILE_CHOICE=""
INSTALL_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --octobot)     BOT_DIR="${2:-}"; shift ;;
    --profile)     PROFILE_CHOICE="${2:-}"; shift ;;
    --install-to)  INSTALL_DIR="${2:-}"; shift ;;
    --auto)        AUTO=1 ;;
    -h|--help)     sed -n '2,30p' "$0" | sed 's/^#\{0,1\} \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1"; exit 1 ;;
  esac
  shift
done

# ------------------------------------------------------------------ output --

if [ -t 1 ]; then
  C_HEAD=$'\033[1;36m'; C_OK=$'\033[0;32m'; C_WARN=$'\033[1;33m'
  C_BAD=$'\033[0;31m'; C_OFF=$'\033[0m'
else
  C_HEAD=""; C_OK=""; C_WARN=""; C_BAD=""; C_OFF=""
fi

say()  { printf '  %s\n' "$*"; }
step() { printf '\n%s  Step %s of 5 - %s%s\n' "$C_HEAD" "$1" "$2" "$C_OFF"
         printf '  %s\n' "------------------------------------------------------------"; }
good() { printf '  %s[ok]%s   %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '  %s[note]%s %s\n' "$C_WARN" "$C_OFF" "$*"; }
bad()  { printf '  %s[stop]%s %s\n' "$C_BAD" "$C_OFF" "$*"; }

ask() {
  local question="$1" default="${2:-}" reply=""
  if [ "$AUTO" = 1 ]; then printf '%s' "$default"; return; fi
  if [ -n "$default" ]; then read -r -p "  $question [$default]: " reply || true
  else read -r -p "  $question: " reply || true; fi
  printf '%s' "${reply:-$default}"
}

ask_yes() {
  local question="$1" default="${2:-y}" reply=""
  if [ "$AUTO" = 1 ]; then [ "$default" = "y" ]; return; fi
  if [ "$default" = "y" ]; then read -r -p "  $question (Y/n): " reply || true
  else read -r -p "  $question (y/N): " reply || true; fi
  reply="${reply:-$default}"
  case "$reply" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

pause_at_end() {
  [ "$AUTO" = 1 ] && return 0
  [ -t 0 ] || return 0
  read -r -p "  Press Enter to close " _ || true
}

is_octobot_dir() { [ -d "${1:-}/tentacles/Trading/Exchange" ]; }

# ------------------------------------------------- find a running OctoBot ---

# Ask the operating system what is running and read the path each process was
# started from. Cheaper and far less nosy than searching the disk: Git Bash
# answers with Windows processes through "ps -W", Linux and macOS through the
# normal ps.
list_process_entries() {
  { ps -W 2>/dev/null; ps -eo pid=,args= 2>/dev/null; ps ax -o pid=,command= 2>/dev/null; } |
    grep -i 'octobot' | tr '\\' '/' | sed 's/"//g'
}

# From the path a program was started from, walk up to the folder that holds
# "tentacles": the program may sit in the folder itself, or in venv/bin.
dir_for_program() {
  local program="$1" dir
  dir="$(dirname "$program" 2>/dev/null)" || return 1
  local hop
  for hop in 0 1 2 3; do
    [ -z "$dir" ] && return 1
    is_octobot_dir "$dir" && { (cd "$dir" && pwd); return 0; }
    dir="$(dirname "$dir")"
    [ "$dir" = "/" ] && return 1
  done
  return 1
}

find_running_octobot() {
  local line pid token dir resolved
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    pid="$(printf '%s' "$line" | awk '{print $1}')"
    case "$pid" in ''|*[!0-9]*) pid="" ;; esac
    for token in $line; do
      case "$token" in *[Oo]ctobot*|*OctoBot*) ;; *) continue ;; esac
      case "$token" in
        /*) resolved="$token" ;;
        *)  # started with a relative path, so resolve it against the working
            # directory the process was launched from, where the OS exposes it
            [ -n "$pid" ] && [ -d "/proc/$pid/cwd" ] \
              && resolved="$(readlink -f "/proc/$pid/cwd" 2>/dev/null)/${token#./}" \
              || continue ;;
      esac
      [ -e "$resolved" ] || continue
      dir="$(dir_for_program "$resolved" || true)"
      [ -n "$dir" ] && { printf '%s' "$dir"; return 0; }
    done
  done < <(list_process_entries)
  return 1
}

find_cli_for() {
  local dir="$1" candidate
  for candidate in \
      "$dir/OctoBot.exe" "$dir/OctoBot" \
      "$dir/OctoBot_windows_x64.exe" "$dir/OctoBot_linux_x64" "$dir/OctoBot_osx" \
      "$dir/venv/Scripts/OctoBot.exe" "$dir/venv/Scripts/OctoBot" \
      "$dir/venv/bin/OctoBot" "$dir/.venv/bin/OctoBot" \
      "$dir/.venv/Scripts/OctoBot.exe"; do
    [ -f "$candidate" ] && { printf '%s' "$candidate"; return 0; }
  done
  command -v OctoBot >/dev/null 2>&1 && { command -v OctoBot; return 0; }
  return 1
}

find_python_for() {
  local dir="$1" candidate
  for candidate in \
      "$dir/venv/Scripts/python.exe" "$dir/venv/bin/python" \
      "$dir/.venv/Scripts/python.exe" "$dir/.venv/bin/python"; do
    [ -f "$candidate" ] && { printf '%s' "$candidate"; return 0; }
  done
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
      "$candidate" -c "import octobot" >/dev/null 2>&1 && { command -v "$candidate"; return 0; }
    fi
  done
  return 1
}

# A Python new enough to host OctoBot 2.1.1, which declares >=3.12.
find_fresh_python() {
  local candidate
  for candidate in python3.14 python3.13 python3.12 python3 python py; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,12) else 1)' >/dev/null 2>&1; then
      command -v "$candidate"; return 0
    fi
  done
  return 1
}

octobot_is_running() {
  command -v curl >/dev/null 2>&1 || return 1
  local code
  code="$(curl -s -o /dev/null -m 4 -w '%{http_code}' "$WEB_URL" 2>/dev/null || true)"
  [ -n "$code" ] && [ "$code" != "000" ]
}

# ------------------------------------------------------- install OctoBot ----

platform_binary() {
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) printf 'OctoBot_windows_x64.exe' ;;
    Darwin)               printf 'OctoBot_osx' ;;
    Linux)
      case "$(uname -m 2>/dev/null)" in
        aarch64|arm64) printf 'OctoBot_linux_arm64' ;;
        *)             printf 'OctoBot_linux_x64' ;;
      esac ;;
    *) printf 'OctoBot_linux_x64' ;;
  esac
}

install_octobot_with_python() { # <target dir> <python>
  local target="$1" python="$2" venv="$target/venv" venv_py
  mkdir -p "$target" || return 1
  say "Making a private Python environment in $venv"
  "$python" -m venv "$venv" >/dev/null 2>&1 || { bad "Could not create it."; return 1; }
  if [ -f "$venv/Scripts/python.exe" ]; then venv_py="$venv/Scripts/python.exe"
  else venv_py="$venv/bin/python"; fi
  "$venv_py" -m pip install -q --upgrade pip setuptools wheel >/dev/null 2>&1
  say "Downloading and installing OctoBot. Several hundred MB; give it a few minutes."
  "$venv_py" -m pip install --upgrade OctoBot || { bad "The OctoBot download failed."; return 1; }
  "$venv_py" -c "import octobot" >/dev/null 2>&1 || { bad "OctoBot did not install cleanly."; return 1; }
  return 0
}

install_octobot_binary() { # <target dir>
  local target="$1" name url out
  name="$(platform_binary)"
  url="$BINARY_BASE/$name"
  command -v curl >/dev/null 2>&1 || { bad "curl is needed to download OctoBot."; return 1; }
  mkdir -p "$target" || return 1
  out="$target/$name"
  say "Downloading $name"
  say "from $url"
  curl -fL --progress-bar -o "$out" "$url" || { bad "Download failed."; rm -f "$out"; return 1; }
  [ -s "$out" ] || { bad "The downloaded file is empty."; rm -f "$out"; return 1; }
  chmod +x "$out" 2>/dev/null
  return 0
}

install_octobot() {
  local target="$1" python
  python="$(find_fresh_python || true)"
  if [ -n "$python" ]; then
    say "Found $("$python" -V 2>&1), which is new enough to run OctoBot."
    install_octobot_with_python "$target" "$python" || return 1
  else
    warn "No Python 3.12 or newer here, so I will fetch the standalone build instead."
    install_octobot_binary "$target" || return 1
  fi

  local cli
  cli="$(find_cli_for "$target" || true)"
  [ -n "$cli" ] || { bad "OctoBot installed but I cannot find its program in $target."; return 1; }
  say "Downloading OctoBot's standard plug-ins. A few more minutes."
  ( cd "$target" && "$cli" tentacles --install --all ) >/dev/null 2>&1
  is_octobot_dir "$target"
}

# ----------------------------------------------------------- the install ----

install_tentacle() {
  local exchange_dir="$BOT_DIR/tentacles/Trading/Exchange"
  [ -d "$exchange_dir" ] || { bad "No tentacles/Trading/Exchange folder in $BOT_DIR."; return 1; }
  # Older versions of this wizard left a backup here. OctoBot scans this
  # folder and treats every entry as a plug-in, so the stray file breaks it.
  rm -f "$exchange_dir/__init__.py.bak"

  # Preferred: hand the prebuilt package to OctoBot's own plug-in installer.
  # It is the only path that also marks the plug-in as active in the tentacles
  # config; without that OctoBot loads the files but falls back to its generic
  # exchange class instead of ours. The package is shipped ready-made because
  # Git Bash has no zip command to build one with.
  if [ -n "$BOT_CLI" ] && [ -f "$TENTACLE_ZIP" ]; then
    ( cd "$BOT_DIR" && "$BOT_CLI" tentacles --install --all --location "$TENTACLE_ZIP" ) >/dev/null 2>&1
    if [ -f "$exchange_dir/bitshares_dex/__init__.py" ]; then
      say "Installed with OctoBot's own plug-in installer."
      return 0
    fi
    warn "OctoBot's installer did not take it. Putting the files in place instead."
  fi

  # Fallback: copy the files and add the index entry ourselves.
  rm -rf "$exchange_dir/bitshares_dex"
  cp -r "$TENTACLE_SRC" "$exchange_dir/bitshares_dex" || return 1
  find "$exchange_dir/bitshares_dex" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  register_tentacle "$exchange_dir/__init__.py"
  activate_tentacle
  [ -f "$exchange_dir/bitshares_dex/__init__.py" ]
}

# A hand-copied plug-in is loaded but not switched on: OctoBot keeps an
# activation map per profile, and a name missing from it is treated as off.
# Measured on a clean install: without this, bitshares_dex resolves to
# ConfigurableDefaultCCXTRestExchange rather than to BitsharesDex.
activate_tentacle() {
  if [ -z "$BOT_PY" ]; then
    warn "No Python here, so I cannot switch the plug-in on in OctoBot's config."
    warn "OctoBot will load it, but may use its generic exchange class."
    return 0
  fi
  "$BOT_PY" - "$BOT_DIR" <<'PYEOF'
import glob, json, os, sys
root = sys.argv[1]
targets = glob.glob(os.path.join(root, "user", "profiles", "*", "tentacles_config.json"))
targets += glob.glob(os.path.join(root, "user", "reference_tentacles_config", "tentacles_config.json"))
changed = 0
for path in targets:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        continue
    trading = data.setdefault("tentacle_activation", {}).setdefault("Trading", {})
    if trading.get("BitsharesDex") is True:
        continue
    trading["BitsharesDex"] = True
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    changed += 1
print(changed)
PYEOF
}

register_tentacle() {
  local index="$1"
  [ -f "$index" ] || return 0
  if grep -q "bitshares_dex" "$index" 2>/dev/null; then
    say "Already listed in OctoBot's plug-in index."
    return 0
  fi
  local backup_dir="$BOT_DIR/user/bitshares_backups"
  mkdir -p "$backup_dir" 2>/dev/null
  cp "$index" "$backup_dir/Exchange__init__.py.bak" 2>/dev/null
  cat >> "$index" <<EOF

if check_tentacle_version('$TENTACLE_VERSION', 'bitshares_dex', '$TENTACLE_ORIGIN'):
    try:
        from .bitshares_dex import *
    except Exception as e:
        get_logger('TentacleLoader').error(f'Error when loading bitshares_dex: '
                                           f'{e.__class__.__name__}{f" ({e})" if f"{e}" else ""}.')
EOF
  say "Added to OctoBot's plug-in index."
}

list_profiles() {
  local root="$BOT_DIR/user/profiles"
  [ -d "$root" ] || return 0
  find "$root" -mindepth 2 -maxdepth 2 -name profile.json 2>/dev/null |
    while IFS= read -r file; do printf '%s\n' "$(basename "$(dirname "$file")")"; done | sort
}

enable_in_profile() {
  local file="$BOT_DIR/user/profiles/$1/profile.json"
  [ -f "$file" ] || { bad "No profile called $1."; return 1; }
  [ -n "$BOT_PY" ] || return 2
  "$BOT_PY" - "$file" <<'PYEOF'
import json, shutil, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
config = data.get("config", data)
shutil.copyfile(path, path + ".bak")
config.setdefault("exchanges", {}).setdefault("bitshares_dex", {})["enabled"] = True
currencies = config.setdefault("crypto-currencies", {})
for name, pair in (("BitShares", "BTS/USDT"), ("NESS", "NESS/BTS"), ("NCH", "NCH/BTS")):
    currencies.setdefault(name, {"enabled": True, "pairs": [pair]})
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
print(", ".join(sorted(config["exchanges"])))
PYEOF
}

verify_with_octobot() {
  [ -n "$BOT_PY" ] || return 2
  ( cd "$BOT_DIR" && "$BOT_PY" - <<'PYEOF'
import sys
try:
    import octobot_tentacles_manager.api as tm
    tm.load_tentacles(verbose=False)
    import octobot_trading.exchanges.util.exchange_util as eu
    print(eu.get_rest_exchange_class("bitshares_dex", tm.get_tentacles_setup_config(), None).__name__)
except Exception as err:
    print("ERROR %s: %s" % (type(err).__name__, err))
    sys.exit(1)
PYEOF
  )
}

open_browser() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$url" >/dev/null 2>&1 &
  elif command -v explorer.exe >/dev/null 2>&1; then explorer.exe "$url" >/dev/null 2>&1 &
  fi
}

# ------------------------------------------------------------ shortcuts ----

IS_WINDOWS=0
case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=1 ;; esac
IS_MAC=0
case "$(uname -s 2>/dev/null)" in Darwin) IS_MAC=1 ;; esac

# Git Bash speaks /c/Users/you; Windows itself needs C:\Users\you in a .lnk,
# and C:/Users/you when the path is an argument to bash.
win_path()     { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }
win_path_fwd() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

start_menu_dir() {
  local appdata="${APPDATA:-}"
  [ -n "$appdata" ] || return 1
  command -v cygpath >/dev/null 2>&1 && appdata="$(cygpath -u "$appdata")"
  printf '%s' "$appdata/Microsoft/Windows/Start Menu/Programs"
}

# One launcher, every platform: start OctoBot if it is not already up, wait
# for the web interface, then open it. This is what every shortcut runs.
write_launcher() {
  local launcher="$BOT_DIR/start-octobot.sh"
  cat > "$launcher" <<EOF
#!/usr/bin/env bash
# Start OctoBot and open its screen. Written by the BitShares wizard.
cd "\$(dirname "\${BASH_SOURCE[0]}")" || exit 1
WEB="$WEB_URL"
CLI="$BOT_CLI"

up() { command -v curl >/dev/null 2>&1 || return 1
       [ "\$(curl -s -o /dev/null -m 4 -w '%{http_code}' "\$WEB" 2>/dev/null)" != "000" ]; }

if ! up; then
  echo "Starting OctoBot..."
  "\$CLI" >/dev/null 2>&1 &
  tries=0
  while [ \$tries -lt 40 ]; do
    sleep 3
    up && break
    tries=\$((tries + 1))
  done
fi

if up; then
  echo "OctoBot is running at \$WEB"
else
  echo "OctoBot did not answer yet. Give it a moment, then open \$WEB"
fi

if command -v xdg-open >/dev/null 2>&1; then xdg-open "\$WEB" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then open "\$WEB" >/dev/null 2>&1 &
elif command -v explorer.exe >/dev/null 2>&1; then explorer.exe "\$WEB" >/dev/null 2>&1 &
fi
EOF
  chmod +x "$launcher" 2>/dev/null
  printf '%s' "$launcher"
}

make_shortcuts() {
  local launcher made=0
  launcher="$(write_launcher)"
  [ -f "$launcher" ] || { warn "Could not write the launcher script."; return 1; }
  say "Launcher: $launcher"

  if [ "$IS_WINDOWS" = 1 ]; then
    local menu bash_exe
    menu="$(start_menu_dir || true)"
    if [ -z "$menu" ] || [ ! -d "$menu" ]; then
      warn "No Start Menu folder found (APPDATA is not set), so no shortcut."
      return 1
    fi
    menu="$menu/BitShares OctoBot"
    mkdir -p "$menu" 2>/dev/null || { warn "Could not write to the Start Menu."; return 1; }

    # An .url is plain text and needs nothing but a shell to write, so the
    # dashboard shortcut always works.
    printf '[InternetShortcut]\r\nURL=%s\r\n' "$WEB_URL" > "$menu/BitShares OctoBot dashboard.url"
    [ -f "$menu/BitShares OctoBot dashboard.url" ] && made=$((made + 1))

    # A .lnk is a binary format, so it needs the helper. Without Python the
    # .url above is still there, it just cannot start OctoBot by itself.
    bash_exe="$(command -v bash 2>/dev/null)"
    if [ -n "$BOT_PY" ] && [ -f "$HERE/tools_mklnk.py" ] && [ -n "$bash_exe" ]; then
      "$BOT_PY" "$HERE/tools_mklnk.py" \
        "$menu/Start BitShares OctoBot.lnk" \
        "$(win_path "$bash_exe")" \
        "-lc \"'$(win_path_fwd "$launcher")'\"" \
        "$(win_path "$BOT_DIR")" \
        "Start OctoBot with the BitShares exchange" >/dev/null 2>&1 \
        && made=$((made + 1))
    fi

    if [ "$made" -gt 0 ]; then
      good "Start Menu: $made shortcut(s) under \"BitShares OctoBot\""
      return 0
    fi
    warn "No Start Menu shortcut could be written."
    return 1
  fi

  if [ "$IS_MAC" = 1 ]; then
    local apps="$HOME/Applications"
    mkdir -p "$apps" 2>/dev/null
    cp "$launcher" "$apps/BitShares OctoBot.command" 2>/dev/null \
      && chmod +x "$apps/BitShares OctoBot.command" 2>/dev/null \
      && { good "Added to $apps as \"BitShares OctoBot.command\""; return 0; }
    warn "Could not add it to $apps."
    return 1
  fi

  local apps="$HOME/.local/share/applications"
  mkdir -p "$apps" 2>/dev/null || { warn "Could not write to $apps."; return 1; }
  cat > "$apps/bitshares-octobot.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=BitShares OctoBot
Comment=Start OctoBot with the BitShares exchange
Exec=$launcher
Path=$BOT_DIR
Terminal=true
Categories=Office;Finance;
EOF
  chmod +x "$apps/bitshares-octobot.desktop" 2>/dev/null
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" >/dev/null 2>&1
  if [ -f "$apps/bitshares-octobot.desktop" ]; then
    good "Applications menu: \"BitShares OctoBot\""
    return 0
  fi
  warn "Could not write the menu entry."
  return 1
}

# ------------------------------------------------------------------ main ----

printf '\n'
printf '  %s\n' "============================================================"
printf '  %s\n' " BitShares for OctoBot"
printf '  %s\n' " Adds the BitShares decentralised exchange to your OctoBot,"
printf '  %s\n' " so NESS, NCH and BTS trade next to your other exchanges."
printf '  %s\n' "============================================================"

if [ ! -d "$TENTACLE_SRC" ]; then
  bad "The BitShares files are missing from this folder."
  say "Expected: $TENTACLE_SRC"
  say "Unzip the whole package, keeping its folders, and run this again."
  pause_at_end; exit 1
fi

# --- 1 -----------------------------------------------------------------------
step 1 "Finding OctoBot"

if [ -n "$BOT_DIR" ]; then
  BOT_DIR="$(cd "$BOT_DIR" 2>/dev/null && pwd)" || { bad "No such folder."; pause_at_end; exit 1; }
  is_octobot_dir "$BOT_DIR" || { bad "$BOT_DIR has no tentacles folder, so it is not an OctoBot install."; pause_at_end; exit 1; }
fi

if [ -z "$BOT_DIR" ]; then
  say "Asking the system which programs are running..."
  BOT_DIR="$(find_running_octobot || true)"
  [ -n "$BOT_DIR" ] && good "Found it from the running process."
fi

if [ -z "$BOT_DIR" ]; then
  for guess in "$HERE" "$(dirname "$HERE")" "$HOME/OctoBot"; do
    if is_octobot_dir "$guess"; then
      BOT_DIR="$(cd "$guess" && pwd)"
      good "Found it at $BOT_DIR"
      break
    fi
  done
fi

if [ -z "$BOT_DIR" ]; then
  say "OctoBot is not running and is not in this folder or in \$HOME/OctoBot."
  say "I do not go searching through the rest of your disk."
  say ""
  typed="$(ask 'Where is it? (Enter to skip and install a fresh copy)' '')"
  if [ -n "$typed" ] && is_octobot_dir "$typed"; then
    BOT_DIR="$(cd "$typed" && pwd)"
  elif [ -n "$typed" ]; then
    warn "$typed has no tentacles folder."
  fi
fi

if [ -z "$BOT_DIR" ] && octobot_is_running; then
  bad "OctoBot is answering on $WEB_URL, so it IS installed, but I could not"
  bad "work out where from. I will not install a second copy on top of it."
  say ""
  typed="$(ask 'Type its folder, or press Enter to stop' '')"
  if [ -n "$typed" ] && is_octobot_dir "$typed"; then
    BOT_DIR="$(cd "$typed" && pwd)"
  else
    say "Stopping. Nothing was changed."
    pause_at_end; exit 1
  fi
fi

if [ -z "$BOT_DIR" ]; then
  say ""
  if ask_yes "Download and install OctoBot now?" "y"; then
    target="${INSTALL_DIR:-$HOME/OctoBot}"
    target="$(ask 'Install it where' "$target")"
    if install_octobot "$target"; then
      BOT_DIR="$(cd "$target" && pwd)"
      good "OctoBot installed in $BOT_DIR"
    else
      bad "OctoBot was not installed."
      say "Get it yourself from https://www.octobot.cloud, run it once, then run this again."
      pause_at_end; exit 1
    fi
  else
    say "Nothing was changed. Run this again once OctoBot is installed."
    pause_at_end; exit 0
  fi
fi

good "OctoBot folder: $BOT_DIR"
BOT_CLI="$(find_cli_for "$BOT_DIR" || true)"
BOT_PY="$(find_python_for "$BOT_DIR" || true)"
[ -n "$BOT_CLI" ] && good "Program:        $BOT_CLI"
[ -n "$BOT_PY" ]  && good "Python:         $BOT_PY"

WAS_RUNNING=0
octobot_is_running && WAS_RUNNING=1

# --- 2 -----------------------------------------------------------------------
step 2 "Checking your OctoBot"
EXCHANGES_DIR="$BOT_DIR/tentacles/Trading/Exchange"
HOW_MANY="$(find "$EXCHANGES_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
if [ "${HOW_MANY:-0}" -lt 5 ]; then
  warn "Only ${HOW_MANY:-0} exchange plug-ins are installed, which is unusually few."
  if [ -n "$BOT_CLI" ] && ask_yes "Download OctoBot's standard plug-ins first?" "y"; then
    ( cd "$BOT_DIR" && "$BOT_CLI" tentacles --install --all ) >/dev/null 2>&1 \
      && good "Standard plug-ins installed." || warn "That did not finish. Carrying on."
  fi
else
  good "$HOW_MANY exchange plug-ins already installed."
fi

# --- 3 -----------------------------------------------------------------------
step 3 "Adding BitShares"
if install_tentacle; then
  good "Installed in $EXCHANGES_DIR/bitshares_dex"
  say "It lives inside your OctoBot folder only. Nothing was installed"
  say "system-wide, and deleting that folder removes it again."
else
  bad "BitShares was not installed."
  pause_at_end; exit 1
fi

if [ -n "$BOT_PY" ]; then
  RESOLVED="$(verify_with_octobot || true)"
  case "$RESOLVED" in
    BitsharesDex) good "OctoBot loads it and uses the BitShares exchange class." ;;
    DefaultRestExchange) warn "OctoBot loads it but falls back to its generic class." ;;
    ERROR*) warn "Could not ask OctoBot: $RESOLVED" ;;
    *) warn "Unexpected answer from OctoBot: $RESOLVED" ;;
  esac
else
  say "No Python here, so I cannot ask OctoBot to confirm before it starts."
  say "The files are in place; OctoBot loads them when it starts."
fi

# --- 4 -----------------------------------------------------------------------
step 4 "Switching it on"
PROFILES=()
while IFS= read -r line; do [ -n "$line" ] && PROFILES+=("$line"); done < <(list_profiles)
if [ "${#PROFILES[@]}" -eq 0 ]; then
  warn "No trading profiles found yet, so there is nothing to switch on."
  say "Start OctoBot, make a profile, then run this again."
elif [ -z "$BOT_PY" ]; then
  warn "No Python here, so I will not edit your settings file by hand."
  say "Switch BitShares on in OctoBot instead: it is one click, see the end."
else
  DEFAULT_PROFILE="arbitrage_trading"
  printf '%s\n' "${PROFILES[@]}" | grep -qx "$DEFAULT_PROFILE" || DEFAULT_PROFILE="${PROFILES[0]}"
  [ -n "$PROFILE_CHOICE" ] && DEFAULT_PROFILE="$PROFILE_CHOICE"
  say "A profile is one trading setup: which exchanges, which pairs, which"
  say "strategy. BitShares is switched on per profile, not for the whole bot."
  say ""
  say "Your profiles: $(printf '%s, ' "${PROFILES[@]}" | sed 's/, $//')"
  CHOSEN="$(ask 'Which one should get BitShares?' "$DEFAULT_PROFILE")"
  printf '%s\n' "${PROFILES[@]}" | grep -qx "$CHOSEN" || {
    warn "No profile called $CHOSEN. Using $DEFAULT_PROFILE."
    CHOSEN="$DEFAULT_PROFILE"
  }
  if RESULT="$(enable_in_profile "$CHOSEN")"; then
    good "Profile $CHOSEN now uses: $RESULT"
    say "A copy of the old settings file is beside it, ending in .bak"
  else
    warn "Could not change that profile. Switch it on in OctoBot instead."
  fi
fi

# --- 5 -----------------------------------------------------------------------
step 5 "Seeing it"
say "OctoBot shows its screens in a web browser, at $WEB_URL"
say ""

if [ "$WAS_RUNNING" = 1 ]; then
  warn "OctoBot was already running when I started. Close it and start it"
  warn "again, or it keeps using the plug-in list it read at startup."
elif [ -n "$BOT_CLI" ] && ask_yes "Start OctoBot now so you can look?" "y"; then
  say "Starting OctoBot. The first start takes a minute."
  ( cd "$BOT_DIR" && "$BOT_CLI" >/dev/null 2>&1 & )
  tries=0
  while [ "$tries" -lt 30 ]; do
    sleep 5
    octobot_is_running && break
    tries=$((tries + 1))
  done
  if octobot_is_running; then
    good "OctoBot is up."
    if command -v curl >/dev/null 2>&1; then
      HITS="$(curl -s -m 20 "$WEB_URL/profile" 2>/dev/null | grep -c -i bitshares || true)"
      if [ "${HITS:-0}" -gt 0 ]; then
        good "BitShares is on the configuration screen. Checked, not assumed."
      else
        warn "The screen loaded but BitShares was not on it."
      fi
    fi
    open_browser "$WEB_URL/profile"
  else
    warn "OctoBot did not answer in time. Start it yourself and look."
  fi
fi

SHORTCUT_OK=0
make_shortcuts && SHORTCUT_OK=1

printf '\n'
printf '  %s%s%s\n' "$C_OK" "############################################################" "$C_OFF"
printf '  %s%s%s\n' "$C_OK" "##                                                        ##" "$C_OFF"
printf '  %s%s%s\n' "$C_OK" "##     B I T S H A R E S   I S   I N S T A L L E D        ##" "$C_OFF"
printf '  %s%s%s\n' "$C_OK" "##                                                        ##" "$C_OFF"
printf '  %s%s%s\n' "$C_OK" "############################################################" "$C_OFF"
say ""
if [ "$SHORTCUT_OK" = 1 ]; then
  if [ "$IS_WINDOWS" = 1 ]; then
    say " From now on:  Start Menu  ->  BitShares OctoBot"
  elif [ "$IS_MAC" = 1 ]; then
    say " From now on:  Applications  ->  BitShares OctoBot"
  else
    say " From now on:  your applications menu  ->  BitShares OctoBot"
  fi
else
  say " To start it:  $BOT_DIR/start-octobot.sh"
fi
say ""
say " Then: Profile -> scroll the exchange cards -> BitShares."
say ""
say " --------------------------------------------------------"
say " WHAT YOU CAN DO NOW"
say " --------------------------------------------------------"
say ""
say " BitShares is a blockchain, not a company. No identity check,"
say " nobody holding your coins, nobody able to freeze you out."
say " Your bot can now read that market and trade it beside the"
say " centralised exchanges it already knows."
say ""
say " Read-only today: prices, order books, candles and trades"
say " come straight off the chain. No account, no key on this"
say " machine, nothing listening on your network. Paper trading"
say " works right now, against real live prices."
say ""
say " Placing real orders needs the signing bridge, which holds"
say " your key. WHAT-YOU-GET.md covers that, and why the account"
say " it uses should hold only what you are willing to lose."
say ""
say " One thing worth knowing before you plan an arbitrage run:"
say " Binance delisted BTS in December 2023. The exchanges that"
say " still carry it are MEXC and Gate, both of which OctoBot"
say " already supports. See WHAT-YOU-GET.md for the volumes."
say ""
pause_at_end
