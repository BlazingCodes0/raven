#!/bin/bash
# fix_quarantine.sh — install the finch exec-quarantine dedupe/cap patch into raven.
#
# What it does:
#   * stops raven (watchdog -> twin -> gui) so the rewrite is not reverted
#   * unseals the chattr +i files it touches
#   * backs up the current app.py and manifest
#   * installs the patched app.py (live + mirror) and updates the sealed manifest
#   * re-seals the files
#
# Run as:  sudo bash /home/a/raven/fix_quarantine.sh
set -u
[ "$(id -u)" -eq 0 ] || exec sudo bash "$0" "$@"

U=a
UHOME=/home/a
RAV=$UHOME/raven
APP=$RAV/app.py
NEW=$RAV/.app.py.new
MIR=$UHOME/.ravenheart
MIRAPP=$MIR/sync/app.py
MAN=$MIR/manifest.json
STAMP=$(date +%Y%m%d-%H%M%S)

echo "== raven finch quarantine dedupe/cap installer =="
[ -f "$NEW" ] || { echo "FATAL: $NEW missing"; exit 1; }
python3 -m py_compile "$NEW" || { echo "FATAL: patched app.py does not compile"; exit 1; }

UIDA=$(id -u "$U")

echo "[1/6] stopping raven (watchdog -> twin -> gui)"
for i in $(seq 1 15); do
  sudo -u "$U" env XDG_RUNTIME_DIR=/run/user/$UIDA \
    systemctl --user stop raven-heart.service >/dev/null 2>&1 || true
  pkill -9 -u "$U" -f 'ravenheart\.py' >/dev/null 2>&1 || true
  pkill -9 -u "$U" -f '/home/a/raven/app\.py' >/dev/null 2>&1 || true
  sleep 0.4
  pgrep -u "$U" -f 'ravenheart\.py|/home/a/raven/app\.py' >/dev/null 2>&1 || break
done
if pgrep -u "$U" -f 'ravenheart\.py|/home/a/raven/app\.py' >/dev/null 2>&1; then
  echo "FATAL: raven is still running; nothing was changed. Re-run once it stops."
  exit 2
fi

echo "[2/6] unsealing (chattr -i)"
chattr -i "$APP" "$MIRAPP" "$MAN" 2>/dev/null || true

echo "[3/6] backing up current files"
cp -a "$APP" "$RAV/app.py.bak.$STAMP"
[ -f "$MAN" ] && cp -a "$MAN" "$MIR/manifest.json.bak.$STAMP" 2>/dev/null || true

echo "[4/6] installing patched app.py (live + mirror)"
cp -a "$NEW" "$APP"
cp -a "$NEW" "$MIRAPP"
chown "$U:$U" "$APP" "$MIRAPP" 2>/dev/null || true

echo "[5/6] updating sealed manifest hash for app.py"
python3 - "$MAN" "$APP" <<'PY'
import json, sys, hashlib, os
manf, app = sys.argv[1], sys.argv[2]
try:
    man = json.load(open(manf))
except Exception:
    man = {}
man[app] = hashlib.sha256(open(app, "rb").read()).hexdigest()
tmp = manf + ".tmp"
with open(tmp, "w") as f:
    json.dump(man, f)
os.replace(tmp, manf)
print("  manifest[%s] = %s..." % (app, man[app][:16]))
PY

echo "[6/6] re-sealing (chattr +i)"
chattr +i "$APP" "$MIRAPP" "$MAN" 2>/dev/null || true

echo
echo "DONE. raven is stopped and patched."
echo "  old code backup : $RAV/app.py.bak.$STAMP"
echo "  start raven with: /home/a/raven/raven_boot.sh"
