"""Atomic working snapshots and independently selected observation history.

Spec Part III: resumption is supported. These records are not advertised as
event-sourced replay. A crash after a dispatch leaves an uncertain charged
reservation; the engine does not retry the remote call automatically.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile


FORMAT_VERSION = 1


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, separators=(",", ":"))
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


@contextmanager
def workspace_lock(directory):
    """Exclude simultaneous CLI writers; stale locks require explicit recovery."""
    path = Path(directory) / ".writer.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError("Run is locked by another writer. After confirming it has stopped, remove .writer.lock to recover.") from error
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class Recorder:
    """Record actual host events; event text cannot choose its operational kind."""

    def __init__(self, directory, mode, limit=256):
        self.directory = Path(directory) if directory else None
        self.mode = mode
        self.limit = limit
        self.observers = []
        self.events = []

    def record(self, event):
        # A test observer is independent of retention and participant history.
        for observer in self.observers:
            observer(json.loads(json.dumps(event)))
        if self.mode == "off":
            return
        if self.directory is None:
            raise OSError("Observation recording needs an explicit run directory")
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.mode == "append-only":
            path = self.directory / "observations.jsonl"
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
                file.flush()
                os.fsync(file.fileno())
        else:
            path = self.directory / "observations.json"
            events = read_json(path) if path.exists() else []
            atomic_json(path, (events + [event])[-self.limit:])
