#!/usr/bin/env python3
"""systemwatch — a lean, read-only eye on the whole host.

Two jobs, both cheap on purpose:

  1. INJECTION / hiding  — walks /proc (world-readable) and flags the tells of
     code being slipped into this machine:
        * TracerPid != 0            -> a debugger/injector has attached to a process
        * LD_PRELOAD set            -> a library is being force-loaded into a program
        * a program running from /tmp, /dev/shm, /run/user -> dropped payload
        * an executable whose file was deleted/replaced while it runs
     No killing here. It only reports. (ravenheart decides what to do; this is the eye.)

  2. FILE ACCESS — uses the kernel's inotify directly (via ctypes, no packages)
     to watch the paths that matter (keys, config, raven's own state, autostart)
     and logs every open/read/write/delete. Event-driven: it costs nothing while
     nothing is happening.

Honest limits: inotify says WHAT was touched and WHEN, not WHO (the kernel does
not hand out the reader's pid on this interface). For attribution you correlate
its timestamps with the process sweep. It only sees paths you put on the watch
list, and only while it is running.
"""
import argparse
import ctypes
import ctypes.util
import json
import os
import select
import struct
import subprocess
import sys
import time

# named "events.*" on purpose: ravenheart's survival freeze skips those, so the
# log stays appendable even while the rest of ~/.ravenheart is chattr +i.
LOG = os.path.expanduser("~/.ravenheart/events.systemwatch.log")
LOG_CAP = 1_000_000          # keep the log under ~1MB; rotate one old copy
UNIT = "systemwatch.service"  # the always-lean service raven's UI and the wire arm


# ── the on/off hook anyone can call (raven GUI, mr.fluffy's wire) ───────────
def _systemctl(*args):
    try:
        return subprocess.run(["systemctl", "--user", *args],
                              capture_output=True, text=True, timeout=6).stdout.strip()
    except Exception:
        return ""


def arm():
    """Start the eye (idempotent)."""
    _systemctl("start", UNIT)
    return status()


def standdown():
    """Return the eye to dormancy (idempotent)."""
    _systemctl("stop", UNIT)
    return status()


def status():
    return _systemctl("is-active", UNIT) or "unknown"

# ── inotify constants (linux/inotify.h) ─────────────────────────────────────
IN_ACCESS        = 0x00000001
IN_MODIFY        = 0x00000002
IN_ATTRIB        = 0x00000004
IN_CLOSE_WRITE   = 0x00000008
IN_CLOSE_NOWRITE = 0x00000010
IN_OPEN          = 0x00000020
IN_MOVED_FROM    = 0x00000040
IN_MOVED_TO      = 0x00000080
IN_CREATE        = 0x00000100
IN_DELETE        = 0x00000200
IN_DELETE_SELF   = 0x00000400
IN_MOVE_SELF     = 0x00000800
IN_ISDIR         = 0x40000000
O_NONBLOCK       = 0x00000800
O_CLOEXEC        = 0x00080000

WATCH_MASK = (IN_ACCESS | IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE |
              IN_OPEN | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE |
              IN_DELETE | IN_DELETE_SELF | IN_MOVE_SELF)

MASK_NAME = {
    IN_ACCESS: "READ", IN_MODIFY: "WRITE", IN_ATTRIB: "CHATTR",
    IN_CLOSE_WRITE: "CLOSE-W", IN_CLOSE_NOWRITE: "CLOSE-R", IN_OPEN: "OPEN",
    IN_MOVED_FROM: "MOVE-OUT", IN_MOVED_TO: "MOVE-IN", IN_CREATE: "CREATE",
    IN_DELETE: "DELETE", IN_DELETE_SELF: "SELF-GONE", IN_MOVE_SELF: "SELF-MOVED",
}

# paths worth an eye: keys, config, raven's own memory, autostart, shells
DEFAULT_WATCH = [
    "~/.ssh", "~/.gnupg", "~/.config/opencode", "~/.ravenheart",
    "~/.config/autostart", "~/.local/share/keyrings",
    "~/.bashrc", "~/.zshrc", "~/.profile",
    "~/.bash_history", "~/.zsh_history",
    "/home/a/raven/app.py", "/home/a/raven/ravenheart.py",
]

# name fragments never logged: our own log (feedback loop) and raven's ledgers
SKIP_NAMES = ("events.", "systemwatch.log", "/proc/", "node_modules", "__pycache__")

# subtrees that are huge and irrelevant — never descend into them
DIR_SKIP = {"node_modules", "__pycache__", ".git", "sync", "cache", "Cache"}
MAX_WATCH = 4000             # hard cap so we never exhaust the kernel watches

# programs that legitimately map RWX / run from odd places, so we don't cry wolf
ALLOW = ("ravenheart.py", "raven/app.py", "systemwatch.py", "Xorg", "Xwayland",
         "kwin_wayland", "plasmashell", "pulseaudio", "pipewire", "systemd",
         "NetworkManager", "dbus-daemon", "python3", "python", "opencode",
         "chrome", "firefox", "electron", "java", "node", "code")


# ── logging (capped) ────────────────────────────────────────────────────────
def log(line):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        if os.path.exists(LOG) and os.path.getsize(LOG) > LOG_CAP:
            try:
                os.replace(LOG, LOG + ".1")
            except OSError:
                open(LOG, "w").close()
        with open(LOG, "a") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except Exception:
        pass


# ── job 1: injection / hiding sweep over /proc ──────────────────────────────
def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return b""


def scan_injection():
    """One pass over /proc. Returns a list of finding dicts. Cheap: reads a
    couple of small files per process, skips the rest on the fast path."""
    finds = []
    me = os.getpid()
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        pid = int(d)
        if pid == me:
            continue
        status = _read("/proc/%d/status" % pid).decode("utf-8", "replace")
        if not status:
            continue
        name = ""
        tracer = "0"
        for ln in status.splitlines():
            if ln.startswith("Name:"):
                name = ln.split(":", 1)[1].strip()
            elif ln.startswith("TracerPid:"):
                tracer = ln.split(":", 1)[1].strip()
        cmdline = _read("/proc/%d/cmdline" % pid).replace(b"\0", b" ").decode("utf-8", "replace").strip()
        allowed = any(a in cmdline or a == name for a in ALLOW)

        if tracer not in ("0", ""):
            finds.append({"kind": "TRACED", "pid": pid, "name": name,
                          "detail": "pid %d (%s) is being traced by pid %s — "
                                    "debugger/injector attached" % (pid, name, tracer)})
        # exe path: dropped payload or replaced binary
        try:
            exe = os.readlink("/proc/%d/exe" % pid)
        except OSError:
            exe = ""
        if exe:
            if exe.endswith(" (deleted)"):
                finds.append({"kind": "REPLACED", "pid": pid, "name": name,
                              "detail": "pid %d (%s) runs %s — the file was "
                                        "deleted/replaced under it" % (pid, name, exe)})
            elif (exe.startswith(("/tmp/", "/dev/shm/", "/run/user/"))
                  and not allowed):
                finds.append({"kind": "WILD_EXEC", "pid": pid, "name": name,
                              "detail": "pid %d (%s) runs from %s — dropped "
                                        "payload territory" % (pid, name, exe)})
        # LD_PRELOAD: library injected into a running program
        env = _read("/proc/%d/environ" % pid).split(b"\0")
        for e in env:
            if e.startswith(b"LD_PRELOAD=") and not allowed:
                val = e.split(b"=", 1)[1].decode("utf-8", "replace")
                finds.append({"kind": "PRELOAD", "pid": pid, "name": name,
                              "detail": "pid %d (%s) has LD_PRELOAD=%s"
                                        % (pid, name, val)})
                break
    return finds


# ── job 2: inotify file-access watch ────────────────────────────────────────
class Inotify:
    def __init__(self):
        libc_name = ctypes.util.find_library("c") or "libc.so.6"
        self.libc = ctypes.CDLL(libc_name, use_errno=True)
        self.fd = self.libc.inotify_init1(O_NONBLOCK | O_CLOEXEC)
        if self.fd < 0:
            raise OSError("inotify_init1 failed")
        self.wd_path = {}

    def add(self, path, recursive=True):
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            return self._add_one(path) if os.path.exists(path) else 0
        if not recursive:
            return self._add_one(path)
        n = 0
        for root, dirs, _files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in DIR_SKIP]   # prune in place
            n += self._add_one(root)
            if len(self.wd_path) >= MAX_WATCH:
                break
        return n

    def _add_one(self, path):
        wd = self.libc.inotify_add_watch(self.fd, path.encode(), WATCH_MASK)
        if wd < 0:
            return 0
        self.wd_path[wd] = path
        return 1

    def read(self, timeout=1.0):
        r, _w, _x = select.select([self.fd], [], [], timeout)
        if not r:
            return []
        data = os.read(self.fd, 65536)
        out = []
        i = 0
        while i + 16 <= len(data):
            wd, mask, cookie, length = struct.unpack_from("iIII", data, i)
            i += 16
            name = data[i:i + length].split(b"\0", 1)[0].decode("utf-8", "replace")
            i += length
            base = self.wd_path.get(wd, "?")
            full = os.path.join(base, name) if name else base
            out.append((full, mask))
        return out


def describe(path, mask):
    acts = [v for k, v in MASK_NAME.items() if mask & k]
    if mask & IN_ISDIR:
        acts.append("(dir)")
    if not acts:
        return None
    if any(s in path for s in SKIP_NAMES):
        return None
    return "%s -> %s" % (",".join(acts), path)


def watch(paths, quiet=False):
    iface = Inotify()
    total = sum(iface.add(p) for p in paths)
    log("systemwatch: watching %d path(s)" % total)
    if not quiet:
        print("watching %d path(s); events -> %s" % (total, LOG))
    while True:
        for path, mask in iface.read(timeout=2.0):
            line = describe(path, mask)
            if not line:
                continue
            # a plain read/open of a key file is the loud one
            loud = bool(mask & (IN_ACCESS | IN_DELETE | IN_MOVED_FROM | IN_ATTRIB))
            log(("FILE! " if loud else "file  ") + line)
            if not quiet:
                print(("FILE! " if loud else "file  ") + line)


def loop_injection(interval, quiet=False, as_json=None):
    seen = set()
    first = True
    while True:
        keys = set()
        for f in scan_injection():
            k = (f["kind"], f["pid"])
            keys.add(k)
            if k in seen:
                continue
            log("INJECT? " + f["detail"])
            if not quiet:
                print("INJECT? " + f["detail"])
        if as_json:
            try:
                with open(as_json, "w") as fh:
                    json.dump({"ts": int(time.time()), "findings": scan_injection()}, fh)
            except Exception:
                pass
        seen = keys
        time.sleep(interval)


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)   # live output even when piped
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="lean read-only system eye")
    ap.add_argument("--injection", action="store_true", help="one injection sweep, then exit")
    ap.add_argument("--watch", action="store_true", help="watch files (inotify), run until stopped")
    ap.add_argument("--all", action="store_true", help="injection loop + file watch together")
    ap.add_argument("--interval", type=float, default=15.0, help="seconds between injection sweeps")
    ap.add_argument("--paths", nargs="*", default=DEFAULT_WATCH)
    ap.add_argument("--json", metavar="PATH", default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--arm", action="store_true", help="start the eye (service), then report")
    ap.add_argument("--standdown", action="store_true", help="stop the eye, then report")
    ap.add_argument("--status", action="store_true", help="report whether the eye is open")
    a = ap.parse_args()

    if a.arm or a.standdown or a.status:
        if a.arm:
            arm()
        if a.standdown:
            standdown()
        print("systemwatch:", status())
        return 0

    if a.injection or not (a.watch or a.all):
        finds = scan_injection()
        if not finds:
            print("injection sweep: clean — no tracer, no LD_PRELOAD, no dropped "
                  "executables, no replaced binaries")
        else:
            for f in finds:
                print("[%s] %s" % (f["kind"], f["detail"]))
            log("injection sweep: %d finding(s)" % len(finds))
        if a.json:
            with open(a.json, "w") as fh:
                json.dump({"ts": int(time.time()), "findings": finds}, fh)
        if not (a.watch or a.all):
            return 0
    if a.all:
        import threading
        threading.Thread(target=loop_injection, args=(a.interval, a.quiet, a.json),
                         daemon=True).start()
        watch(a.paths, a.quiet)
    elif a.watch:
        watch(a.paths, a.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
