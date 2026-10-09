#!/usr/bin/env bash
# raven IDS launcher — run detached as root; finch tails eve.json for alerts.
set -e
IDS=/home/a/raven/ids
mkdir -p "$IDS"
GW_IP=$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}')
if [ -n "$GW_IP" ]; then
    SUB=$(echo "$GW_IP" | sed -E 's/\.[0-9]+(\/[0-9]+)$/.0\1/')
    sed -E "s|HOME_NET: \[.*\]|HOME_NET: [\"$SUB\"]|" "$IDS/suricata.yaml" > "$IDS/suricata.live"
    CONFIG="$IDS/suricata.live"
else
    CONFIG="$IDS/suricata.yaml"
fi
suricata -D --af-packet -c "$CONFIG" --pidfile "$IDS/suricata.pid"