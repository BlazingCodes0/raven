# Raven

Raven is a single-file PyQt6 desktop app (`app.py`) for running a **local,
authorized lab** on the machine it lives on: recon/defense tooling, autonomous
"crow" pipelines, and a host **lifeline** that keeps the whole thing alive. It is
built for a teacher's pentest lab. It only ever acts on **THIS host** or the
local segment the operator points it at — it never attacks a remote machine.

## What Raven does

- **Lifeline / second heart** — a `ravenheart.py` supervisor (the "twin") that
  keeps Raven alive, backed by a systemd `--user` `raven-heart` unit
  (`Restart=on-failure`), so Raven cannot easily die or be killed off by accident.
- **SURVIVAL** — a lockdown mode: it seals Raven's core files `chattr +i` and puts
  the second heart on watch. **While SURVIVAL is armed, Raven refuses to shut
  down.** It must be stood down first.
- **ARP guard** (`arpguard.py`) — active, host-local layer-2 defense. It hardens
  kernel knobs (`arp_ignore`, `arp_announce`, `rp_filter`), pins every known-good
  neighbour as PERMANENT, and installs a `RAVENGUARD` drop chain so a forged ARP
  reply cannot poison the gateway or this host. `arpsentry.py` is the read-only
  watcher; the drops act only on frames arriving at our own NIC.
- **systemwatch** — a dormant, read-only host eye (process injection + file
  access via inotify), armed on demand as a `systemwatch.service` user unit.
- **Crows** — autonomous recon / pentest / sniff pipelines that save their
  findings and pcaps under `crow/`.
- **dye / finch / crow / ids** — the network memory, the quarantine/baseline
  state, and the IDS (Suricata) pieces the rest of the house reads.

Everything Raven installs is bounded to this machine: the `RAVENGUARD` drops act
on inbound ARP at our NIC, the neighbour pins are our own cache, and no rule is
ever aimed at another host.

## Shutting Raven down — stand protection down FIRST

Raven refuses an operator shutdown while **SURVIVAL** is armed, so turn the
protection off first, then bring the app down:

1. **Stand SURVIVAL down** — GUI button *SURVIVAL STAND DOWN* (thaws the sealed
   files and dismisses the second heart).
2. **Disarm the ARP guard** —
   `sudo python3 ~/raven/arpguard.py disarm`
   (removes the `RAVENGUARD` rules and releases the neighbour pins).
2. **Stand systemwatch down** — GUI *STAND DOWN*, or
   `systemctl --user stop systemwatch.service`.
3. **Quit Raven** — the app's shutdown stops the second heart, the twin and
   Raven itself.
4. To keep it down across reboots, disable the autostart entry
   `~/.config/autostart/raven.desktop`.

> `arpguard.py disarm` releases the `RAVENGUARD` rules and the neighbour pins but
> leaves the hardened kernel knobs (`arp_ignore=1`, `arp_announce=2`, `rp_filter`)
> in place. Reset those yourself if you want the host back to stock.

## Install

```bash
bash ~/raven/install.sh            # one sudo prompt; scoped grant (recommended)
bash ~/raven/install.sh --full     # raven may run anything as root
bash ~/raven/install.sh --revoke   # take the grant back
```

## Start / restart

```bash
bash ~/raven/raven_boot.sh
```
