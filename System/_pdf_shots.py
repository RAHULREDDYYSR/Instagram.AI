"""Snapshot the current PDF at given pages via agent-browser."""
import subprocess
import sys
from pathlib import Path

PDF = Path(r"C:\Users\rahul\Desktop\Instagram.AI\Brain\Scripts\_Compiled_Scripts_Sample.pdf")
URL = f"file:///{PDF.as_posix()}"
OUT = Path(r"C:\Users\rahul\AppData\Local\Temp\opencode\pass")
OUT.mkdir(parents=True, exist_ok=True)


def sh(cmd, timeout=30000):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=timeout)
    return r.stdout, r.stderr


def open_pdf():
    sh(f'agent-browser open "{URL}"', timeout=60000)
    sh("agent-browser wait 800")


def snapshot():
    sh("agent-browser snapshot -i 2>&1")


def goto(page: int, tag: str):
    sh("agent-browser fill '@e3' '1'")
    sh("agent-browser press Tab")
    sh("agent-browser wait 200")
    sh(f"agent-browser fill '@e3' '{page}'")
    sh("agent-browser press Enter")
    sh("agent-browser wait 600")
    sh(f"agent-browser screenshot \"{OUT / f'{tag}_p{page:02d}.png'}\"")


def main():
    open_pdf()
    pages = [1, 2, 3, 4, 5, 7, 9, 12]
    if len(sys.argv) > 1:
        pages = [int(x) for x in sys.argv[1:]]
    for p in pages:
        goto(p, sys.argv[2] if len(sys.argv) > 2 else "shot")


if __name__ == "__main__":
    main()
