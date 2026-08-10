"""Small cross-platform advisory lock for shared pipeline state."""

from __future__ import annotations

import functools
import os
import tempfile
import time
from contextlib import contextmanager
from typing import Callable, Iterator, TypeVar


WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCK_PATH = os.path.join(WORKSPACE, ".instagram_ai_workbook.lock")
F = TypeVar("F", bound=Callable)


@contextmanager
def workspace_lock(timeout: float = 60.0) -> Iterator[None]:
    """Serialize workbook read-modify-write operations across processes."""
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    with open(LOCK_PATH, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()

        deadline = time.monotonic() + timeout
        locked = False
        while time.monotonic() < deadline:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except (OSError, BlockingIOError):
                time.sleep(0.1)

        if not locked:
            raise TimeoutError(f"timed out acquiring workspace lock: {LOCK_PATH}")

        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def locked(function: F) -> F:
    """Decorator for top-level commands that own a workbook transaction."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with workspace_lock():
            return function(*args, **kwargs)
    return wrapper  # type: ignore[return-value]


@contextmanager
def atomic_path(path: str) -> Iterator[str]:
    """Yield a sibling temp path and replace the destination after success."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".atomic_", suffix=".tmp", dir=directory)
    os.close(fd)
    try:
        yield temp_path
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
