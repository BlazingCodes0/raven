#!/usr/bin/env python3
# ravenheart — the unconscious twin + big brother. one job: this host never loses its link,
# and nobody — student or tool — gets to watch its screen, gut its tools, or rewrite its files.
# a separate process on purpose: if the Raven GUI dies, this keeps beating anyway.
import hashlib, json, os, shlex, socket, subprocess, sys, time

RUNTIME = "/tmp/ravenheart"
STATE = RUNTIME + "/state.json"
LEDGER = RUNTIME + "/events.log"
CONTROL = RUNTIME + "/control.json"
PIDF = RUNTIME + "/twin.pid"

BEAT = 2.0


def shout(cmd, timeout=7):
    try:
        return subprocess.run(cmd, shell=True, timeout=timeout, text=True,
                              capture_output=True).stdout.strip()
    except Exception:
        return ""


def ev(tag, msg):
    try:
        with open(LEDGER, "a") as f:
            f.write("[%s] %s: %s\n" % (time.strftime("%H:%M:%S"), tag, msg))
    except Exception:
        pass


def beat_state(**kw):
    st = {"t": time.strftime("%H:%M:%S"), "ts": int(time.time())}
    st.update(kw)
    tmp = STATE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, STATE)
    except Exception:
        pass


def ctl():
    base = {"auto": True, "guard": True, "aggressive": True, "opencode": True, "threshold": 2}
    try:
        with open(CONTROL) as f:
            base.update(json.load(f))
    except Exception:
        pass
    return base


def route():
    out = shout("ip route show default").split()
    dev = gw = None
    if "dev" in out:
        dev = out[out.index("dev") + 1]
    if "via" in out:
        gw = out[out.index("via") + 1]
    return dev, gw


def tcp_ok(host, port=443, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def online():
    # "online" means a real bearer is carrying traffic, not merely 'associated'
    for host in ("1.1.1.1", "8.8.8.8"):
        for port in (443, 53):
            if tcp_ok(host, port, 2):
                return True
    return False


def rtt_ms(host="1.1.1.1"):
    out = shout("ping -q -c 1 -W 2 %s" % shlex.quote(host))
    try:
        return round(float(out.split("= ")[-1].split("/")[0]), 1)
    except Exception:
        return None


def wifi_profile():
    for line in shout("nmcli -t -f NAME,TYPE connection show").splitlines():
        parts = line.split(":")
        if len(parts) == 2 and parts[1].startswith("802-11-wireless"):
            return parts[0]
    return None


def dhcp_renew(dev):
    shout("sudo -n ip link set %s mtu 1500 2>/dev/null" % dev)
    shout("sudo -n dhclient -v -r %s 2>/dev/null; sleep 2; sudo -n dhclient -v %s 2>/dev/null" % (dev, dev))


def heal(dev, strikes):
    shout("iw dev %s set power_save off 2>/dev/null" % dev)
    prof = wifi_profile()
    if strikes == 1:
        ev("WATCH", "missed a beat — rescanning; power-save held off on %s" % dev)
        shout("nmcli device wifi rescan ifname %s 2>/dev/null" % dev)
    elif strikes == 2:
        if prof:
            ev("HEAL", "re-associating saved wifi profile: %s" % prof)
            shout("nmcli device wifi connect %s ifname %s 2>/dev/null" % (shlex.quote(prof), dev))
        else:
            ev("HEAL", "no saved wifi profile — DHCP renew on %s" % dev)
            dhcp_renew(dev)
    elif strikes == 3:
        ev("HEAL", "nmcli reapply on %s" % dev)
        shout("nmcli device reapply %s 2>/dev/null" % dev)
    else:
        ev("HEAL", "hard bounce of %s + DHCP, repeated until it answers" % dev)
        shout("sudo -n ip link set %s down 2>/dev/null; sleep 3; sudo -n ip link set %s up 2>/dev/null" % (dev, dev))
        shout("nmcli device reapply %s 2>/dev/null" % dev)
        if prof:
            shout("nmcli device wifi connect %s ifname %s 2>/dev/null" % (shlex.quote(prof), dev))
        dhcp_renew(dev)
    for alt in shout("ls /sys/class/net").split():
        if alt in ("lo", dev) or not alt.startswith(("wl", "en", "eth")):
            continue
        if shout("cat /sys/class/net/%s/carrier 2>/dev/null" % alt) == "1":
            ev("HEAL", "failover: attaching to %s" % alt)
            shout("nmcli device set %s autoconnect yes 2>/dev/null" % alt)
            shout("nmcli device connect %s 2>/dev/null" % alt)


# ── BIG BROTHER: the unconscious guard ──────────────────────────────────────
# Expel-class = a hand watching this machine (screen capture, keylogs, reverse
# shells, remote pokes). Watch-class = tools that could be used for it; alert
# first, and only expel if they linger while AGGRESSIVE is on.
# ALLOW must be precise — a loose token like "opencode" would whitelist any
# payload path that contains the word. Match on exact binaries/paths instead.
ALLOW = ("raven/app.py", "ravenheart.py", "/.opencode/bin/opencode",
         "opencode serve", "opencode web", "opencode tui", "Xorg", "Xwayland",
         "kwin_wayland", "plasmashell", "pulseaudio", "pipewire", "systemd",
         "NetworkManager", "avahi-daemon", "sshd", "dbus-daemon", "polkitd",
         "chronyd", "timesyncd", "udisksd", "systemd-logind", "accounts-daemon")

EXPELLED = (
    "xwd ", " scrot ", "maim ", " grim ", "grimscape", "flameshot", "spectacle",
    "import -window", "import -screen", "x11vnc", "vncserver", "xvnc", "vino",
    " krfb", "x11grab", "/dev/fb0", "/dev/input/", "keylogger", "pyautogui",
    " bash -i", " sh -i", "/dev/tcp/", " -e /bin/bash", "nc -e", "ncat -e",
    " nc -lvp", "ncat -lvp", "nc -l -p", " socat", " chisel", "meterpreter",
    "msfconsole", "strace -p", "gdb -p", "pspy", "reveal", "socat ",
)

WATCHED = (
    "xdotool", "convert ", "magick ", "binwalk", "foremost", "exiftool",
    "steghide", "pngcheck", "tesseract", "xxd ", " lsof", " inotifywait",
    "tcpdump -r", "capinfos", "wireshark", "tshark -r",
)

CORE_FILES = [
    "/home/a/raven/app.py",
    "/home/a/raven/ravenheart.py",
    "/home/a/raven/SNAPSHOT.md",
]
LATCH_FILES = [  # rewritten => restored from backup (ssh keys are the crown jewels)
    "~/.ssh/authorized_keys",
]
SUSPECT_FILES = [  # rewritten => loud alert, left alone unless AGGRESSIVE
    "~/.bashrc", "~/.zshrc", "~/.profile", "~/.config/opencode/config.json",
    "~/.config/opencode/opencode.json", "~/.config/opencode/opencode.jsonc",
]
WATCH_DIRS = ["~/.config/autostart", "~/.config/opencode", "/etc/systemd/system"]

OFF = {}
INTEGRITY = {}
ACTS = 0
LAST_ACT = ""
LAST_TIMES = {"mom": 0, "oc": 0, "sync": 0}
SAFE_BINS = ("/usr/bin/", "/bin/", "/usr/sbin/", "/sbin/")
SYNC_DIR = RUNTIME + "/sync"
LAIR = RUNTIME + "/lair"


def pscan():
    procs = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        base = "/proc/" + d
        try:
            with open(base + "/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            uid = "?"
            try:
                with open(base + "/status") as f:
                    for ln in f:
                        if ln.startswith("Uid:"):
                            uid = ln.split()[1]
                            break
            except Exception:
                pass
            procs[int(d)] = {"cmd": cmd, "uid": uid}
        except Exception:
            continue
    return procs


def kill_proc(pid, uid):
    try:
        os.kill(pid, 9)
        return True
    except ProcessLookupError:
        return True
    except PermissionError:
        return subprocess.run(["sudo", "-n", "kill", "-9", str(pid)],
                              capture_output=True).returncode == 0


def cripple(cmd):
    # lift the malicious kit file(s): take the first non-system path token in
    # the command line (the executable may be the shell; the kit is an arg)
    try:
        toks = shlex.split(cmd)
    except Exception:
        toks = cmd.split()
    hit = ""
    for t in toks:
        if t.startswith("/") and not t.startswith(SAFE_BINS) and os.path.exists(t):
            hit = t
            break
    if hit:
        try:
            os.makedirs(LAIR, exist_ok=True)
            target = os.path.join(LAIR, "%s_%d" % (os.path.basename(hit), int(time.time())))
            os.rename(hit, target)
            os.chmod(target, 0)
            return " (binary lifted to lair: %s)" % os.path.basename(hit)
        except Exception:
            return " (could not lift binary)"
    return ""

def handle(pid, cmd, cls, tok, uid):
    global ACTS, LAST_ACT
    c = ctl()
    if not c.get("guard", True):
        return
    for a in ALLOW:
        if a in cmd:
            return
    OFF[pid] = OFF.get(pid, 0) + 1
    hits = OFF[pid]
    if cls == "EXPEL" and hits >= c.get("threshold", 2):
        killed = kill_proc(pid, uid)
        note = cripple(cmd)
        ACTS += 1
        LAST_ACT = "removed PID %d (%s)%s" % (pid, cmd[:50], note)
        ev("EXPEL", "GOT ONE — PID %d uid %s [%s]%s %s"
           % (pid, uid, cmd[:90], note, "killed" if killed else "kill failed"))
    elif cls == "WATCH":
        if hits <= 3:
            ev("WATCH", "PID %d uid %s fingering: %s" % (pid, uid, cmd[:90]))
        if c.get("aggressive") and hits >= 8:
            killed = kill_proc(pid, uid)
            note = cripple(cmd)
            ACTS += 1
            LAST_ACT = "removed lingering watcher PID %d%s" % (pid, note)
            ev("EXPEL", "persistent watcher PID %d uid %s [%s]%s removed"
               % (pid, uid, cmd[:90], note))


def checksum(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def dir_snap(d):
    snap = {}
    try:
        for ent in sorted(os.listdir(d)):
            p = os.path.join(d, ent)
            if os.path.isfile(p):
                st = os.stat(p)
                snap[ent] = (int(st.st_mtime_ns), int(st.st_size))
            else:
                snap[ent] = None
    except Exception:
        return {}
    return snap


def backup(path):
    b = os.path.basename(path)
    try:
        with open(path, "rb") as f:
            with open(os.path.join(SYNC_DIR, b), "wb") as g:
                g.write(f.read())
    except Exception:
        pass


def integrity_boot():
    os.makedirs(SYNC_DIR, exist_ok=True)
    os.makedirs(LAIR, exist_ok=True)
    for p in CORE_FILES + LATCH_FILES + SUSPECT_FILES:
        p = os.path.expanduser(p)
        backup(p)
        INTEGRITY[p] = checksum(p)
    for d in WATCH_DIRS:
        INTEGRITY[d] = dir_snap(os.path.expanduser(d))


def integrity_scan():
    if time.time() - LAST_TIMES["sync"] > 3600:  # hourly re-backup of the good copies
        LAST_TIMES["sync"] = time.time()
        for p in CORE_FILES + LATCH_FILES:
            backup(os.path.expanduser(p))
    for p in CORE_FILES + LATCH_FILES:
        p = os.path.expanduser(p)
        cur = checksum(p)
        base = INTEGRITY.get(p)
        if cur is None:
            continue
        if base and cur != base:
            b = os.path.basename(p)
            try:
                with open(os.path.join(SYNC_DIR, b), "rb") as g:
                    data = g.read()
                with open(p, "wb") as f:
                    f.write(data)
                INTEGRITY[p] = checksum(p)
                ev("EXPEL", "hand rewrote %s — restored from the twin's copy" % p)
            except Exception as ex:
                ev("ALERT", "tampered %s and restore failed: %r" % (p, ex))
        else:
            INTEGRITY.setdefault(p, cur)
    for p in SUSPECT_FILES:
        p = os.path.expanduser(p)
        cur = checksum(p)
        base = INTEGRITY.get(p)
        if base and cur != base:
            ev("WATCH", "someone rewrote %s (not restored — operator owns their dotfiles)" % p)
            INTEGRITY[p] = cur or base
        elif cur:
            INTEGRITY.setdefault(p, cur)
    for d in WATCH_DIRS:
        d = os.path.expanduser(d)
        snap = dir_snap(d)
        if INTEGRITY.get(d) is not None and snap != INTEGRITY[d]:
            diff = sorted(set(snap) - set(INTEGRITY[d]))[:4]
            ev("WATCH", "directory changed: %s -> added: %s" % (d, diff))
        INTEGRITY[d] = snap


def guardian():
    global OFF
    ps = pscan()
    for pid, info in ps.items():
        cmd = info["cmd"]
        if not cmd:
            continue
        for tok in EXPELLED:
            if tok in cmd:
                handle(pid, cmd, "EXPEL", tok, info["uid"])
                break
        else:
            for tok in WATCHED:
                if tok in cmd:
                    handle(pid, cmd, "WATCH", tok, info["uid"])
                    break
    OFF = {k: v for k, v in OFF.items() if k in ps}
    integrity_scan()
    respawn_guard(ps)
    c = ctl()
    return {"mode": "aggressive" if c.get("aggressive") else ("armed" if c.get("guard") else "off"),
            "acts": ACTS, "last": LAST_ACT, "ts": int(time.time())}


def respawn_guard(ps):
    c = ctl()
    if not c.get("guard", True):
        return
    now = time.time()
    if not any("raven/app.py" in p["cmd"] for p in ps.values()):
        if now - LAST_TIMES["mom"] > 45:
            LAST_TIMES["mom"] = now
            ev("ACT", "MOTHER SHIP DOWN — relaunching raven app")
            try:
                subprocess.Popen([sys.executable, "/home/a/raven/app.py"],
                                 cwd="/home/a/raven", start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except Exception as ex:
                ev("ERR", "respawn app failed: %r" % ex)
    if c.get("opencode", True) and not any(".opencode/bin/opencode" in p["cmd"] for p in ps.values()):
        if now - LAST_TIMES["oc"] > 60:
            LAST_TIMES["oc"] = now
            ev("ACT", "opencode engine missing — relaunching it")
            try:
                oc = os.path.expanduser("~/.opencode/bin/opencode")
                if os.path.exists(oc):
                    subprocess.Popen([oc, "web"], start_new_session=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            except Exception as ex:
                ev("ERR", "respawn opencode failed: %r" % ex)


def main():
    os.makedirs(RUNTIME, exist_ok=True)
    try:
        with open(PIDF) as f:
            old = int(f.read().strip())
        with open("/proc/%d/stat" % old) as f:
            if f.read().rsplit(")", 1)[1].split()[0] != "Z":
                sys.exit(0)  # a twin is already on watch — never twin-thrash
    except Exception:
        pass
    with open(PIDF, "w") as f:
        f.write(str(os.getpid()))
    ev("LIFE", "unconscious twin + big brother on watch")
    integrity_boot()
    strikes = 0
    while True:
        try:
            dev, gw = route()
            c = ctl()
            heartbeat = online()
            gd = guardian()
            if heartbeat:
                strikes = 0
                beat_state(up=True, iface=dev or "", gw=gw or "", strikes=0,
                           rtt=rtt_ms(), auto=c.get("auto", True), pid=os.getpid(), guard=gd)
            else:
                strikes = min(strikes + 1, 6)
                beat_state(up=False, iface=dev or "", gw=gw or "", strikes=strikes,
                           auto=c.get("auto", True), pid=os.getpid(), guard=gd)
                if dev and c.get("auto", True):
                    heal(dev, strikes)
                elif not dev:
                    ev("CRIT", "no default route — faint but watching; nothing to bounce")
        except Exception as ex:
            ev("ERR", repr(ex))
        try:
            if ctl().get("panic"):
                ev("PANIC", "manual resurrect ordered by the operator")
                if route()[0]:
                    heal(route()[0], 6)
        except Exception:
            pass
        time.sleep(BEAT)


if __name__ == "__main__":
    main()
