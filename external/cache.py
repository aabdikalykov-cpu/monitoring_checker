"""FR-8: Кэш результатов внешних запросов (JSON-файл, TTL)."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class FileCache:
    """Простой файловый кэш с TTL в часах."""

    def __init__(self, cache_dir: str = ".cache", ttl_hours: int = 72):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600

    def _key_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        """Вернуть значение из кэша или None, если истекло/отсутствует."""
        path = self._key_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - payload.get("ts", 0) > self.ttl_seconds:
                path.unlink(missing_ok=True)
                return None
            return payload.get("value")
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: Any) -> None:
        """Сохранить значение в кэш."""
        path = self._key_path(key)
        payload = {"ts": time.time(), "value": value}
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
