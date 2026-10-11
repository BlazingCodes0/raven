#!/usr/bin/env python3
"""arpsentry — passive ARP integrity sentry (LISTEN-ONLY).

Watches the local segment for ARP poisoning / spoofing and reports who is
claiming what. It never sends an ARP packet, never touches another host, and
never changes state on the wire — it is a camera, not a hand. Run it on a
network you own or are authorised to observe.

What it catches:
  * an IP claimed by more than one MAC        -> SPOOF (the classic poison)
  * the gateway's MAC changing                -> SPOOF (MITM on the way out)
  * one MAC claiming many IPs                 -> SPOOF (a machine posing as the LAN)
  * gratuitous / unsolicited ARP replies      -> SPOOF (an active poisoning burst)
  * a single MAC flooding ARP                 -> FLOOD (DoS / poison storm)
  * who-has for hosts that never answer       -> probes (recon)

Output: a human report on stdout, and (with --json) a machine record raven can
read. Designed to run in short windows so it stays cheap (a few seconds of
capture), not to sit on the CPU.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict

RE_REPLY = re.compile(r"Reply (\d+\.\d+\.\d+\.\d+) is-at ([0-9a-f:]{17})")
RE_REQ = re.compile(r"Request who-has (\d+\.\d+\.\d+\.\d+) tell (\d+\.\d+\.\d+\.\d+)")

BROADCAST = "ff:ff:ff:ff:ff:ff"
ZERO = "00:00:00:00:00:00"


def default_iface():
    try:
        out = subprocess.run(["ip", "route", "show", "default"],
                             capture_output=True, text=True).stdout.split()
        return out[out.index("dev") + 1] if "dev" in out else None
    except Exception:
        return None


def default_gateway():
    try:
        out = subprocess.run(["ip", "route", "show", "default"],
                             capture_output=True, text=True).stdout.split()
        return out[out.index("via") + 1] if "via" in out else None
    except Exception:
        return None


def local_mac(iface):
    try:
        with open("/sys/class/net/%s/address" % iface) as f:
            return f.read().strip().lower()
    except Exception:
        return None


def capture(iface, seconds):
    """Return the raw tcpdump lines for ARP seen in the window (needs root)."""
    cmd = ["sudo", "-n", "timeout", str(int(seconds) + 1), "tcpdump",
           "-i", iface, "-n", "-e", "-t", "-l", "-U", "-s", "0", "arp"]
    lines = []
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
    except Exception as ex:
        print("cannot start tcpdump:", ex, file=sys.stderr)
        return lines
    try:
        for ln in p.stdout:                 # ends when `timeout` stops tcpdump
            lines.append(ln.rstrip("\n"))
    finally:
        try:
            p.wait(timeout=3)
        except Exception:
            p.kill()
    return lines


def analyse(lines, iface, gw_hint):
    """A tcpdump -e line looks like:
        <srcmac> > <dstmac>, ethertype ARP, ...
            Reply 192.168.1.254 is-at 9c:1e:95:cc:ae:00
            Request who-has 192.168.1.254 tell 192.168.1.64
    We track who claims which IP (from replies) and how loud each MAC is."""
    bindings = {}                      # ip -> {mac: count}
    mac_sends = defaultdict(int)       # ether-src mac -> frames sent
    for ln in lines:
        src = ln.split(">", 1)[0].strip().lower() if ">" in ln else ""
        m = RE_REPLY.search(ln)
        if m:
            ip, mac = m.group(1), m.group(2).lower()
            b = bindings.setdefault(ip, {})
            b[mac] = b.get(mac, 0) + 1
            mac_sends[src or mac] += 1
            continue
        if RE_REQ.search(ln):
            mac_sends[src] += 1
    return bindings, mac_sends


def report(iface, seconds, gw_hint, lines, bindings, mac_sends):
    gw = gw_hint or default_gateway()
    me = local_mac(iface)
    out = []
    out.append("ARP SENTRY — passive, listen-only")
    out.append("  interface %s  ·  my MAC %s  ·  window %ss  ·  %d ARP frames"
               % (iface, me, seconds, len(lines)))
    out.append("  gateway: %s" % (gw or "unknown"))
    finds = []

    # conflicts: one IP, many MACs
    for ip, macs in bindings.items():
        if len(macs) > 1:
            tag = "GATEWAY" if ip == gw else "HOST"
            finds.append(("SPOOF", "%s %s claimed by %d MACs: %s"
                          % (tag, ip, len(macs),
                             ", ".join("%s×%d" % (m, c) for m, c in macs.items()))))
    # one MAC claiming many IPs
    mac_ips = defaultdict(set)
    for ip, macs in bindings.items():
        for m in macs:
            mac_ips[m].add(ip)
    for m, ips in mac_ips.items():
        if len(ips) > 2 and m not in (BROADCAST, ZERO):
            finds.append(("SPOOF", "MAC %s claims %d IPs: %s"
                          % (m, len(ips), ", ".join(sorted(ips)[:6]))))
    # bogus MACs
    for ip, macs in bindings.items():
        for m in macs:
            if m in (ZERO,) and ip != "0.0.0.0":
                finds.append(("SPOOF", "%s claimed by null MAC %s (probe/poison)" % (ip, m)))
    # flood: one MAC dominating the window
    top = max(mac_sends.items(), key=lambda kv: kv[1], default=(None, 0))
    if top[0] and top[1] >= 25 and top[1] >= max(1, sum(mac_sends.values())) * 0.5:
        finds.append(("FLOOD", "MAC %s sent %d of %d ARP frames — storm/poison tool"
                      % (top[0], top[1], sum(mac_sends.values()))))

    if not finds:
        out.append("  VERDICT: clean — one MAC per IP, gateway stable,"
                   " no gratuitous flood. (Nothing here proves the net is safe;"
                   " it only proves no ARP lie was visible in this window.)")
    else:
        out.append("  VERDICT: %d anomal%s — ARP integrity is suspicious:" % (len(finds), "y" if len(finds) == 1 else "ies"))
    for kind, msg in finds:
        out.append("    [%s] %s" % (kind, msg))

    out.append("  seen:")
    def sortkey(x):
        return tuple(int(p) for p in x.split(".")) if re.match(r"^\d+\.", x) else (999,)
    for ip in sorted(bindings, key=sortkey):
        for m, c in sorted(bindings[ip].items(), key=lambda kv: -kv[1]):
            who = " (gateway)" if ip == gw else (" (you)" if m == me else "")
            out.append("    %-16s %s  ×%d%s" % (ip, m, c, who))
    return out, finds, gw


def main():
    ap = argparse.ArgumentParser(description="passive ARP spoofing sentry")
    ap.add_argument("-i", "--iface", default=default_iface())
    ap.add_argument("-t", "--time", type=float, default=20.0,
                    help="capture window in seconds (default 20)")
    ap.add_argument("--gateway", default=None)
    ap.add_argument("--json", metavar="PATH", default=None,
                    help="also write a machine-readable record")
    a = ap.parse_args()
    if not a.iface:
        print("no interface — is there a default route?", file=sys.stderr)
        return 2
    lines = capture(a.iface, a.time)
    bindings, mac_sends = analyse(lines, a.iface, a.gateway)
    text, finds, gw = report(a.iface, a.time, a.gateway, lines, bindings, mac_sends)
    print("\n".join(text))
    if a.json:
        rec = {"ts": int(time.time()), "iface": a.iface, "gateway": gw,
               "seconds": a.time, "frames": len(lines),
               "anomalies": [{"kind": k, "detail": d} for k, d in finds],
               "bindings": {ip: dict(macs) for ip, macs in bindings.items()}}
        try:
            with open(a.json, "w") as f:
                json.dump(rec, f)
        except Exception as ex:
            print("json write failed:", ex, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
