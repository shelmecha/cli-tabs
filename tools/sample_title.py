"""Test helper: print the tab titles of the parent Claude Code session.

Run it from a Claude Code Bash tool call, so its parent chain reaches claude.exe:
  python -I tools/sample_title.py [seconds]
It attaches to the console of claude.exe and reads the title every 30 ms.
Pass: exit 0, "blank or dot titles: 0", and the frames stay in order.
Exit 1: no parent claude.exe, or a blank or dot title.
"""
import collections
import ctypes
import importlib.util
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tab_status.py")
spec = importlib.util.spec_from_file_location("tab_status", path)
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)

pid = ts.find_claude_pid()
print("claude pid", pid)
ts.k32.FreeConsole()
print("attach", bool(ts.k32.AttachConsole(pid)))
buf = ctypes.create_unicode_buffer(512)
seq = []
end = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 4)
while time.time() < end:
    ts.k32.GetConsoleTitleW(buf, 512)
    if not seq or seq[-1] != buf.value:
        seq.append(buf.value)
    time.sleep(0.03)
ts.k32.FreeConsole()
print("transitions:", len(seq))
print("distinct:", dict(collections.Counter(seq)))
print("first glyphs in order:", " ".join(repr(s[:1]) for s in seq[:40]))
bad = len([s for s in seq if not s.strip() or s.startswith("·")])
print("blank or dot titles:", bad)
sys.exit(0 if pid is not None and bad == 0 else 1)
