"""Protected user-level credentials and cross-process refresh serialization."""

from __future__ import annotations

import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4


class CredentialStore:
    """Store connections outside projects, shared by local Thadam interfaces.

    No paths are read or created until an explicit connection operation. Unix
    uses owner-only files/directories; Windows relies on the user's profile ACL.
    An explicit directory is useful for isolated applications and tests.
    """

    def __init__(self, directory: str | Path | None = None):
        self.root = (
            Path(directory)
            if directory is not None
            else Path(os.environ.get("THADAM_CONFIG_DIR", Path.home() / ".config" / "thadam"))
        )

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise ValueError("Credential directory must not be a symbolic link")
        if os.name != "nt":
            self.root.chmod(0o700)
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.root / "connections.lock", flags, 0o600)
        with os.fdopen(fd, "a+b") as stream:
            if os.name == "nt":
                import msvcrt

                stream.write(b"\0")
                stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield self
            finally:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def read(self) -> dict:
        """Read while holding locked(); reject links and permissive Unix files."""
        path = self.root / "connections.json"
        if path.is_symlink():
            raise ValueError("Credential file must not be a symbolic link")
        if not path.exists():
            return {}
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("Credential file must have owner-only permissions (chmod 600)")
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, UnicodeError) as error:
            raise ValueError("Saved connection is invalid; disconnect and reconnect") from error

    def write(self, data: dict) -> None:
        """Atomically replace the entire credential set while holding locked()."""
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.root, delete=False
            ) as file:
                temporary = Path(file.name)
                file.write(json.dumps(data, ensure_ascii=False, allow_nan=False))
            temporary.replace(self.root / "connections.json")
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def host_id(self, data: dict) -> str:
        if not data.get("host_id"):
            data["host_id"] = "urn:uuid:" + str(uuid4())
            self.write(data)
        return data["host_id"]

    def disconnect(self, connection: str) -> None:
        if connection not in ("api_key", "chatgpt"):
            raise ValueError("Choose api_key or chatgpt")
        with self.locked():
            data = self.read()
            data.pop(connection, None)
            self.write(data)
