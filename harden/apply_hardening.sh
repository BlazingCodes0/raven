#!/usr/bin/env bash
# raven confinement — AppArmor profile (complain mode: observes, does not block).
# To ENFORCE later: sudo sed -i 's/flags=(complain)/flags=(enforce)/' \
#                         /etc/apparmor.d/raven && sudo apparmor_parser -r /etc/apparmor.d/raven
set -e
SRC=/home/a/raven/harden/apparmor-raven
DST=/etc/apparmor.d/raven
sudo cp "$SRC" "$DST"
sudo apparmor_parser -r "$DST"
echo "raven apparmor profile loaded in COMPLAIN mode (audit-only)."
echo "Watch /var/log/audit/audit.log or 'dmesg | grep apparmor' for denied ops."