#!/usr/bin/env python3
# ravenheart — the unconscious twin + big brother. one job: this host never loses its link,
# and nobody — student or tool — gets to watch its screen, gut its tools, or rewrite its files.
# a separate process on purpose: if the Raven GUI dies, this keeps beating anyway.
import hashlib, json, os, shlex, socket, subprocess, sys, time

RUNTIME = "/tmp/ravenheart"
MIRROR = os.path.expanduser("~/.ravenheart")   # survives an attacker wiping /tmp
MSYNC = MIRROR + "/sync"
STATE = RUNTIME + "/state.json"
LEDGER = RUNTIME + "/events.log"
CONTROL = RUNTIME + "/control.json"
MCONTROL = MIRROR + "/control.json"
PIDF = RUNTIME + "/twin.pid"
WDF = RUNTIME + "/watchdog.pid"
MWDF = MIRROR + "/watchdog.pid"
MANIFEST = MIRROR + "/manifest.json"           # sha256 of every sealed file

BEAT = 2.0
SURV_LOCKED = False
THAWED = False


def shout(cmd, timeout=7):
    try:
        return subprocess.run(cmd, shell=True, timeout=timeout, text=True,
                              capture_output=True).stdout.strip()
    except Exception:
        return ""


def run_argv(argv, timeout=7):
    # no /bin/sh between us and the tool — one fork instead of two, every beat
    try:
        return subprocess.run(argv, timeout=timeout, text=True,
                              capture_output=True).stdout.strip()
    except Exception:
        return ""


def ev(tag, msg):
    line = "[%s] %s: %s\n" % (time.strftime("%H:%M:%S"), tag, msg)
    for path in (LEDGER, MIRROR + "/events.log"):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                f.write(line)
        except Exception:
            pass


def beat_state(**kw):
    st = {"t": time.strftime("%H:%M:%S"), "ts": int(time.time())}
    st.update(kw)
    tmp = STATE + ".tmp"
    try:
        os.makedirs(RUNTIME, exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, STATE)
    except Exception:
        pass


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def dump(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        return True
    except OSError:
        return False


_MEMO = {}


def _memo(key, ttl, fn):
    # control files are human-driven; re-reading + parsing them ~4x per beat is
    # pure churn. Cache for < one beat so a button press is still seen promptly.
    now = time.time()
    ent = _MEMO.get(key)
    if ent and now - ent[0] < ttl:
        return ent[1]
    val = fn()
    _MEMO[key] = (now, val)
    return val


def survival_on():
    # the mirror is the single source of truth — wiping /tmp does not disarm it
    return bool(_memo("surv", 1.0, lambda: load(MCONTROL).get("survival")))


def _ctl_load():
    base = {"auto": True, "resurrect": True, "guard": True,
            "aggressive": True, "opencode": True, "survival": False,
            "threshold": 2}
    base.update(load(MCONTROL))     # mirror first…
    base.update(load(CONTROL))      # …live file wins, then survival is re-checked
    if survival_on():
        # survival means "extreme protective": it does not accept being talked
        # out of guarding by a rewritten control.json
        base.update({"survival": True, "auto": True, "resurrect": True,
                     "guard": True, "aggressive": True, "opencode": True})
    return base


def ctl():
    return _memo("ctl", 1.0, _ctl_load)


def route():
    out = run_argv(["ip", "route", "show", "default"]).split()
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
    out = run_argv(["ping", "-q", "-c", "1", "-W", "2", host])
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

# Anything spawned by Raven itself (its tshark/dumpcap captures, scans, crow
# tasks) is Raven's own gear — never an intruder. Matching by ancestor command
# keeps a student's standalone tshark watched while leaving ours alone.
TRUSTED_ROOTS = ("raven/app.py", "ravenheart.py", "/.opencode/bin/opencode",
                 "opencode web", "opencode serve", "opencode tui")

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
    # only the command line is needed every beat; uid/ppid are pulled lazily
    # (proc_meta) for the handful of processes that actually match a token.
    procs = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open("/proc/" + d + "/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            procs[int(d)] = {"cmd": cmd}
        except Exception:
            continue
    return procs


_PROC_META = {}


def proc_meta(pid):
    now = time.time()
    ent = _PROC_META.get(pid)
    if ent and now - ent[0] < 1.0:
        return ent[1]
    uid, ppid = "?", 0
    try:
        with open("/proc/%d/status" % pid) as f:
            for ln in f:
                if ln.startswith("Uid:"):
                    uid = ln.split()[1]
                elif ln.startswith("PPid:"):
                    ppid = int(ln.split()[1])
    except Exception:
        pass
    val = (uid, ppid)
    _PROC_META[pid] = (now, val)
    return val


def trusted(pid, procs):
    # walk the ancestor chain; a descendant of Raven/opencode is Raven's own tool
    seen = set()
    while pid and pid not in seen:
        seen.add(pid)
        info = procs.get(pid)
        if info is None:
            return False
        cmd = info.get("cmd", "")
        for r in TRUSTED_ROOTS:
            if r in cmd:
                return True
        try:
            pid = proc_meta(pid)[1]
        except Exception:
            return False
    return False


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


STAT_CACHE = {}


def checksum_cached(path):
    # the beat is 2s; re-reading+hashing app.py/ravenheart.py every beat is pure
    # IO/CPU burn. Fingerprint on (mtime_ns, size) and only re-hash on change.
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (int(st.st_mtime_ns), int(st.st_size))
    ent = STAT_CACHE.get(path)
    if ent is not None and ent[0] == key:
        return ent[1]
    h = checksum(path)
    if h is not None:
        STAT_CACHE[path] = (key, h)
    return h


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
            data = f.read()
    except Exception:
        return
    for d in (SYNC_DIR, MSYNC):
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, b), "wb") as g:
                g.write(data)
        except Exception:
            pass


# ── SURVIVAL: seal the files, spawn the second heart ─────────────────────────
def freeze_list():
    paths = [os.path.expanduser(p) for p in CORE_FILES + LATCH_FILES]
    for root, _dirs, files in os.walk(MIRROR):
        for n in files:
            if n.startswith("events"):     # the ledger stays appendable
                continue
            paths.append(os.path.join(root, n))
    return paths


def chattr(path, on):
    return shout("sudo -n chattr %s %s 2>/dev/null" % ("+i" if on else "-i",
                                                       shlex.quote(path)), timeout=5)


def freeze(paths=None):
    for p in (paths or freeze_list()):
        chattr(p, True)


def thaw(paths=None):
    for p in (paths or freeze_list()):
        chattr(p, False)


def proc_alive(pidf):
    try:
        pid = int(open(pidf).read().strip())
        with open("/proc/%d/stat" % pid) as f:
            if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                return None
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def twin_alive():
    # an attacker can wipe the pid file — find a live twin the hard way
    me = os.getpid()
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            with open("/proc/%s/cmdline" % d, "rb") as f:
                toks = f.read().split(b"\0")
        except Exception:
            continue
        if not toks or not toks[0].endswith((b"python3", b"python")):
            continue
        if not any(t.endswith(b"ravenheart.py") for t in toks[1:]):
            continue
        if b"--watchdog" in toks:
            continue
        try:
            with open("/proc/%s/stat" % d) as f:
                if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                    continue
        except Exception:
            continue
        return True
    return False


def spawn(argv):
    try:
        subprocess.Popen(argv, cwd="/home/a/raven", start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except Exception as ex:
        ev("ERR", "spawn %s failed: %r" % (argv, ex))
        return False


def self_path():
    return os.path.abspath(__file__)


# ── the unkillable supervisor: systemd --user owns the second heart ──────────
UNIT = "raven-heart"


def unit_state():
    if not os.path.exists("/usr/bin/systemctl"):
        return ""
    return shout("systemctl --user show %s -p ActiveState --value 2>/dev/null" % UNIT,
                 timeout=5).strip()


def stop_unit():
    if os.path.exists("/usr/bin/systemctl"):
        shout("systemctl --user stop %s.service 2>/dev/null" % UNIT, timeout=8)


def ensure_watchdog():
    # one heart only: systemd's copy wins, the manual spawn is the fallback
    if proc_alive(WDF) or proc_alive(MWDF):
        return True
    if os.path.exists("/usr/bin/systemctl"):
        shout("systemctl --user start %s.service 2>/dev/null" % UNIT, timeout=8)
        if unit_state() in ("active", "activating"):
            return True
        # no unit yet (or an attacker stopped it) — recreate the transient unit
        # Restart=on-failure: a SIGKILL counts as a failure, so it comes back ~1s.
        # KillMode=process: stopping the unit takes only the heart — the twin and
        # Raven (started from inside the unit's cgroup) survive a stand-down.
        shout("systemd-run --quiet --user --unit=%s --property=Restart=on-failure "
              "--property=RestartSec=1 --property=KillMode=process "
              "--property=Type=simple "
              "/usr/bin/python3 %s --watchdog" % (UNIT, shlex.quote(self_path())), timeout=8)
        if unit_state() in ("active", "activating"):
            ev("ACT", "second heart handed to systemd (Restart=on-failure) — it cannot stay dead")
            return True
    spawn([sys.executable, self_path(), "--watchdog"])
    return True


def load_manifest():
    return load(MANIFEST)


def seal_manifest():
    # arming is an operator action: the live copy becomes the sealed baseline
    man = {}
    for p in CORE_FILES + LATCH_FILES:
        p = os.path.expanduser(p)
        man[p] = checksum(p)
        backup(p)
    dump(MANIFEST, man)
    return man


def unseal_manifest():
    # standing down = the operator is allowed to edit: re-seal on the live copy
    thaw()
    man = {}
    for p in CORE_FILES + LATCH_FILES:
        p = os.path.expanduser(p)
        man[p] = checksum(p)
        backup(p)
    dump(MANIFEST, man)
    return man


def copy_in(path):
    b = os.path.basename(path)
    for d in (MSYNC, SYNC_DIR):
        try:
            with open(os.path.join(d, b), "rb") as g:
                data = g.read()
            chattr(path, False)
            with open(path, "wb") as f:
                f.write(data)
            if survival_on():
                chattr(path, True)
            return True
        except Exception:
            continue
    return False


def integrity_boot():
    os.makedirs(SYNC_DIR, exist_ok=True)
    os.makedirs(LAIR, exist_ok=True)
    man = load_manifest() if survival_on() else {}   # sealed baseline only under survival
    for p in CORE_FILES + LATCH_FILES + SUSPECT_FILES:
        p = os.path.expanduser(p)
        want = man.get(p)
        if want and checksum(p) != want and copy_in(p):
            ev("EXPEL", "%s was rewritten while sealed — rolled back to the twin's copy" % p)
        elif not man:
            backup(p)
        INTEGRITY[p] = want or checksum(p)
    for d in WATCH_DIRS:
        INTEGRITY[d] = dir_snap(os.path.expanduser(d))


def integrity_scan():
    sealed = survival_on() and bool(load_manifest())
    if not sealed and time.time() - LAST_TIMES["sync"] > 3600:  # hourly re-backup
        LAST_TIMES["sync"] = time.time()
        for p in CORE_FILES + LATCH_FILES:
            backup(os.path.expanduser(p))
    for p in CORE_FILES + LATCH_FILES:
        p = os.path.expanduser(p)
        cur = checksum_cached(p)
        base = INTEGRITY.get(p)
        if cur is None:
            continue
        if base and cur != base:
            if copy_in(p):
                INTEGRITY[p] = checksum_cached(p)
                ev("EXPEL", "hand rewrote %s — restored from the twin's copy" % p)
            else:
                ev("ALERT", "tampered %s and restore failed" % p)
        else:
            INTEGRITY.setdefault(p, cur)
    for p in SUSPECT_FILES:
        p = os.path.expanduser(p)
        cur = checksum_cached(p)
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
        cls = tok = ""
        for t in EXPELLED:
            if t in cmd:
                cls, tok = "EXPEL", t
                break
        if not cls:
            for t in WATCHED:
                if t in cmd:
                    cls, tok = "WATCH", t
                    break
        if not cls:
            continue
        if trusted(pid, ps):
            continue
        handle(pid, cmd, cls, tok, proc_meta(pid)[0])
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
        # survival = extreme protective: the mother ship comes back fast
        wait = 10 if c.get("survival") else 45
        if now - LAST_TIMES["mom"] > wait:
            LAST_TIMES["mom"] = now
            ev("ACT", "MOTHER SHIP DOWN — relaunching raven app")
            try:
                subprocess.Popen([sys.executable, "/home/a/raven/app.py"],
                                 cwd="/home/a/raven", start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except Exception as ex:
                ev("ERR", "respawn app failed: %r" % ex)
    # NOTE: opencode is the operator's quicklaunch helper, not part of the host's
    # lifeline. The twin must never spend cycles (or open browser tabs) respawning it.


# ── SURVIVAL: the twin locks itself down and spawns the second heart ─────────
def survival_lock():
    global SURV_LOCKED
    os.makedirs(MIRROR, exist_ok=True)
    man = seal_manifest()
    freeze()
    SURV_LOCKED = True
    ensure_watchdog()
    ev("ACT", "SURVIVAL ARMED — %d core files sealed (chattr +i), second heart on watch"
       % len(man))


def survival_unlock():
    global SURV_LOCKED, THAWED
    unseal_manifest()
    SURV_LOCKED = False
    THAWED = True
    kill_watchdog()
    ev("ACT", "SURVIVAL STAND DOWN — files thawed, second heart dismissed")


def kill_watchdog():
    stop_unit()
    wd = proc_alive(WDF) or proc_alive(MWDF)
    if not wd:
        return
    try:
        os.kill(wd, 9)
    except Exception:
        pass
    for f in (WDF, MWDF):
        try:
            os.remove(f)
        except OSError:
            pass


def keep_survival():
    # runs every beat: seal, re-assert, and refuse to be talked out of it
    global SURV_LOCKED, THAWED
    if not survival_on():
        if SURV_LOCKED:
            survival_unlock()          # full teardown, once
        elif not THAWED:
            kill_watchdog()            # boot with survival off: make sure it's clean
            thaw()
            THAWED = True
        return
    if not SURV_LOCKED:
        survival_lock()
        return
    ensure_watchdog()
    data = load(CONTROL)
    if data:
        if not data.get("survival") or not all(data.get(k) for k in
                                               ("guard", "auto", "resurrect", "aggressive")):
            data.update({"survival": True, "guard": True, "auto": True,
                         "resurrect": True, "aggressive": True, "opencode": True})
            dump(CONTROL, data)
            ev("ACT", "control.json rewritten to disarm survival — forced back on")


def watchdog_main():
    # the second heart: if the twin dies, it comes back within ~1.5s
    for other in (WDF, MWDF):          # one heart only — never two racing
        pid = proc_alive(other)
        if pid and pid != os.getpid():
            return
    os.makedirs(RUNTIME, exist_ok=True)
    os.makedirs(MIRROR, exist_ok=True)
    for f in (WDF, MWDF):
        try:
            with open(f, "w") as fh:
                fh.write(str(os.getpid()))
        except OSError:
            pass
    ev("LIFE", "second heart (watchdog) on watch — the twin cannot stay dead")
    last = 0
    while True:
        try:
            if not survival_on():
                ev("ACT", "second heart retiring — survival stood down")
                for f in (WDF, MWDF):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
                return
            if not os.path.isdir(RUNTIME):
                os.makedirs(RUNTIME, exist_ok=True)
                ev("ACT", "second heart: /tmp/ravenheart was wiped — rebuilt it")
            if not load(CONTROL):
                dump(CONTROL, load(MCONTROL))
                ev("ACT", "second heart: control.json gone — restored from the mirror")
            if not load(CONTROL).get("survival"):
                d = load(CONTROL)
                d["survival"] = True
                dump(CONTROL, d)
                ev("ACT", "second heart: survival flipped off in control.json — re-asserted")
            if not twin_alive() and time.time() - last > 3:
                last = time.time()
                ev("ACT", "second heart: TWIN IS DOWN — pulling it back")
                spawn([sys.executable, self_path()])
        except Exception as ex:
            ev("ERR", "second heart: %r" % ex)
        time.sleep(1.5)


def main():
    os.makedirs(RUNTIME, exist_ok=True)
    if twin_alive():
        sys.exit(0)  # a twin is already on watch — never twin-thrash
    with open(PIDF, "w") as f:
        f.write(str(os.getpid()))
    ev("LIFE", "unconscious twin + big brother on watch")
    integrity_boot()
    strikes = 0
    beat = 0
    while True:
        try:
            # the pid file can be wiped with /tmp — keep it truthful so the
            # pane and the shutdown button can always find this twin
            me = str(os.getpid())
            try:
                cur = open(PIDF).read().strip()
            except OSError:
                cur = ""
            if cur != me:
                os.makedirs(RUNTIME, exist_ok=True)
                with open(PIDF, "w") as f:
                    f.write(me)
        except Exception:
            pass
        try:
            keep_survival()
        except Exception as ex:
            ev("ERR", "survival: %r" % ex)
        try:
            dev, gw = route()
            c = ctl()
            # AUTO RESURRECT: ping the bearer every beat; armed = ping + fix itself
            armed = bool(c.get("auto", True)) and bool(c.get("resurrect", True))
            # probe the WAN only when auto-resurrect can act on the answer; when
            # it's off, "up" is local route presence and we send no packets.
            if armed:
                rtt = rtt_ms()                   # one real ICMP ping, every beat
                heartbeat = (rtt is not None) or online()
            else:
                rtt = None
                heartbeat = bool(dev)
            gd = guardian()
            surv = survival_on()
            if heartbeat:
                if strikes:
                    ev("PING", "bearer is back — 1.1.1.1 answered in %s ms" % rtt)
                strikes = 0
                beat += 1
                if armed and beat % 15 == 0:
                    ev("PING", "auto resurrect probe: 1.1.1.1 answered in %s ms" % rtt)
                beat_state(up=True, iface=dev or "", gw=gw or "", strikes=0,
                           rtt=rtt, auto=armed, surv=surv, pid=os.getpid(), guard=gd)
            else:
                strikes = min(strikes + 1, 6)
                beat_state(up=False, iface=dev or "", gw=gw or "", strikes=strikes,
                           rtt=None, auto=armed, surv=surv, pid=os.getpid(), guard=gd)
                if armed:
                    ev("PING", "no answer from 1.1.1.1/8.8.8.8 — auto resurrect (%d/6)"
                       % strikes)
                    if dev:
                        heal(dev, strikes)
                    else:
                        ev("CRIT", "no default route — faint but watching; nothing to bounce")
                elif not dev:
                    ev("CRIT", "no default route — faint but watching; nothing to bounce")
        except Exception as ex:
            ev("ERR", repr(ex))
        try:
            c = ctl()
            if c.get("panic"):
                ev("PANIC", "manual resurrect ordered by the operator")
                if route()[0]:
                    heal(route()[0], 6)
                c["panic"] = 0          # one click = one resurrect; consume the flag
                with open(CONTROL, "w") as f:
                    json.dump(c, f)
        except Exception:
            pass
        time.sleep(BEAT)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watchdog":
        watchdog_main()
    else:
        main()
