#!/usr/bin/env python3

"""Persistent library: recently-used history and named collections.

Sounds are stored as the raw Freesound result dicts, so the Library and
collections keep working (playback, waveform, metadata) without re-querying.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from resolve_freesound_browser.logging_setup import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)

# Sentinel "source" used by the UI to request the recently-used history.
HISTORY_KEY = "__history__"


def _sound_id(sound: dict[str, Any]) -> str:
    return str(sound.get("id", ""))


class LibraryStore:
    MAX_HISTORY = 300

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.history_path = self.dir / "history.json"
        self.collections_path = self.dir / "collections.json"
        self.history: list[dict[str, Any]] = self._load(self.history_path, [])
        self.collections: dict[str, list[dict[str, Any]]] = self._load(self.collections_path, {})

    # ----- persistence -------------------------------------------------
    def _load(self, path: Path, default):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except Exception:
            log.warning("Could not read %s; starting empty", path, exc_info=True)
            return default
        if type(data) is not type(default):
            return default
        return data

    def _save(self, path: Path, data) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError:
            log.exception("Could not write %s", path)

    # ----- history -----------------------------------------------------
    def record_use(self, sound: dict[str, Any]) -> None:
        sid = _sound_id(sound)
        if not sid:
            return
        self.history = [s for s in self.history if _sound_id(s) != sid]
        self.history.insert(0, sound)
        del self.history[self.MAX_HISTORY:]
        self._save(self.history_path, self.history)
        log.debug("Recorded use of sound %s (history=%d)", sid, len(self.history))

    def clear_history(self) -> None:
        self.history = []
        self._save(self.history_path, self.history)

    # ----- collections -------------------------------------------------
    def collection_names(self) -> list[str]:
        return sorted(self.collections.keys(), key=str.lower)

    def create_collection(self, name: str) -> bool:
        name = name.strip()
        if not name:
            return False
        if name not in self.collections:
            self.collections[name] = []
            self._save(self.collections_path, self.collections)
            log.info("Created collection %r", name)
        return True

    def delete_collection(self, name: str) -> None:
        if name in self.collections:
            del self.collections[name]
            self._save(self.collections_path, self.collections)
            log.info("Deleted collection %r", name)

    def add_to_collection(self, name: str, sound: dict[str, Any]) -> None:
        name = name.strip()
        if not name:
            return
        coll = self.collections.setdefault(name, [])
        sid = _sound_id(sound)
        if not any(_sound_id(s) == sid for s in coll):
            coll.insert(0, sound)
            self._save(self.collections_path, self.collections)
            log.info("Added sound %s to collection %r", sid, name)

    def remove_from_collection(self, name: str, sound: dict[str, Any]) -> None:
        if name not in self.collections:
            return
        sid = _sound_id(sound)
        before = len(self.collections[name])
        self.collections[name] = [s for s in self.collections[name] if _sound_id(s) != sid]
        if len(self.collections[name]) != before:
            self._save(self.collections_path, self.collections)
            log.info("Removed sound %s from collection %r", sid, name)

    def is_in_collection(self, name: str, sound: dict[str, Any]) -> bool:
        sid = _sound_id(sound)
        return any(_sound_id(s) == sid for s in self.collections.get(name, []))

    def collections_for(self, sound: dict[str, Any]) -> list[str]:
        sid = _sound_id(sound)
        return [name for name, items in self.collections.items() if any(_sound_id(s) == sid for s in items)]

    # ----- queries -----------------------------------------------------
    def sounds_for(self, source: str) -> list[dict[str, Any]]:
        if source == HISTORY_KEY:
            return list(self.history)
        return list(self.collections.get(source, []))
