#!/usr/bin/env python3
"""arpguard — active, host-local ARP integrity defense (layer 2).

Where `arpsentry` only *watches*, arpguard holds the line on THIS machine:

  * kernel knobs    — arp_ignore=1, arp_announce=2, rp_filter=1 (all/default/dev)
  * static pinning  — the gateway (and every known-good neighbour) is written as
                      a PERMANENT neighbour entry, so the kernel will not re-learn
                      a poisoned MAC from a forged ARP reply
  * arptables drop  — a RAVENGUARD chain in the filter table drops ARP replies
                      that claim the gateway's (or our own) IP from a MAC that
                      does not own it — plus a per-attacker block added the moment
                      a bite fires

Everything runs through `sudo -n` (passwordless on this host). It is bounded to
this machine: it never *sends* an ARP packet and never touches another host —
the drops act on frames arriving at our own NIC, the pins are our own cache.
`disarm` removes the rules and releases the pins.
"""
import argparse
import json
import re
import subprocess
import sys

CHAIN = "RAVENGUARD"
KNOBS = {"arp_ignore": "1", "arp_announce": "2", "rp_filter": "1"}


# ── process helpers ─────────────────────────────────────────────────────────
def _run(argv, timeout=6):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def _sudo(*args):
    return _run(["sudo", "-n", *args])


def _ok(r):
    return bool(r and r.returncode == 0)


# ── discovery ───────────────────────────────────────────────────────────────
def default_iface():
    r = _run(["ip", "route", "show", "default"])
    if r and r.stdout:
        w = r.stdout.split()
        if "dev" in w:
            return w[w.index("dev") + 1]
    return None


def default_gateway():
    r = _run(["ip", "route", "show", "default"])
    if r and r.stdout:
        w = r.stdout.split()
        if "via" in w:
            return w[w.index("via") + 1]
    return None


def iface_mac(iface):
    try:
        with open("/sys/class/net/%s/address" % iface) as f:
            return f.read().strip().lower()
    except Exception:
        return None


def iface_ip(iface):
    r = _run(["ip", "-4", "addr", "show", "dev", iface])
    if r and r.stdout:
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", r.stdout)
        if m:
            return m.group(1)
    return None


def neighbors(iface=None):
    argv = ["ip", "neigh", "show"]
    if iface:
        argv += ["dev", iface]
    r = _run(argv)
    pairs = {}
    if r and r.stdout:
        for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)(?: +dev +\S+)? +lladdr +([\da-fA-F:]{17})",
                             r.stdout):
            pairs[m.group(1)] = m.group(2).lower()
    return pairs


# ── kernel knobs ────────────────────────────────────────────────────────────
def sysctl_harden(iface=None):
    """Set the hardened knobs on all/default/<iface>. Returns what changed."""
    changed = []
    for scope in ["all", "default"] + ([iface] if iface else []):
        for k, v in KNOBS.items():
            path = "net.ipv4.conf.%s.%s" % (scope, k)
            cur = _run(["sysctl", "-n", path])
            if cur and cur.stdout.strip() == v:
                continue
            if _ok(_sudo("sysctl", "-w", "%s=%s" % (path, v))):
                changed.append(path)
    return changed


# ── static pinning ──────────────────────────────────────────────────────────
def pin(ip, mac, iface, state="permanent"):
    """Write a neighbour entry and hold it (default PERMANENT — no relearn)."""
    return _ok(_sudo("ip", "neigh", "replace", ip, "lladdr", mac,
                     "dev", iface, "nud", state))


def unpin(ip, iface):
    """Release a pin back to the kernel's own ARP."""
    if _ok(_sudo("ip", "neigh", "change", ip, "dev", iface, "nud", "reachable")):
        return True
    return _ok(_sudo("ip", "neigh", "del", ip, "dev", iface))


def pinned(iface=None):
    argv = ["ip", "neigh", "show"]
    if iface:
        argv += ["dev", iface]
    r = _run(argv)
    out = {}
    if r and r.stdout:
        for line in r.stdout.splitlines():
            m = re.match(r"(\d+\.\d+\.\d+\.\d+).*?lladdr ([\da-f:]{17}).*(PERMANENT|NOARP)",
                         line, re.I)
            if m:
                out[m.group(1)] = m.group(2).lower()
    return out


# ── arptables ───────────────────────────────────────────────────────────────
def _arpt(*args):
    return _sudo("arptables", *args)


def _ensure_chain():
    """Create the chain and hook it into INPUT once (idempotent)."""
    _arpt("-N", CHAIN)                       # fails harmlessly if it exists
    h = _arpt("-S", "INPUT")
    if not (h and h.stdout and CHAIN in h.stdout):
        _arpt("-I", "INPUT", "1", "-j", CHAIN)


def _drop(iface, ip, mac):
    """DROP ARP replies claiming `ip` from a MAC other than `mac`."""
    if not (iface and ip and mac):
        return False
    return _ok(_arpt("-A", CHAIN, "-i", iface, "--opcode", "Reply",
                     "--source-ip", ip, "!", "--source-mac", mac,
                     "-j", "DROP"))


def install(iface=None, anchors=None):
    """Rebuild RAVENGUARD from scratch and hook it: gateway + self + anchors.

    `anchors` is an ip->mac map of every known-good neighbour we will defend.
    Returns the number of drop rules installed.
    """
    iface = iface or default_iface()
    if not iface:
        return 0
    gw_ip = default_gateway()
    my_ip = iface_ip(iface)
    anchors = dict(anchors or {})
    if gw_ip and gw_ip in anchors:
        gw_mac = anchors[gw_ip]
    else:
        gw_mac = neighbors(iface).get(gw_ip) if gw_ip else None
        if gw_ip and gw_mac:
            anchors[gw_ip] = gw_mac
    my_mac = iface_mac(iface)

    _ensure_chain()
    _arpt("-F", CHAIN)                       # rebuild so it is always idempotent
    n = 0
    if gw_ip and gw_mac:
        n += _drop(iface, gw_ip, gw_mac)
    if my_ip and my_mac:
        n += _drop(iface, my_ip, my_mac)
    for ip, mac in anchors.items():
        if ip in (gw_ip, my_ip):
            continue
        n += _drop(iface, ip, mac)
    return n


def block(iface, ip, mac):
    """Block one specific liar (replies for `ip` from `mac`) — keeps chain hooked."""
    if not (iface and ip and mac):
        return False
    _ensure_chain()
    return _ok(_arpt("-A", CHAIN, "-i", iface, "--opcode", "Reply",
                     "--source-ip", ip, "--source-mac", mac, "-j", "DROP"))


def _rules_remove():
    _arpt("-D", "INPUT", "-j", CHAIN)
    _arpt("-F", CHAIN)
    _arpt("-X", CHAIN)


# ── top-level verbs ─────────────────────────────────────────────────────────
def arm(extra=None):
    """Harden the kernel, pin the known-good map, install the drops."""
    iface = default_iface()
    rep = {"iface": iface, "gateway": default_gateway(),
           "my_ip": iface_ip(iface) if iface else None,
           "my_mac": iface_mac(iface) if iface else None,
           "changed_knobs": [], "pinned": {}, "rules": 0, "errors": []}
    if not iface:
        rep["errors"].append("no default interface")
        return rep
    rep["changed_knobs"] = sysctl_harden(iface)
    anchors = dict(neighbors(iface))
    if extra:
        anchors.update(extra)
    anchors.pop(rep["my_ip"], None)
    for ip, mac in anchors.items():
        if pin(ip, mac, iface):
            rep["pinned"][ip] = mac
    rep["rules"] = install(iface, anchors=anchors)
    return rep


def disarm():
    iface = default_iface()
    _rules_remove()
    released = 0
    for ip in list(pinned(iface).keys()):
        if unpin(ip, iface):
            released += 1
    return {"released": released}


def status():
    iface = default_iface()
    s = _arpt("-S", CHAIN)
    rules = [l for l in (s.stdout or "").splitlines() if l.startswith("-A")] if s else []
    h = _arpt("-S", "INPUT")
    return {"iface": iface, "gateway": default_gateway(), "chain": CHAIN,
            "hooked": bool(h and h.stdout and CHAIN in h.stdout),
            "rules": rules, "pinned": pinned(iface)}


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="active host-local ARP integrity defense")
    ap.add_argument("action",
                    choices=["arm", "disarm", "status", "install", "pin",
                             "unpin", "block", "sysctl"])
    ap.add_argument("args", nargs="*", help="pin: IP MAC · unpin: IP · block: IP MAC")
    ap.add_argument("--json", metavar="PATH", default=None)
    a = ap.parse_args()

    if a.action == "arm":
        rep = arm()
    elif a.action == "disarm":
        rep = disarm()
    elif a.action == "sysctl":
        rep = {"changed": sysctl_harden(default_iface())}
    elif a.action == "install":
        rep = {"iface": default_iface(), "rules": install(), "pinned": pinned()}
    elif a.action == "pin":
        if len(a.args) < 2:
            ap.error("pin needs IP MAC")
        rep = {"pin": pin(a.args[0], a.args[1].lower(), default_iface())}
    elif a.action == "unpin":
        if len(a.args) < 1:
            ap.error("unpin needs IP")
        rep = {"unpin": unpin(a.args[0], default_iface())}
    elif a.action == "block":
        if len(a.args) < 2:
            ap.error("block needs IP MAC")
        rep = {"block": block(default_iface(), a.args[0], a.args[1].lower())}
    else:
        rep = status()

    print(json.dumps(rep, indent=2))
    if a.json:
        try:
            with open(a.json, "w") as f:
                json.dump(rep, f, indent=1)
        except Exception as ex:
            print("json write failed:", ex, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
