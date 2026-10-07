"""Claude Code hook: show the session state on the Windows Terminal tab.

Usage (from a hook): python -I tab_status.py working|tool|done|wait|end
  working  working glyph in the title (animated for the "claude" theme)
  tool     same as working, but skipped if "done" was set less than 3 s ago
           (PostToolUse runs async and can arrive after Stop)
  done     done glyph in the title (Stop)
  wait     done glyph too: Claude waits for you (permission, question)
  end      plain name
Internal: python -I tab_status.py animate <session> <claude pid>

The tab name is the session name from /rename, else the folder name.
The theme is the first word in theme.txt next to this script (default "claude").

Hook commands run in a hidden console, so the script attaches to the console
of the parent claude.exe and writes there. Any failure exits 0 silently.
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import subprocess
import sys
import tempfile
import time

# working: frames (more than one = animated), done: one glyph
THEMES = {
    # no "·" frame: at tab size it looks blank, so the star seemed to blink off
    "claude": {"working": ["✢", "✶", "✻", "✽", "✻", "✶"],
               "done": "✓ "},  # trailing space: the check sits tight against the name
    "steady": {"working": ["✻"], "done": "✓ "},
    "circles": {"working": ["\U0001F7E1"], "done": "\U0001F7E2"},
    "hearts": {"working": ["\U0001F49B"], "done": "\U0001F49A"},
    "moon": {"working": ["\U0001F311", "\U0001F312", "\U0001F313", "\U0001F314", "\U0001F315"],
             "done": "✨"},
    "sprout": {"working": ["\U0001F331"], "done": "\U0001F338"},
    "chick": {"working": ["\U0001F95A"], "done": "\U0001F423"},
}
DEFAULT_THEME = "claude"
FRAME_S = 0.12
ANIM_MAX_S = 4 * 3600

# No spinner ring on the tab icon. Every state clears it,
# also a ring left by an older version of this script.
CLEAR = "\x1b]9;4;0;0\x07"
STATE_DIR = os.path.join(tempfile.gettempdir(), "cli-tabs")
HERE = os.path.dirname(os.path.abspath(__file__))
DONE_GUARD_S = 3.0
TAIL_BYTES = 512 * 1024
MAX_NAME = 30

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateToolhelp32Snapshot.restype = w.HANDLE
k32.CreateFileW.restype = w.HANDLE
k32.OpenProcess.restype = w.HANDLE


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", w.DWORD),
                ("cntThreads", w.DWORD), ("th32ParentProcessID", w.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def find_claude_pid():
    snap = k32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    procs = {}
    ok = k32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        procs[pe.th32ProcessID] = (pe.th32ParentProcessID, pe.szExeFile.lower())
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    pid = os.getpid()
    for _ in range(25):
        if pid not in procs:
            return None
        ppid, exe = procs[pid]
        if exe == "claude.exe":
            return pid
        pid = ppid
    return None


def is_alive(pid):
    h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = w.DWORD()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


def load_theme():
    try:
        with open(os.path.join(HERE, "theme.txt"), encoding="utf-8") as f:
            name = (f.read().split() or [DEFAULT_THEME])[0].lower()
    except OSError:
        name = DEFAULT_THEME
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def custom_title(transcript_path):
    """The name set with /rename, from the end of the transcript, or None."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TAIL_BYTES))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return None
    for line in reversed(lines):
        if '"custom-title"' in line:
            try:
                title = (json.loads(line).get("customTitle") or "").strip()
            except ValueError:
                continue
            if title:
                return title if len(title) <= MAX_NAME else title[:MAX_NAME - 1] + "…"
    return None


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def attach(pid):
    k32.FreeConsole()
    return bool(k32.AttachConsole(pid))


def write_console(seq):
    out = k32.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)  # GENERIC_RW, share RW, OPEN_EXISTING
    if out and out != w.HANDLE(-1).value:
        k32.WriteConsoleW(out, seq, len(seq), ctypes.byref(w.DWORD()), None)
        k32.CloseHandle(out)


def start_animator(session, claude_pid):
    """Start one detached animator per session, unless one already runs."""
    lock = os.path.join(STATE_DIR, session + ".anim")
    pid = read_json(lock).get("pid")
    if pid and is_alive(pid):
        return
    args = [sys.executable, "-I", os.path.abspath(__file__), "animate", session, str(claude_pid)]
    base = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS, NEW_PROCESS_GROUP, NO_WINDOW
    for flags in (base | 0x01000000, base):  # try CREATE_BREAKAWAY_FROM_JOB first
        try:
            subprocess.Popen(args, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            continue


def animate(session, claude_pid):
    """Cycle the working frames until the state is no longer "working"."""
    state_path = os.path.join(STATE_DIR, session + ".json")
    lock = os.path.join(STATE_DIR, session + ".anim")
    write_json(lock, {"pid": os.getpid()})
    try:
        if not attach(claude_pid):
            return
        frames = load_theme()["working"]
        end = time.time() + ANIM_MAX_S
        i = 0
        while time.time() < end and is_alive(claude_pid):
            state = read_json(state_path)
            if state.get("state") != "working":
                return
            k32.SetConsoleTitleW("%s %s" % (frames[i % len(frames)], state.get("name", "")))
            i += 1
            time.sleep(FRAME_S)
    finally:
        if read_json(lock).get("pid") == os.getpid():
            try:
                os.remove(lock)
            except OSError:
                pass


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "done"
    if mode == "animate":
        animate(sys.argv[2], int(sys.argv[3]))
        return
    try:
        hook = json.load(sys.stdin)
    except ValueError:
        hook = {}
    session = hook.get("session_id") or "unknown"
    name = (custom_title(hook.get("transcript_path"))
            or os.path.basename(os.path.normpath(hook.get("cwd") or os.getcwd())) or "claude")
    state_path = os.path.join(STATE_DIR, session + ".json")

    prev = read_json(state_path)
    if mode == "tool":
        if prev.get("state") == "done" and time.time() - prev.get("ts", 0) < DONE_GUARD_S:
            return
        mode = "working"

    # Already working with a live animator: keep its frame. Writing frame 0 here
    # on every tool call made the star jump back each time.
    if mode == "working" and prev.get("state") == "working":
        anim = read_json(os.path.join(STATE_DIR, session + ".anim")).get("pid")
        if anim and is_alive(anim):
            write_json(state_path, {"state": mode, "ts": time.time(), "name": name})
            pid = find_claude_pid()
            if pid is not None and attach(pid):
                write_console(CLEAR)  # still clear a ring from the tool call
                k32.FreeConsole()
            return

    # The state file goes first: the animator reads it on every frame.
    if mode == "end":
        try:
            os.remove(state_path)
        except OSError:
            pass
    else:
        write_json(state_path, {"state": mode, "ts": time.time(), "name": name})

    pid = find_claude_pid()
    if pid is None or not attach(pid):
        return
    theme = load_theme()
    if mode == "end":
        title = name
    elif mode == "working":
        title = "%s %s" % (theme["working"][0], name)
    else:
        title = "%s %s" % (theme["done"], name)
    k32.SetConsoleTitleW(title)
    write_console(CLEAR)

    if mode == "working" and len(theme["working"]) > 1:
        start_animator(session, pid)
    elif mode != "working":
        # An animator frame can land just after the title above; write it again.
        time.sleep(FRAME_S * 2)
        k32.SetConsoleTitleW(title)
    k32.FreeConsole()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
