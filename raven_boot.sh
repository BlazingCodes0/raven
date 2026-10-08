#!/bin/sh
# Starts Raven's GUI + its lifeline twin, detached and quiet.
# Used by ~/.config/autostart/raven.desktop (autostart on login) and for manual
# restarts. The twin (ravenheart.py, its own process) auto-resurrects all of it.
setsid nohup python3 /home/a/raven/app.py > /tmp/opencode/raven.log 2>&1 < /dev/null &