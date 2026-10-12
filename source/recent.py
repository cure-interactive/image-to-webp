"""Machine-local history of desktop conversion configs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


MAX_RECENT = 16


class RecentConfigs:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.paths = self._read()

    def _read(self) -> list[str]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        raw = data.get("recent_configs", []) if isinstance(data, dict) else []
        if not isinstance(raw, list):
            return []
        paths: list[str] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, str) or not item.strip():
                continue
            path = Path(item).expanduser().resolve()
            key = os.path.normcase(str(path))
            if path.is_file() and key not in seen:
                paths.append(str(path))
                seen.add(key)
            if len(paths) == MAX_RECENT:
                break
        return paths

    def remember(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            return
        key = os.path.normcase(str(resolved))
        self.paths = [str(resolved)] + [
            item for item in self.paths if os.path.normcase(item) != key and Path(item).is_file()
        ][:MAX_RECENT - 1]
        self._write()

    def clear(self) -> None:
        self.paths = []
        self._write()

    def _write(self) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                             dir=self.state_path.parent, prefix=".app-state-",
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"recent_configs": self.paths}, stream, indent=2)
                stream.write("\n")
            os.replace(temporary, self.state_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
