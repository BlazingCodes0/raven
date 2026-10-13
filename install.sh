#!/bin/bash
# ============================================================================
# RAVEN INSTALL — "type your password once, raven takes the wheel"
#
# One `sudo` prompt. In that single elevated run raven:
#   1. installs a sudoers grant (scoped by default, --full for NOPASSWD:ALL)
#   2. installs any missing tools it needs (apt, only if you say yes)
#   3. sets up autostart + user-linger so raven returns after reboot
#   4. re-checks that the grant actually works (sudo -n -l)
# and then hands control back. Everything after is silent sudo -n.
#
# Safety: the sudoers file is validated with `visudo -cf` BEFORE it is moved
# into /etc/sudoers.d/. A bad edit can never brick sudo.
#
# Usage (as a normal user, NOT root):
#   bash ~/raven/install.sh            # scoped grant (recommended)
#   bash ~/raven/install.sh --full     # raven may run anything as root
#   bash ~/raven/install.sh --yes      # install missing deps without asking
#   bash ~/raven/install.sh --revoke   # take the grant back (one password)
# ============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-$USER}"
LOG="$REPO/install.log"
STAGE="${TMPDIR:-/tmp}/raven-install"
FULL="${FULL:-0}"
ASSUME_YES=0
REVOKE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --full)    FULL=1 ;;
    --yes|-y)  ASSUME_YES=1 ;;
    --revoke)  REVOKE=1 ;;
    *) echo "install.sh: unknown option '$1'"; exit 2 ;;
  esac
  shift
done

say()   { printf '\033[1;32m[raven]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[raven]\033[0m WARN: %s\n' "$*"; }
die()   { printf '\033[1;31m[raven]\033[0m FAIL: %s\n' "$*"; exit 1; }
log()   { printf '%s\n' "$*" >> "$LOG"; }
root()  { [ "$(id -u)" -eq 0 ]; }

# ---------------------------------------------------------------------------
log "=== raven install start $(date -u +%FT%TZ) user=$USER_NAME mode=$([ $FULL -eq 1 ] && echo full || echo scoped)"

if root; then
  # ---------------- ELEVATED PHASE (runs inside the single sudo) ----------
  [ -n "${SUDO_USER:-}" ] && USER_NAME="$SUDO_USER"
  say "elevated phase as root for user '$USER_NAME'"

  # 1) sudoers grant
  TARGET="/etc/sudoers.d/raven"
  if [ -f "$TARGET" ] && [ ! -w "$STAGE/$USER_NAME.raven" ]; then
    cp -a "$TARGET" "$STAGE/$USER_NAME.raven.prev" 2>/dev/null || true
    say "existing grant backed up to $STAGE/$USER_NAME.raven.prev"
  fi

  if [ $FULL -eq 1 ]; then
    printf '%s ALL=(ALL:ALL) NOPASSWD: ALL\nDefaults:%s !requiretty\n' "$USER_NAME" "$USER_NAME" > "$STAGE/raven.sudoers"
    say "granting FULL root access (--full)"
  else
    # Scoped grant: every binary the raven agent actually calls via sudo.
    cat > "$STAGE/raven.sudoers" <<EOF
$USER_NAME ALL=(root) NOPASSWD: /usr/sbin/arp-scan, /sbin/ip, /usr/sbin/ip, \\
    /sbin/dhclient, /usr/sbin/dhclient, /sbin/dhcpcd, /usr/sbin/dhcpcd, \\
    /bin/kill, /usr/bin/kill, \\
    /usr/bin/chattr, \\
    /usr/bin/truncate, \\
    /sbin/iptables, /usr/sbin/iptables, \\
    /usr/bin/systemctl, \\
    /usr/sbin/airmon-ng, /usr/sbin/airodump-ng, /usr/sbin/aireplay-ng, \\
    /usr/bin/tshark, /usr/bin/tcpdump, /usr/bin/nmap, \\
    /usr/bin/cat, /usr/bin/cp, \\
    /usr/bin/bash $REPO/ids/run_suricata.sh
Defaults:$USER_NAME !requiretty
EOF
    say "granting SCOPED tools (recon/capture/harden/expel/suricata)"
  fi
  chmod 0640 "$STAGE/raven.sudoers"

  say "validating sudoers syntax..."
  if ! visudo -cf "$STAGE/raven.sudoers" >/dev/null 2>&1; then
    printf 'syntax check of the generated sudoers FAILED. Refusing to install it.\n'
    printf 'Nothing was changed on the system. Checking the draft: %s\n' "$STAGE/raven.sudoers"
    exit 2
  fi
  install -o root -g root -m 0440 "$STAGE/raven.sudoers" "$TARGET"
  say "installed $TARGET (validated, mode 0440)"

  # 2) missing tools
  MISSING=""
  add_missing() { command -v "$1" >/dev/null 2>&1 || MISSING="$MISSING $2"; }
  add_missing arp-scan     arp-scan
  add_missing nmap         nmap
  add_missing tshark       wireshark-common
  add_missing tcpdump      tcpdump
  add_missing airmon-ng    aircrack-ng
  add_missing airodump-ng  aircrack-ng
  add_missing aireplay-ng  aircrack-ng
  add_missing iptables     iptables
  add_missing suricata     suricata
  add_missing chattr       e2fsprogs
  add_missing dhcpcd       dhcpcd5
  if [ -n "$MISSING" ]; then
    if [ $ASSUME_YES -eq 1 ] || [ "$(command -v apt-get)" ]; then
      if [ $ASSUME_YES -eq 0 ]; then
        printf 'Missing packages:%s\nInstall them now with apt? [y/N] ' "$MISSING"
        read -r r && [ "${r,,}" = "y" ] || { warn "skipping apt install (recommend after: apt-get install -y $MISSING)"; MISSING=""; }
      fi
      if [ -n "$MISSING" ]; then
        say "installing:$MISSING"
        apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $MISSING
      fi
    else
      warn "missing tools:$MISSING (no apt here — install them with your package manager)"
    fi
  else
    say "all tools present — nothing to install"
  fi

  # 3) take-over plumbing
  if command -v loginctl >/dev/null 2>&1; then
    loginctl enable-linger "$USER_NAME" 2>/dev/null && say "user-linger enabled (raven survives reboot without a login)"
  fi
  if [ ! -f "/home/$USER_NAME/.config/autostart/raven.desktop" ]; then
    mkdir -p "/home/$USER_NAME/.config/autostart"
    printf '[Desktop Entry]\nType=Application\nName=Raven\nExec=/bin/bash %s/raven_boot.sh\nX-GNOME-Autostart-enabled=true\nComment=Raven security agent (autostart)\n' "$REPO" \
      > "/home/$USER_NAME/.config/autostart/raven.desktop"
    chown "$USER_NAME":"$USER_NAME" "/home/$USER_NAME/.config/autostart/raven.desktop"
    say "autostart installed (raven returns next login)"
  fi

  # 4) confirm the grant works
  if sudo -u "$USER_NAME" sudo -n true >/dev/null 2>&1; then
    say "passwordless sudo VERIFIED for $USER_NAME"
  elif sudo -u "$USER_NAME" sh -c "sudo -n -l | grep -qi 'raven'" ; then
    say "grant present (NOPASSWD tools verified: $(sudo -u "$USER_NAME" sudo -n -l | grep -c NOPASSWD) rule blocks)"
  else
    warn "could not self-verify the grant — check: sudo -n -l"
  fi

  say "elevated phase complete."
  exit 0
fi

# ---------------- NORMAL USER PHASE ---------------------------------------
say "RAVEN INSTALL — this is the security agent for $USER_NAME"
say "one password, full take-over. Everything runs from here."

# 0) revoke mode
if [ $REVOKE -eq 1 ]; then
  say "revoking the raven sudoers grant (you will be asked for the password once)..."
  sudo -n -v 2>/dev/null || sudo -v || true
  sudo -n rm -f /etc/sudoers.d/raven && say "grant removed. raven is back to password-required." || die "could not revoke"
  exit 0
fi

# 1) are we even allowed to sudo?
if ! id -nG | grep -qw sudo; then
  die "your account is not in the 'sudo' group. As root run: usermod -aG sudo $USER_NAME; then re-login and rerun this installer."
fi

# 2) preflight staging (no elevation yet)
rm -rf "$STAGE"; mkdir -p "$STAGE"
[ -f /etc/sudoers.d/raven ] && cp -a /etc/sudoers.d/raven "$STAGE/$USER_NAME.raven.prev" 2>/dev/null || true
say "preflight done. Here's the plan:"
[ $FULL -eq 1 ] && say "  - grant: raven = FULL root (NOPASSWD: ALL)"
[ $FULL -ne 1 ] && say "  - grant: raven = scoped tools (recon, capture, harden, expel, suricata)"
say "  - deps:  only missing tools, if you allow apt"
say "  - boot:  autostart + user-linger so it survives reboot"
printf '\nContinue? Type the password when sudo asks (once). [Enter to continue, Ctrl-C to abort] '
read -r _

# 3) THE ONE password prompt; everything elevated runs inside it.
sudo -n -v 2>/dev/null || sudo -v || die "sudo rejected the password"
sudo bash "$0" $([ $FULL -eq 1 ] && echo --full) $([ $ASSUME_YES -eq 1 ] && echo --yes)

# 4) wrap-up (no elevation needed)
say ""
say "=== raven is in control ==="
printf 'grant summary (passwordless):\n'
sudo -n -l 2>/dev/null | grep -i -A40 'user '"$USER_NAME" || true
say "revoke any time:  bash $REPO/install.sh --revoke"
printf '\nLaunch raven now? [Y/n] '
read -r r
if [ "${r,,}" != "n" ]; then
  bash "$REPO/raven_boot.sh" && say "raven is up. GUI + lifeline twin running."
fi
exit 0
# 5) create user launchers (Desktop + Applications)
if [ "$(id -u)" -ne 0 ]; then
  SHARE="$HOME/.local/share/applications"
  DESK="$HOME/Desktop"
  mkdir -p "$SHARE" "$DESK"
  cat > "$SHARE/Raven.desktop" <<EOD
[Desktop Entry]
Version=1.0
Type=Application
Name=Raven
Comment=Raven Lab (supervised with lifeline)
Exec=$REPO/raven_boot.sh
Icon=$REPO/assets/raven_neon.png
Terminal=false
Categories=Finance;Utility;
EOD
  cp -f "$SHARE/Raven.desktop" "$DESK/Raven.desktop" 2>/dev/null || true
  chmod +x "$SHARE/Raven.desktop" "$DESK/Raven.desktop" 2>/dev/null || true
  chmod +x "$REPO/raven_boot.sh" 2>/dev/null || true
  say "launchers installed: $DESK/Raven.desktop and $SHARE/Raven.desktop"
fi
