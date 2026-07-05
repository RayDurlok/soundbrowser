#!/usr/bin/env python3

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from resolve_freesound_browser.logging_setup import LOGGER_NAME, install_excepthook, setup_logging
from resolve_freesound_browser.store import HISTORY_KEY, LibraryStore

from PySide6.QtCore import QMimeData, QObject, QPoint, QRect, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDrag,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStyle,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:
    QAudioOutput = None
    QMediaPlayer = None


APP_NAME = "Resolve Freesound Browser"
API_BASE = "https://freesound.org/apiv2"
DEFAULT_PAGE_SIZE = 30

# Label -> Freesound APIv2 "sort" value. "score" is the default relevance sort.
SORT_OPTIONS: list[tuple[str, str]] = [
    ("Relevance", "score"),
    ("Rating", "rating_desc"),
    ("Most downloaded", "downloads_desc"),
    ("Newest", "created_desc"),
    ("Duration (short first)", "duration_asc"),
    ("Duration (long first)", "duration_desc"),
]
DEFAULT_SORT = "score"
SEARCH_FIELDS = ",".join(
    [
        "id",
        "name",
        "username",
        "license",
        "url",
        "tags",
        "description",
        "created",
        "type",
        "channels",
        "filesize",
        "duration",
        "samplerate",
        "bitdepth",
        "previews",
        "images",
        "download",
        "num_downloads",
        "avg_rating",
    ]
)


def platform_config_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "Resolve Freesound Browser"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Resolve Freesound Browser"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "resolve-freesound-browser"


def platform_cache_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "Resolve Freesound Browser" / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "Resolve Freesound Browser"
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "resolve-freesound-browser"


CONFIG_DIR = platform_config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"
IMAGE_CACHE_DIR = platform_cache_dir() / "images"
PREVIEW_CACHE_DIR = platform_cache_dir() / "previews"
CLIP_CACHE_DIR = platform_cache_dir() / "clips"
LOG_DIR = platform_cache_dir() / "logs"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Freesound Downloads"
RESOURCES_DIR = Path(__file__).resolve().parents[1] / "resources"

log = logging.getLogger(LOGGER_NAME)


def load_config() -> dict[str, Any]:
    defaults = {
        "api_key": os.environ.get("FREESOUND_API_KEY", ""),
        "download_dir": str(DEFAULT_DOWNLOAD_DIR),
        "cc0_only": True,
        "page_size": DEFAULT_PAGE_SIZE,
        "volume": 80,
        "sort": DEFAULT_SORT,
        "source": "freesound",
        "openverse_filters": {},
        "openverse_client_id": "",
        "openverse_client_secret": "",
    }
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.info("No config file at %s; using defaults", CONFIG_PATH)
        return defaults
    except Exception:
        log.warning("Failed to read config at %s; using defaults", CONFIG_PATH, exc_info=True)
        return defaults
    defaults.update({key: data[key] for key in defaults if key in data})
    defaults["page_size"] = max(DEFAULT_PAGE_SIZE, int(defaults.get("page_size") or DEFAULT_PAGE_SIZE))
    if os.environ.get("FREESOUND_API_KEY"):
        defaults["api_key"] = os.environ["FREESOUND_API_KEY"]
    log.debug(
        "Loaded config from %s (api_key=%s, download_dir=%s, cc0_only=%s)",
        CONFIG_PATH,
        "set" if defaults.get("api_key") else "missing",
        defaults.get("download_dir"),
        defaults.get("cc0_only"),
    )
    return defaults


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    log.debug("Saved config to %s", CONFIG_PATH)


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[^\w.\- ]+", "_", value, flags=re.UNICODE).strip()
    value = re.sub(r"\s+", " ", value)
    return value[:120] or "sound"


def format_duration(seconds: Any) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return ""
    minutes = int(value // 60)
    remainder = int(round(value - minutes * 60))
    return f"{minutes}:{remainder:02d}"


def format_size(value: Any) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return ""
    units = ["B", "KB", "MB", "GB"]
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.1f} {units[unit]}"


def preview_url(sound: dict[str, Any]) -> str:
    previews = sound.get("previews") or {}
    return (
        previews.get("preview-hq-mp3")
        or previews.get("preview-lq-mp3")
        or previews.get("preview-hq-ogg")
        or previews.get("preview-lq-ogg")
        or ""
    )


def waveform_url(sound: dict[str, Any]) -> str:
    images = sound.get("images") or {}
    return images.get("waveform_l") or images.get("waveform_m") or ""


def extension_from_url(url: str, fallback: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix and len(suffix) <= 8:
        return suffix
    return fallback


def auth_download_bytes(url: str, api_key: str = "", authorization: str = "") -> bytes:
    headers = {"User-Agent": "ResolveFreesoundBrowser/0.2"}
    if authorization:
        headers["Authorization"] = authorization
    elif api_key:
        headers["Authorization"] = f"Token {api_key}"
    request = urllib.request.Request(url, headers=headers)
    log.debug("GET %s (auth=%s)", url, bool(authorization or api_key))
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:500]
        except Exception:
            pass
        log.error("HTTP %s for %s: %s", exc.code, url, body)
        raise
    except urllib.error.URLError as exc:
        log.error("Network error for %s: %s", url, exc.reason)
        raise
    log.debug("GET %s -> %d bytes in %.0f ms", url, len(data), (time.perf_counter() - started) * 1000)
    return data


def request_json(url: str, api_key: str = "", authorization: str = "") -> dict[str, Any]:
    return json.loads(auth_download_bytes(url, api_key, authorization).decode("utf-8"))


def sound_id(sound: dict[str, Any]) -> str:
    return str(sound.get("id", "sound"))


def sound_tags(sound: dict[str, Any], limit: int = 6) -> str:
    tags = list(sound.get("tags") or [])
    return ", ".join(tags[:limit])


def sound_duration_seconds(sound: dict[str, Any]) -> float:
    try:
        return max(0.0, float(sound.get("duration") or 0.0))
    except (TypeError, ValueError):
        return 0.0


AUDIO_NAME_EXTS = {
    ".wav", ".wave", ".aif", ".aiff", ".aifc", ".flac", ".mp3", ".ogg",
    ".oga", ".opus", ".m4a", ".aac", ".wma", ".au", ".raw",
}


def sound_stem(sound: dict[str, Any]) -> str:
    """The sound's display name without its original audio extension."""
    name = str(sound.get("name", "sound"))
    lower = name.lower()
    for ext in AUDIO_NAME_EXTS:
        if lower.endswith(ext) and len(name) > len(ext):
            name = name[: -len(ext)]
            break
    return sanitize_filename(name) or "sound"


def clean_filename(sound: dict[str, Any], suffix: str) -> str:
    return f"{sound_stem(sound)}{suffix}"


def rating_stars(value: Any, maximum: int = 5) -> str:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return ""
    if rating <= 0:
        return ""
    filled = max(0, min(maximum, int(round(rating))))
    return "★" * filled + "☆" * (maximum - filled)


OPENVERSE_SOURCE_LABELS = {
    "jamendo": "Jamendo",
    "wikimedia_audio": "Wikimedia",
    "freesound": "Freesound",
}


def source_label(sound: dict[str, Any]) -> str:
    """Human-readable provider name for an Openverse sound (else empty)."""
    source = sound.get("_source") or ""
    if not source:
        return ""
    return OPENVERSE_SOURCE_LABELS.get(source, source.replace("_", " ").title())


def selection_is_full(start_fraction: float, end_fraction: float) -> bool:
    return start_fraction <= 0.001 and end_fraction >= 0.999


def ffmpeg_binary() -> str | None:
    """Locate the ffmpeg executable, incl. common Homebrew paths on macOS
    (GUI apps launched from Finder/Dock don't inherit the shell PATH)."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    if sys.platform == "darwin":
        for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
            if os.path.exists(candidate):
                return candidate
    return None


def trim_preview_file(source: Path, sound: dict[str, Any], start_fraction: float, end_fraction: float, target_dir: Path | None = None) -> Path:
    if selection_is_full(start_fraction, end_fraction):
        return source
    ffmpeg = ffmpeg_binary()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for trimmed drag/download/import.")

    duration = sound_duration_seconds(sound)
    if duration <= 0:
        raise RuntimeError("Cannot trim this sound because its duration is unknown.")

    start = max(0.0, min(duration, duration * start_fraction))
    end = max(start + 0.01, min(duration, duration * end_fraction))
    suffix = source.suffix or ".mp3"
    filename = clean_filename(sound, suffix)
    if target_dir is not None:
        # Download folder: cleanly named file, overwrite so the folder always
        # reflects the sound and range you just exported.
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
    else:
        # Cache: uniqueness comes from the id+range subfolder, so the file
        # itself keeps the clean drag/drop name.
        base_dir = CLIP_CACHE_DIR / f"{sound_id(sound)}_{int(start * 1000)}_{int(end * 1000)}"
        base_dir.mkdir(parents=True, exist_ok=True)
        target = base_dir / filename
        if target.exists() and target.stat().st_size > 0:
            log.debug("Trim cache hit for sound %s (%s)", sound_id(sound), target)
            return target

    log.info("Trimming sound %s to [%.3f, %.3f]s -> %s", sound_id(sound), start, end, target)
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(source),
        "-c",
        "copy",
        str(target),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as exc:
        log.warning("ffmpeg stream copy failed (%s); retrying with re-encode", (exc.stderr or "").strip())
        command = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(source),
            str(target),
        ]
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as exc2:
            log.error("ffmpeg re-encode failed for sound %s: %s", sound_id(sound), (exc2.stderr or "").strip())
            raise
    return target


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class FunctionWorker(QRunnable):
    def __init__(self, fn, *, label: str = ""):
        super().__init__()
        self.fn = fn
        self.label = label or getattr(fn, "__name__", "worker")
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.fn())
        except Exception as exc:
            log.exception("Worker '%s' failed", self.label)
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class FreesoundClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def update_api_key(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, cc0_only: bool, page_size: int, sort: str = DEFAULT_SORT) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("Add a Freesound API key in Settings first.")
        params = {
            "query": query,
            "page_size": str(page_size),
            "fields": SEARCH_FIELDS,
            "sort": sort or DEFAULT_SORT,
        }
        if cc0_only:
            params["filter"] = 'license:"Creative Commons 0"'
        url = f"{API_BASE}/search/?{urllib.parse.urlencode(params)}"
        log.info("Search: query=%r cc0_only=%s sort=%s page_size=%d", query, cc0_only, sort, page_size)
        response = request_json(url, self.api_key)
        log.info("Search returned %s matches (%d in page)", response.get("count"), len(response.get("results", [])))
        return response

    def fetch_url(self, url: str) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("Add a Freesound API key in Settings first.")
        log.debug("Fetching page %s", url)
        return request_json(url, self.api_key)

    def fetch_more(self, url: str) -> dict[str, Any]:
        return self.fetch_url(url)

    def preview_cache_path(self, sound: dict[str, Any], target_dir: Path | None = None) -> Path:
        url = preview_url(sound)
        suffix = extension_from_url(url, ".mp3")
        filename = clean_filename(sound, suffix)
        if target_dir is not None:
            return target_dir / filename
        # Cache: keep the clean drag/drop name, get uniqueness from the id folder.
        return PREVIEW_CACHE_DIR / sound_id(sound) / filename

    def ensure_preview_file(self, sound: dict[str, Any], target_dir: Path | None = None) -> Path:
        url = preview_url(sound)
        if not url:
            raise RuntimeError("This sound has no preview URL.")
        target = self.preview_cache_path(sound, target_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target_dir is not None:
            # Download folder: always write a fresh, cleanly-named copy.
            log.info("Downloading preview for sound %s -> %s", sound_id(sound), target)
            target.write_bytes(auth_download_bytes(url, self.api_key))
        elif not target.exists() or target.stat().st_size == 0:
            log.info("Downloading preview for sound %s -> %s", sound_id(sound), target)
            target.write_bytes(auth_download_bytes(url, self.api_key))
        else:
            log.debug("Preview cache hit for sound %s (%s)", sound_id(sound), target)
        return target

    def download_waveform(self, sound: dict[str, Any]) -> Path:
        url = waveform_url(sound)
        if not url:
            raise RuntimeError("This sound has no waveform image.")
        suffix = extension_from_url(url, ".png")
        IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        target = IMAGE_CACHE_DIR / f"{sound_id(sound)}_waveform{suffix}"
        if not target.exists() or target.stat().st_size == 0:
            log.debug("Downloading waveform for sound %s", sound_id(sound))
            target.write_bytes(auth_download_bytes(url, self.api_key))
        return target


OPENVERSE_BASE = "https://api.openverse.org/v1"

# (label, api value) for the Openverse filter UI.
OPENVERSE_SOURCES = [
    ("Freesound", "freesound"),
    ("Jamendo", "jamendo"),
    ("Wikimedia Commons", "wikimedia_audio"),
]
OPENVERSE_CATEGORIES = [
    ("Hörbuch", "audiobook"),
    ("Musik", "music"),
    ("News", "news"),
    ("Podcast", "podcast"),
    ("Aussprache", "pronunciation"),
    ("Soundeffekte", "sound_effect"),
]
OPENVERSE_LICENSES = [
    ("Public Domain Mark", "pdm"),
    ("CC0", "cc0"),
    ("CC BY", "by"),
]
# Freesound is excluded by default so Openverse only adds NEW content (no dupes).
OPENVERSE_DEFAULT_SOURCES = ["jamendo", "wikimedia_audio"]
OPENVERSE_DEFAULT_LICENSES = ["pdm", "cc0", "by"]
# Anonymous Openverse requests are capped at page_size 20; a token lifts this.
OPENVERSE_ANON_PAGE_SIZE = 20
OPENVERSE_AUTH_PAGE_SIZE = 50


def normalize_openverse_sound(raw: dict[str, Any]) -> dict[str, Any]:
    """Map an Openverse audio result onto the app's internal sound shape."""
    tags = [t.get("name") for t in (raw.get("tags") or []) if isinstance(t, dict) and t.get("name")]
    duration_ms = raw.get("duration") or 0
    try:
        duration_s = float(duration_ms) / 1000.0
    except (TypeError, ValueError):
        duration_s = 0.0
    filetype = (raw.get("filetype") or "").lower()
    if filetype.startswith("mp3"):  # Jamendo uses codes like mp31/mp32
        filetype = "mp3"
    return {
        "id": raw.get("id"),
        "name": raw.get("title") or "Untitled",
        "username": raw.get("creator") or "",
        "duration": duration_s,
        "type": filetype,
        "filesize": raw.get("filesize"),
        "samplerate": raw.get("sample_rate"),
        "previews": {"preview-hq-mp3": raw.get("url") or ""},
        "url": raw.get("foreign_landing_url") or raw.get("url") or "",
        "tags": tags,
        "avg_rating": 0,
        "num_downloads": "",
        "created": (raw.get("indexed_on") or "")[:10],
        "description": raw.get("attribution") or "",
        "_provider": "openverse",
        "_license": (raw.get("license") or "").upper(),
        "_license_url": raw.get("license_url") or "",
        "_source": raw.get("source") or "",
        "_waveform_url": raw.get("waveform") or "",
    }


def render_waveform_png(peaks: list[float], target: Path, width: int = 780, height: int = 300) -> None:
    """Draw amplitude peaks (0..1) as a Freesound-style filled waveform PNG.

    Uses QImage/QPainter (safe off the GUI thread) so the row/detail views can
    load it exactly like a downloaded Freesound waveform image.
    """
    from PySide6.QtGui import QImage

    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)

    gradient = QLinearGradient(0, 0, width, 0)
    gradient.setColorAt(0.0, QColor("#8ac926"))
    gradient.setColorAt(0.5, QColor("#f0b429"))
    gradient.setColorAt(1.0, QColor("#e8532b"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))

    count = len(peaks)
    center = height / 2.0
    if count > 0:
        for x in range(width):
            peak = peaks[int(x * count / width)]
            try:
                amp = max(0.0, min(1.0, float(peak)))
            except (TypeError, ValueError):
                amp = 0.0
            bar_h = max(1.0, amp * (height - 6))
            painter.drawRect(QRectF(x, center - bar_h / 2.0, 1.0, bar_h))
    painter.end()
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(target), "PNG")


class OpenverseClient:
    """Openverse audio provider (Jamendo, Wikimedia, …). Anonymous by default.

    Anonymous requests are capped at page_size 20. Supplying a client_id /
    client_secret (registered once at api.openverse.org) fetches a bearer token
    that lifts the page-size cap and raises the rate limits.
    """

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = ""
        self._token_expiry = 0.0

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        if (client_id, client_secret) != (self.client_id, self.client_secret):
            self.client_id = client_id
            self.client_secret = client_secret
            self._token = ""
            self._token_expiry = 0.0

    def _bearer(self) -> str:
        """Return an Authorization header value, refreshing the token if needed."""
        if not (self.client_id and self.client_secret):
            return ""
        if self._token and time.time() < self._token_expiry - 30:
            return f"Bearer {self._token}"
        try:
            body = urllib.parse.urlencode({
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            }).encode()
            request = urllib.request.Request(
                f"{OPENVERSE_BASE}/auth_tokens/token/",
                data=body,
                headers={
                    "User-Agent": "ResolveFreesoundBrowser/0.2",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode())
            self._token = data.get("access_token", "")
            self._token_expiry = time.time() + float(data.get("expires_in") or 0)
            log.info("Obtained Openverse access token (expires in %ss)", data.get("expires_in"))
        except Exception:
            log.warning("Failed to obtain Openverse token; falling back to anonymous", exc_info=True)
            self._token = ""
        return f"Bearer {self._token}" if self._token else ""

    def _page_size(self, requested: int) -> int:
        limit = OPENVERSE_AUTH_PAGE_SIZE if (self.client_id and self.client_secret) else OPENVERSE_ANON_PAGE_SIZE
        return max(1, min(requested, limit))

    def build_search_url(self, query: str, filters: dict[str, Any], page_size: int, page: int = 1) -> str:
        params: dict[str, str] = {
            "q": query,
            "page_size": str(self._page_size(page_size)),
            "page": str(page),
        }
        if filters.get("sources"):
            params["source"] = ",".join(filters["sources"])
        if filters.get("categories"):
            params["category"] = ",".join(filters["categories"])
        if filters.get("licenses"):
            params["license"] = ",".join(filters["licenses"])
        if filters.get("license_type"):
            params["license_type"] = ",".join(filters["license_type"])
        return f"{OPENVERSE_BASE}/audio/?{urllib.parse.urlencode(params)}"

    def search(self, query: str, filters: dict[str, Any], page_size: int) -> dict[str, Any]:
        url = self.build_search_url(query, filters, page_size, page=1)
        log.info("Openverse search: query=%r filters=%s", query, filters)
        return self.fetch_more(url)

    def fetch_more(self, url: str) -> dict[str, Any]:
        raw = request_json(url, authorization=self._bearer())
        results = [normalize_openverse_sound(r) for r in raw.get("results", [])]
        page = int(raw.get("page") or 1)
        page_count = int(raw.get("page_count") or 1)
        next_url = None
        if page < page_count:
            parts = urllib.parse.urlsplit(url)
            query = dict(urllib.parse.parse_qsl(parts.query))
            query["page"] = str(page + 1)
            next_url = urllib.parse.urlunsplit(
                parts._replace(query=urllib.parse.urlencode(query))
            )
        log.info("Openverse returned %s matches (%d in page)", raw.get("result_count"), len(results))
        return {"count": raw.get("result_count", len(results)), "results": results, "next": next_url}

    def preview_cache_path(self, sound: dict[str, Any], target_dir: Path | None = None) -> Path:
        url = preview_url(sound)
        suffix = extension_from_url(url, ".mp3")
        filename = clean_filename(sound, suffix)
        if target_dir is not None:
            return target_dir / filename
        return PREVIEW_CACHE_DIR / sound_id(sound) / filename

    def ensure_preview_file(self, sound: dict[str, Any], target_dir: Path | None = None) -> Path:
        url = preview_url(sound)
        if not url:
            raise RuntimeError("This sound has no audio URL.")
        target = self.preview_cache_path(sound, target_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target_dir is not None or not target.exists() or target.stat().st_size == 0:
            log.info("Downloading Openverse audio %s -> %s", sound_id(sound), target)
            target.write_bytes(auth_download_bytes(url))  # public CDN, no auth
        return target

    def download_waveform(self, sound: dict[str, Any]) -> Path:
        peaks_url = sound.get("_waveform_url")
        if not peaks_url:
            raise RuntimeError("This sound has no waveform data.")
        IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        target = IMAGE_CACHE_DIR / f"ov_{sound_id(sound)}_waveform.png"
        if not target.exists() or target.stat().st_size == 0:
            log.debug("Rendering Openverse waveform for sound %s", sound_id(sound))
            raw = request_json(peaks_url, authorization=self._bearer())
            render_waveform_png(raw.get("points") or [], target)
        return target


def resolve_module_candidates() -> list[Path]:
    candidates = []
    env_api = os.environ.get("RESOLVE_SCRIPT_API")
    if env_api:
        candidates.append(Path(env_api) / "Modules")

    if os.name == "nt":
        program_data = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
        candidates.append(
            program_data
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Support"
            / "Developer"
            / "Scripting"
            / "Modules"
        )
    elif sys.platform == "darwin":
        candidates.append(
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
        )
    else:
        candidates.append(Path("/opt/resolve/Developer/Scripting/Modules"))

    return candidates


def get_resolve():
    for module_dir in resolve_module_candidates():
        module_path = module_dir / "DaVinciResolveScript.py"
        if module_path.exists() and str(module_dir) not in sys.path:
            log.debug("Using Resolve scripting module at %s", module_dir)
            sys.path.insert(0, str(module_dir))

    if sys.platform.startswith("linux"):
        os.environ.setdefault("RESOLVE_SCRIPT_API", "/opt/resolve/Developer/Scripting")
        os.environ.setdefault("RESOLVE_SCRIPT_LIB", "/opt/resolve/libs/Fusion/fusionscript.so")
    elif sys.platform == "darwin":
        os.environ.setdefault(
            "RESOLVE_SCRIPT_API",
            "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
        )
        os.environ.setdefault(
            "RESOLVE_SCRIPT_LIB",
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so",
        )
    elif os.name == "nt":
        program_data = os.environ.get("PROGRAMDATA", "C:\\ProgramData")
        os.environ.setdefault(
            "RESOLVE_SCRIPT_API",
            os.path.join(program_data, "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting"),
        )
        os.environ.setdefault(
            "RESOLVE_SCRIPT_LIB",
            "C:\\Program Files\\Blackmagic Design\\DaVinci Resolve\\fusionscript.dll",
        )

    module = importlib.import_module("DaVinciResolveScript")
    return module.scriptapp("Resolve")


def import_into_resolve(paths: list[Path]) -> int:
    log.info("Importing %d file(s) into Resolve: %s", len(paths), [str(p) for p in paths])
    try:
        resolve = get_resolve()
    except Exception:
        log.exception("Failed to load Resolve scripting module")
        raise RuntimeError("Could not load the Resolve scripting module. Is Resolve installed?")
    if not resolve:
        raise RuntimeError("Could not connect to Resolve. Is Resolve running with scripting enabled?")
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject() if project_manager else None
    if not project:
        raise RuntimeError("Resolve has no current project.")
    media_pool = project.GetMediaPool()
    imported = media_pool.ImportMedia([str(path) for path in paths])
    if not imported:
        raise RuntimeError("Resolve did not import the selected file.")
    log.info("Resolve imported %d file(s)", len(imported))
    return len(imported)


def ffmpeg_available() -> bool:
    return ffmpeg_binary() is not None


def ffmpeg_install_command() -> list[str] | None:
    """Best-effort privileged install command for the current OS, or None."""
    if sys.platform.startswith("linux"):
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return None
        if shutil.which("dnf"):
            return [pkexec, "dnf", "install", "-y", "ffmpeg-free"]
        if shutil.which("apt-get"):
            return [pkexec, "sh", "-c", "apt-get update && apt-get install -y ffmpeg"]
        if shutil.which("pacman"):
            return [pkexec, "pacman", "-S", "--noconfirm", "ffmpeg"]
        if shutil.which("zypper"):
            return [pkexec, "zypper", "install", "-y", "ffmpeg"]
        return None
    if os.name == "nt":
        if shutil.which("winget"):
            return [
                "winget", "install", "--silent",
                "--accept-package-agreements", "--accept-source-agreements",
                "--id", "Gyan.FFmpeg",
            ]
        return None
    if sys.platform == "darwin":
        brew = shutil.which("brew") or next(
            (p for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if os.path.exists(p)), None
        )
        if brew:
            return [brew, "install", "ffmpeg"]
        return None
    return None


def run_ffmpeg_install(command: list[str]) -> str:
    log.info("Installing ffmpeg via: %s", " ".join(command))
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = (result.stdout or "").strip()
    log.info("ffmpeg install finished (exit=%s)", result.returncode)
    if result.returncode != 0:
        raise RuntimeError(output or f"Installer exited with code {result.returncode}.")
    if not ffmpeg_available():
        raise RuntimeError("Installer finished but ffmpeg is still not on PATH.")
    return output


def make_app_icon() -> QIcon:
    """The app logo (transparent PNG), falling back to a drawn placeholder."""
    logo = RESOURCES_DIR / "icon.png"
    if logo.exists():
        icon = QIcon(str(logo))
        if not icon.isNull():
            return icon

    size = 256
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    radius = size * 0.22
    card = QPainterPath()
    card.addRoundedRect(0, 0, size, size, radius, radius)
    background = QLinearGradient(0, 0, 0, size)
    background.setColorAt(0.0, QColor("#1b2026"))
    background.setColorAt(1.0, QColor("#0f1114"))
    painter.fillPath(card, background)

    bars = QLinearGradient(0, 0, size, 0)
    bars.setColorAt(0.0, QColor("#8ac926"))
    bars.setColorAt(0.5, QColor("#f0b429"))
    bars.setColorAt(1.0, QColor("#f0b429"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(bars))

    heights = [0.30, 0.55, 0.82, 0.98, 0.62, 0.88, 0.42, 0.70, 0.34]
    margin = size * 0.18
    usable = size - 2 * margin
    bar_w = usable / (len(heights) * 2 - 1)
    center = size / 2
    for i, height in enumerate(heights):
        x = margin + i * bar_w * 2
        bar_h = height * (size * 0.5)
        painter.drawRoundedRect(
            QRect(int(x), int(center - bar_h / 2), int(round(bar_w)), int(bar_h)),
            bar_w * 0.4,
            bar_w * 0.4,
        )
    painter.end()
    return QIcon(pixmap)


def make_settings_icon() -> QIcon:
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(size / 2, size / 2)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#d8dee5"))
    for _ in range(8):
        painter.drawRoundedRect(QRect(-4, -28, 8, 12), 3, 3)
        painter.rotate(45)

    painter.setBrush(QColor("#d8dee5"))
    painter.drawEllipse(QPoint(0, 0), 20, 20)
    painter.setBrush(QColor("#272c33"))
    painter.drawEllipse(QPoint(0, 0), 9, 9)
    painter.end()
    return QIcon(pixmap)


class SettingsDialog(QDialog):
    def __init__(self, config: dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Freesound Settings")
        self.api_key = QLineEdit(config.get("api_key", ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.download_dir = QLineEdit(config.get("download_dir", str(DEFAULT_DOWNLOAD_DIR)))
        browse = QPushButton("Browse")
        browse.clicked.connect(self.choose_download_dir)

        dir_row = QHBoxLayout()
        dir_row.addWidget(self.download_dir, 1)
        dir_row.addWidget(browse)

        self.ov_client_id = QLineEdit(config.get("openverse_client_id", ""))
        self.ov_client_secret = QLineEdit(config.get("openverse_client_secret", ""))
        self.ov_client_secret.setEchoMode(QLineEdit.Password)
        ov_hint = QLabel(
            'Optional — lifts Openverse\'s anonymous page-size/rate limit. '
            'Register once at <a href="https://api.openverse.org/v1/#tag/auth">api.openverse.org</a> '
            "(name, email → client ID/secret; confirm the email)."
        )
        ov_hint.setOpenExternalLinks(True)
        ov_hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Freesound API key", self.api_key)
        form.addRow("Download folder", dir_row)
        form.addRow("Openverse client ID", self.ov_client_id)
        form.addRow("Openverse client secret", self.ov_client_secret)
        form.addRow("", ov_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def choose_download_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose download folder", self.download_dir.text())
        if selected:
            self.download_dir.setText(selected)


class DragFileButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path: Path | None = None
        self.setText("Drag to Resolve")
        self.setToolTip("Drag the cached preview file into Resolve, the Media Pool, or a folder.")
        self.setEnabled(False)

    def set_file_path(self, path: Path | None) -> None:
        self.file_path = Path(path) if path else None
        self.setEnabled(bool(self.file_path and self.file_path.exists()))
        self.setText("")

    def mouseMoveEvent(self, event) -> None:
        if not self.file_path or not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.file_path))])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class SoundRowWidget(QWidget):
    def __init__(self, sound: dict[str, Any], parent=None):
        super().__init__(parent)
        self.sound = sound
        self.waveform = QLabel()
        self.waveform.setFixedSize(170, 46)
        self.waveform.setAlignment(Qt.AlignCenter)
        self.waveform.setObjectName("RowWaveform")
        self.waveform.setText("waveform")

        title = QLabel(str(sound.get("name", "Untitled")))
        title.setObjectName("RowTitle")
        title.setWordWrap(False)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        info = "  ".join(
            part
            for part in [
                format_duration(sound.get("duration")),
                str(sound.get("type", "")).upper(),
            ]
            if part
        )
        meta_html = f'<span style="color:#99a3ad">{info}</span>'
        source = source_label(sound)
        stars = rating_stars(sound.get("avg_rating"))
        if source:  # Openverse: show the provider instead of a (missing) rating
            meta_html += f'&nbsp;&nbsp;<span style="color:#6cb6ff">{source}</span>'
        elif stars:
            meta_html += f'&nbsp;&nbsp;<span style="color:#f0b429">{stars}</span>'
        meta = QLabel()
        meta.setObjectName("RowMeta")
        meta.setTextFormat(Qt.RichText)
        meta.setText(meta_html)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        text_layout.addWidget(title)
        text_layout.addWidget(meta)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.waveform, 0)

    def set_waveform(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.waveform.setText("")
            return
        self.waveform.setPixmap(
            pixmap.scaled(
                self.waveform.size(),
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation,
            )
        )


class SoundListWidget(QListWidget):
    dragStarted = Signal()
    dragFinished = Signal(str)

    def __init__(self, file_provider, parent=None):
        super().__init__(parent)
        self.file_provider = file_provider
        self.setDragEnabled(True)

    def startDrag(self, supported_actions) -> None:
        path = self.file_provider()
        if not path or not Path(path).exists():
            return
        self.dragStarted.emit()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)
        self.dragFinished.emit(str(path))


class WaveformEditor(QWidget):
    selectionChanged = Signal(float, float)
    seekRequested = Signal(float)
    dragStarted = Signal()
    dragFinished = Signal(str)

    def __init__(self, file_provider, parent=None):
        super().__init__(parent)
        self.file_provider = file_provider
        self.pixmap = QPixmap()
        self.in_fraction = 0.0
        self.out_fraction = 1.0
        self.playhead_fraction = 0.0
        self.active_handle: str | None = None
        self.drag_start_pos: QPoint | None = None
        self.setMinimumHeight(176)
        self.setMouseTracking(True)
        self.setAcceptDrops(False)
        self.setObjectName("LargeWaveform")

    def set_waveform(self, path: Path | None) -> None:
        self.pixmap = QPixmap(str(path)) if path else QPixmap()
        self.update()

    def reset_selection(self) -> None:
        self.in_fraction = 0.0
        self.out_fraction = 1.0
        self.playhead_fraction = 0.0
        self.update()

    def set_playhead(self, fraction: float) -> None:
        self.playhead_fraction = max(0.0, min(1.0, fraction))
        self.update()

    def waveform_rect(self) -> QRect:
        margin = 12
        return self.rect().adjusted(margin, margin, -margin, -margin)

    def x_for_fraction(self, fraction: float) -> int:
        rect = self.waveform_rect()
        return int(rect.left() + max(0.0, min(1.0, fraction)) * rect.width())

    def fraction_for_x(self, x: int) -> float:
        rect = self.waveform_rect()
        if rect.width() <= 0:
            return 0.0
        return max(0.0, min(1.0, (x - rect.left()) / rect.width()))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#181c20"))

        rect = self.waveform_rect()
        painter.setPen(QPen(QColor("#2e353d"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 7, 7)

        if self.pixmap.isNull():
            painter.setPen(QColor("#8a949f"))
            painter.drawText(rect, Qt.AlignCenter, "Select a result")
        else:
            # Stretch the waveform across the full editor width so that the
            # x-axis maps linearly to time: In=0% and Out=100% line up with the
            # actual start and end of the audio (no letterboxing / clipping).
            scaled = self.pixmap.scaled(rect.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(rect, 7, 7)
            painter.setClipPath(clip)
            painter.drawPixmap(rect.topLeft(), scaled)
            painter.restore()

        in_x = self.x_for_fraction(self.in_fraction)
        out_x = self.x_for_fraction(self.out_fraction)
        play_x = self.x_for_fraction(self.playhead_fraction)

        painter.fillRect(QRect(rect.left(), rect.top(), max(0, in_x - rect.left()), rect.height()), QColor(0, 0, 0, 120))
        painter.fillRect(QRect(out_x, rect.top(), max(0, rect.right() - out_x), rect.height()), QColor(0, 0, 0, 120))
        painter.fillRect(QRect(in_x, rect.top(), max(0, out_x - in_x), rect.height()), QColor(240, 180, 41, 24))

        handle_color = QColor("#f0b429")
        painter.setPen(QPen(handle_color, 3))
        painter.drawLine(in_x, rect.top() + 2, in_x, rect.bottom() - 2)
        painter.drawLine(out_x, rect.top() + 2, out_x, rect.bottom() - 2)
        painter.setBrush(QBrush(handle_color))
        painter.drawPolygon([
            QPoint(in_x - 7, rect.top() + 1),
            QPoint(in_x + 7, rect.top() + 1),
            QPoint(in_x, rect.top() + 12),
        ])
        painter.drawPolygon([
            QPoint(out_x - 7, rect.top() + 1),
            QPoint(out_x + 7, rect.top() + 1),
            QPoint(out_x, rect.top() + 12),
        ])

        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(play_x, rect.top() + 1, play_x, rect.bottom() - 1)

        painter.setPen(QColor("#c9d1d9"))
        painter.drawText(rect.adjusted(8, 8, -8, -8), Qt.AlignLeft | Qt.AlignBottom, "In")
        painter.drawText(rect.adjusted(8, 8, -8, -8), Qt.AlignRight | Qt.AlignBottom, "Out")

    def nearest_handle(self, pos: QPoint) -> str | None:
        if abs(pos.x() - self.x_for_fraction(self.in_fraction)) <= 10:
            return "in"
        if abs(pos.x() - self.x_for_fraction(self.out_fraction)) <= 10:
            return "out"
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.active_handle = self.nearest_handle(event.pos())
            self.drag_start_pos = event.pos()
            if self.active_handle is None and self.waveform_rect().contains(event.pos()):
                fraction = self.fraction_for_x(event.pos().x())
                self.playhead_fraction = fraction
                self.update()
                self.seekRequested.emit(fraction)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.active_handle:
            fraction = self.fraction_for_x(event.pos().x())
            if self.active_handle == "in":
                self.in_fraction = min(fraction, self.out_fraction - 0.01)
            else:
                self.out_fraction = max(fraction, self.in_fraction + 0.01)
            self.selectionChanged.emit(self.in_fraction, self.out_fraction)
            self.update()
            return

        if event.buttons() & Qt.LeftButton and self.drag_start_pos:
            if (event.pos() - self.drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
                path = self.file_provider()
                if path and Path(path).exists():
                    self.dragStarted.emit()
                    mime = QMimeData()
                    mime.setUrls([QUrl.fromLocalFile(str(path))])
                    drag = QDrag(self)
                    drag.setMimeData(mime)
                    drag.exec(Qt.CopyAction)
                    self.dragFinished.emit(str(path))
                self.drag_start_pos = None
                return

        handle = self.nearest_handle(event.pos())
        if handle:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.active_handle:
            self.selectionChanged.emit(self.in_fraction, self.out_fraction)
        self.active_handle = None
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)


class FlowLayout(QLayout):
    """A layout that lays widgets left-to-right and wraps to new rows as needed."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)
        self._items: list = []

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class FreesoundBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.client = FreesoundClient(self.config["api_key"])
        self.openverse = OpenverseClient(
            self.config.get("openverse_client_id", ""),
            self.config.get("openverse_client_secret", ""),
        )
        self.active_source = self.config.get("source", "freesound")
        self.results_client = self.client
        ovf = self.config.get("openverse_filters", {})
        self.ov_sources = set(ovf.get("sources", OPENVERSE_DEFAULT_SOURCES))
        self.ov_categories = set(ovf.get("categories", []))
        self.ov_licenses = set(ovf.get("licenses", OPENVERSE_DEFAULT_LICENSES))
        self.ov_modify = bool(ovf.get("modify", False))
        self._ov_dirty = False
        self.store = LibraryStore(CONFIG_DIR)
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(8)
        # Keep worker objects alive until they finish. QThreadPool auto-deletes a
        # QRunnable right after run(), which can destroy the WorkerSignals object
        # before its queued result/finished events are delivered on the main
        # thread (dropping e.g. the done_handler that clears the busy state).
        self._active_workers: set[FunctionWorker] = set()
        self.current_sound: dict[str, Any] | None = None
        self.current_preview_file: Path | None = None
        self.current_waveform_file: Path | None = None
        self.sound_widgets: dict[str, SoundRowWidget] = {}
        self.library_widgets: dict[str, SoundRowWidget] = {}
        self.active_list: SoundListWidget | None = None
        self.next_url: str | None = None
        self.total_matches = 0
        self.loading_search = False
        self.loading_more = False
        self.results_query = ""
        self.library_filter = ""
        self._syncing_query = False
        self.cached_preview_by_id: dict[str, Path] = {}
        self.cached_clip_by_key: dict[tuple[str, int, int], Path] = {}
        self.current_clip_file: Path | None = None
        self.selection_start = 0.0
        self.selection_end = 1.0
        self.manual_start_fraction: float | None = None
        self._pending_seek_ms = 0
        self._apply_seek = False
        self._pending_play: tuple[str, float] | None = None

        self.player = None
        self.audio_output = None
        if QMediaPlayer is not None and QAudioOutput is not None:
            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_output)
            self.audio_output.setVolume(int(self.config["volume"]) / 100.0)
            self.player.errorOccurred.connect(self.media_error)
            self.player.positionChanged.connect(self.update_playhead_from_position)
            self.player.playbackStateChanged.connect(self.on_playback_state_changed)
            self.player.mediaStatusChanged.connect(self.on_media_status_changed)

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(40)
        self.playback_timer.timeout.connect(self.stop_at_selection_end)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        self.resize(1240, 780)
        self.build_actions()
        self.build_ui()
        self.apply_config_to_ui()
        if not ffmpeg_available():
            QTimer.singleShot(300, lambda: self.prompt_ffmpeg_install(force=False))

    def build_actions(self) -> None:
        self.settings_action = QAction("API key", self)
        self.settings_action.triggered.connect(self.open_settings)

        self.download_folder_action = QAction("Download folder…", self)
        self.download_folder_action.triggered.connect(self.choose_download_folder)

        self.install_ffmpeg_action = QAction("Install ffmpeg…", self)
        self.install_ffmpeg_action.triggered.connect(lambda: self.prompt_ffmpeg_install(force=True))

    def build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(12)

        self.search_bar = QWidget()
        header = QHBoxLayout(self.search_bar)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.query = QLineEdit()
        self.query.setObjectName("SearchBox")
        self.query.setPlaceholderText("Search Freesound")
        self.query.setMinimumWidth(240)
        self.query.setMaximumWidth(520)
        self.query.textChanged.connect(self.query_changed)
        self.query.returnPressed.connect(self.search)
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("PrimaryButton")
        self.search_button.clicked.connect(self.search)

        sort_label = QLabel("Sort")
        sort_label.setObjectName("FieldLabel")
        self.sort_combo = QComboBox()
        for label, value in SORT_OPTIONS:
            self.sort_combo.addItem(label, value)
        self.sort_combo.setToolTip("Order search results.")
        self.sort_combo.currentIndexChanged.connect(self.sort_changed)

        self.cc0_only = QCheckBox("CC0")
        self.cc0_only.setToolTip("Show only Creative Commons 0 sounds.")
        self.cc0_only.toggled.connect(self.save_filter_config)

        # Source selector (Freesound native vs Openverse aggregator).
        self.source_combo = QComboBox()
        self.source_combo.addItem("Freesound", "freesound")
        self.source_combo.addItem("Openverse", "openverse")
        idx = self.source_combo.findData(self.active_source)
        self.source_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.source_combo.setToolTip("Search Freesound, or Openverse (Jamendo, Wikimedia, …).")
        self.source_combo.currentIndexChanged.connect(self.source_changed)

        # Openverse filter dropdowns (shown only in Openverse mode).
        self.ov_filter_widgets: list[QWidget] = []
        self.ov_quelle_btn = self._make_filter_button(
            "Quelle", OPENVERSE_SOURCES, self.ov_sources, "sources")
        self.ov_kategorie_btn = self._make_category_button()
        self.ov_lizenz_btn = self._make_filter_button(
            "Lizenzen", OPENVERSE_LICENSES, self.ov_licenses, "licenses")
        self.ov_nutzung_btn = self._make_usage_button()
        self.ov_filter_widgets = [
            self.ov_quelle_btn, self.ov_kategorie_btn, self.ov_nutzung_btn, self.ov_lizenz_btn,
        ]

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setIcon(make_settings_icon())
        self.settings_button.setIconSize(QSize(15, 15))
        self.settings_button.setToolTip("Settings")
        self.settings_button.setPopupMode(QToolButton.InstantPopup)
        settings_menu = QMenu(self)
        settings_menu.addAction(self.settings_action)
        settings_menu.addAction(self.download_folder_action)
        settings_menu.addAction(self.install_ffmpeg_action)
        self.settings_button.setMenu(settings_menu)

        header.addWidget(self.query, 2)
        header.addWidget(self.search_button)
        header.addSpacing(8)
        header.addWidget(self.source_combo)
        header.addWidget(sort_label)
        header.addWidget(self.sort_combo)
        header.addWidget(self.cc0_only)
        for widget in self.ov_filter_widgets:
            header.addWidget(widget)
        header.addStretch(1)
        header.addWidget(self.settings_button)
        layout.addWidget(self.search_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setMinimumWidth(180)
        self.status_label.setMaximumWidth(420)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        layout.addWidget(splitter, 1)

        self.left_tabs = QTabWidget()
        self.left_tabs.setObjectName("LeftTabs")
        self.left_tabs.setCornerWidget(self.status_label, Qt.TopRightCorner)

        results_panel = QFrame()
        results_panel.setObjectName("ListPanel")
        list_layout = QVBoxLayout(results_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        self.results = SoundListWidget(self.current_drag_file)
        self.results.setObjectName("ResultsList")
        self.results.setUniformItemSizes(False)
        self.results.setSelectionMode(QListWidget.SingleSelection)
        self.results.itemSelectionChanged.connect(lambda: self.on_list_selection(self.results))
        self.results.itemDoubleClicked.connect(lambda _item: self.on_list_double(self.results))
        self.results.verticalScrollBar().valueChanged.connect(self.maybe_load_more)
        self.results.dragStarted.connect(self.record_current_use)
        self.results.dragFinished.connect(self.on_drag_finished)
        list_layout.addWidget(self.results, 1)
        self.left_tabs.addTab(results_panel, "Results")

        library_panel = QFrame()
        library_panel.setObjectName("ListPanel")
        library_layout = QVBoxLayout(library_panel)
        library_layout.setContentsMargins(10, 10, 10, 10)
        library_layout.setSpacing(8)

        # Always-visible source chips (Recently used + one per collection),
        # wrapping onto as many rows as needed.
        self.library_source_key = HISTORY_KEY
        self.source_group = QButtonGroup(self)
        self.source_group.setExclusive(True)
        self.source_host = QWidget()
        self.source_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.source_layout = FlowLayout(self.source_host, spacing=6)
        library_layout.addWidget(self.source_host)

        self.library_list = SoundListWidget(self.current_drag_file)
        self.library_list.setObjectName("ResultsList")
        self.library_list.setUniformItemSizes(False)
        self.library_list.setSelectionMode(QListWidget.SingleSelection)
        self.library_list.itemSelectionChanged.connect(lambda: self.on_list_selection(self.library_list))
        self.library_list.itemDoubleClicked.connect(lambda _item: self.on_list_double(self.library_list))
        self.library_list.dragStarted.connect(self.record_current_use)
        self.library_list.dragFinished.connect(self.on_drag_finished)
        library_layout.addWidget(self.library_list, 1)
        self.left_tabs.addTab(library_panel, "Library")

        self.left_tabs.currentChanged.connect(self.on_tab_changed)
        self.active_list = self.results
        splitter.addWidget(self.left_tabs)

        detail = QFrame()
        detail.setObjectName("Panel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(12)

        self.title = QLabel("No sound selected")
        self.title.setObjectName("DetailTitle")
        self.title.setWordWrap(True)
        detail_layout.addWidget(self.title)

        self.large_waveform = WaveformEditor(self.current_drag_file)
        self.large_waveform.selectionChanged.connect(self.selection_changed_on_waveform)
        self.large_waveform.seekRequested.connect(self.on_waveform_seek)
        self.large_waveform.dragStarted.connect(self.record_current_use)
        self.large_waveform.dragFinished.connect(self.on_drag_finished)
        detail_layout.addWidget(self.large_waveform)

        controls = QHBoxLayout()
        self.play_button = QPushButton("")
        self.play_button.clicked.connect(self.toggle_play_pause)
        self.next_button = QPushButton("")
        self.next_button.clicked.connect(self.play_next)
        self.volume_label = QLabel("80%")
        self.volume_label.setObjectName("VolumeLabel")
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(150)
        self.volume.valueChanged.connect(self.set_volume)
        self.download_button = QPushButton("")
        self.download_button.clicked.connect(self.download_selected_preview)
        self.collection_button = QToolButton()
        self.collection_button.setObjectName("CollectionButton")
        self.collection_button.setText("☆")
        self.collection_button.setPopupMode(QToolButton.InstantPopup)
        self.collection_menu = QMenu(self)
        self.collection_menu.aboutToShow.connect(self.build_collection_menu)
        self.collection_button.setMenu(self.collection_menu)
        self.import_button = QPushButton("")
        self.import_button.clicked.connect(self.import_selected_to_resolve)
        self.open_button = QPushButton("")
        self.open_button.clicked.connect(self.open_selected_page)

        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.next_button.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipForward))
        self.download_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.import_button.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.open_button.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        self.play_button.setToolTip("Play / pause (starts at the in-point or the cursor set by clicking the waveform)")
        self.next_button.setToolTip("Next result")
        self.download_button.setToolTip("Download selection")
        self.collection_button.setToolTip("Save to collection")
        self.import_button.setToolTip("Import selection to Resolve")
        self.open_button.setToolTip("Open Freesound page")

        for button in [
            self.play_button,
            self.next_button,
            self.download_button,
            self.collection_button,
            self.import_button,
            self.open_button,
        ]:
            button.setFixedWidth(52 if button is self.collection_button else 42)
            controls.addWidget(button)
        controls.addStretch(1)
        controls.addWidget(QLabel("Volume"))
        controls.addWidget(self.volume)
        controls.addWidget(self.volume_label)
        detail_layout.addLayout(controls)

        self.description = QPlainTextEdit()
        self.description.setObjectName("Description")
        self.description.setReadOnly(True)
        detail_layout.addWidget(self.description, 1)

        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        self.user_label = QLabel("")
        self.format_label = QLabel("")
        self.size_label = QLabel("")
        for pill in (self.user_label, self.format_label, self.size_label):
            pill.setObjectName("Pill")
            pill.setAlignment(Qt.AlignCenter)
            pill.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            info_row.addWidget(pill, 1)
        detail_layout.addLayout(info_row)

        detail_host = QWidget()
        detail_host_layout = QVBoxLayout(detail_host)
        detail_host_layout.setContentsMargins(0, 34, 0, 0)
        detail_host_layout.setSpacing(0)
        detail_host_layout.addWidget(detail)
        splitter.addWidget(detail_host)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([560, 680])

        self.setStyleSheet(
            """
            QWidget#Root {
                background: #151719;
                color: #eef0f2;
                font-size: 13px;
            }
            QMenuBar {
                background: #151719;
                color: #eef0f2;
            }
            QMenuBar::item:selected, QMenu {
                background: #24282d;
            }
            QLineEdit#SearchBox {
                background: #0f1114;
                border: 1px solid #343942;
                border-radius: 6px;
                color: #ffffff;
                padding: 9px 12px;
                selection-background-color: #0d6efd;
            }
            QPushButton, QToolButton {
                background: #272c33;
                border: 1px solid #3c434c;
                border-radius: 6px;
                color: #f4f6f8;
                padding: 8px 12px;
                min-height: 18px;
            }
            QPushButton:hover, QToolButton:hover {
                background: #333a43;
                border-color: #59616c;
            }
            QPushButton:pressed, QToolButton:pressed {
                background: #1f6feb;
                border-color: #1f6feb;
            }
            QPushButton:disabled, QToolButton:disabled {
                color: #6f7680;
                background: #1f2328;
                border-color: #2b3036;
            }
            QPushButton#PrimaryButton {
                background: #1f6feb;
                border-color: #1f6feb;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#PrimaryButton:hover {
                background: #388bfd;
                border-color: #388bfd;
                color: #ffffff;
            }
            QToolButton#CollectionButton {
                color: #c9d1d9;
                font-size: 15px;
            }
            QToolButton#CollectionButton:disabled {
                color: #6f7680;
            }
            QToolButton#IconButton {
                padding: 2px;
                min-width: 26px;
                max-width: 26px;
                min-height: 26px;
                max-height: 28px;
            }
            QToolButton#IconButton::menu-indicator {
                image: none;
                width: 0;
            }
            QToolButton#CollectionButton[saved="true"] {
                background: #3a2f12;
                border-color: #f0b429;
                color: #ffd257;
            }
            QPushButton#SourceChip {
                background: #1b2026;
                border: 1px solid #2b3138;
                border-radius: 13px;
                padding: 5px 13px;
                color: #c9d1d9;
                min-height: 16px;
            }
            QPushButton#SourceChip:hover {
                border-color: #59616c;
            }
            QPushButton#SourceChip:checked {
                background: #16324f;
                border-color: #1f6feb;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: none;
                top: 0;
            }
            QTabBar::tab {
                background: #1b2026;
                color: #c9d1d9;
                border: 1px solid #2b3138;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 7px 18px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #101316;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                color: #ffffff;
            }
            QCheckBox {
                spacing: 7px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QLabel#FieldLabel {
                color: #9aa4af;
            }
            QComboBox {
                background: #272c33;
                border: 1px solid #3c434c;
                border-radius: 6px;
                color: #f4f6f8;
                padding: 6px 10px;
                min-height: 18px;
            }
            QComboBox:hover {
                border-color: #59616c;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #1b2026;
                color: #eef0f2;
                border: 1px solid #2b3138;
                selection-background-color: #16324f;
                outline: none;
            }
            QLabel#StatusLabel {
                color: #9aa4af;
                padding: 0 8px 0 10px;
            }
            QSplitter::handle {
                background: #151719;
                border: none;
            }
            QSplitter::handle:horizontal {
                width: 10px;
            }
            QFrame#Panel {
                background: #101316;
                border: 1px solid #2b3138;
                border-radius: 8px;
            }
            QFrame#ListPanel {
                background: #101316;
                border: 1px solid #2b3138;
                border-radius: 8px;
                border-top-left-radius: 0;
            }
            QListWidget#ResultsList {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget#ResultsList::item {
                border-bottom: 1px solid #22272e;
            }
            QListWidget#ResultsList::item:selected {
                background: #16324f;
            }
            QLabel#RowTitle {
                color: #f3f6f9;
                font-weight: 600;
            }
            QLabel#RowMeta {
                color: #99a3ad;
                font-size: 12px;
            }
            QLabel#RowWaveform {
                background: #181c20;
                border: 1px solid #2e353d;
                border-radius: 5px;
                color: #5d6874;
                font-size: 11px;
            }
            QLabel#DetailTitle {
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#LargeWaveform {
                background: #181c20;
                border: 1px solid #2e353d;
                border-radius: 8px;
                color: #8a949f;
            }
            QLabel#Pill {
                background: #22272e;
                border: 1px solid #343b44;
                border-radius: 5px;
                color: #c9d1d9;
                padding: 5px 8px;
            }
            QLabel#VolumeLabel {
                min-width: 38px;
                color: #c9d1d9;
            }
            QPlainTextEdit#Description {
                background: #0f1114;
                border: 1px solid #2b3138;
                border-radius: 7px;
                color: #d8dee5;
                padding: 10px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #2b3138;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
                background: #f0b429;
            }
            QScrollBar:vertical {
                background: #101316;
                width: 12px;
            }
            QScrollBar::handle:vertical {
                background: #343b44;
                border-radius: 6px;
                min-height: 32px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

    def apply_config_to_ui(self) -> None:
        self.cc0_only.setChecked(bool(self.config["cc0_only"]))
        self.volume.setValue(int(self.config["volume"]))
        self.set_volume(int(self.config["volume"]))
        index = self.sort_combo.findData(self.config.get("sort", DEFAULT_SORT))
        if index >= 0:
            self.sort_combo.blockSignals(True)
            self.sort_combo.setCurrentIndex(index)
            self.sort_combo.blockSignals(False)
        can_play = self.player is not None
        self.play_button.setEnabled(can_play)
        self.next_button.setEnabled(True)
        self.refresh_library_sources()
        self.update_header_mode()
        self.update_action_buttons()

    def set_busy(self, busy: bool, message: str = "") -> None:
        self.loading_search = busy
        self.search_button.setEnabled(not busy or self.is_library_tab())
        if message:
            self.status_label.setText(message)

    def start_worker(self, worker: "FunctionWorker") -> None:
        # Retain the worker (and disable auto-delete) so its queued signals are
        # delivered before Python/Qt collect it.
        worker.setAutoDelete(False)
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda: self._active_workers.discard(worker))
        self.thread_pool.start(worker)

    def run_worker(self, message: str, fn, result_handler, *, done_handler=None) -> None:
        self.status_label.setText(message)
        worker = FunctionWorker(fn)
        worker.signals.result.connect(result_handler)
        worker.signals.error.connect(self.show_worker_error)
        if done_handler:
            worker.signals.finished.connect(done_handler)
        self.start_worker(worker)

    def show_worker_error(self, message: str) -> None:
        log.warning("Surfaced error to user: %s", message)
        QMessageBox.warning(self, APP_NAME, message)
        self.status_label.setText(message)

    def save_filter_config(self) -> None:
        self.config["cc0_only"] = self.cc0_only.isChecked()
        self.config["page_size"] = DEFAULT_PAGE_SIZE
        save_config(self.config)

    def set_volume(self, value: int) -> None:
        self.config["volume"] = int(value)
        self.volume_label.setText(f"{value}%")
        save_config(self.config)
        if self.audio_output is not None:
            self.audio_output.setVolume(value / 100.0)

    def media_error(self, error, error_string: str = "") -> None:
        log.warning("Media player error: %s (%s)", error_string or "unknown", error)
        if error_string:
            self.status_label.setText(error_string)

    def choose_download_folder(self) -> None:
        current = self.config.get("download_dir", str(DEFAULT_DOWNLOAD_DIR))
        selected = QFileDialog.getExistingDirectory(self, "Choose download folder", current)
        if not selected:
            return
        self.config["download_dir"] = selected
        save_config(self.config)
        self.status_label.setText(f"Download folder: {selected}")
        log.info("Download folder set to %s", selected)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.config["api_key"] = dialog.api_key.text().strip()
        self.config["download_dir"] = dialog.download_dir.text().strip() or str(DEFAULT_DOWNLOAD_DIR)
        self.config["openverse_client_id"] = dialog.ov_client_id.text().strip()
        self.config["openverse_client_secret"] = dialog.ov_client_secret.text().strip()
        self.config["page_size"] = DEFAULT_PAGE_SIZE
        save_config(self.config)
        self.client.update_api_key(self.config["api_key"])
        self.openverse.set_credentials(
            self.config["openverse_client_id"], self.config["openverse_client_secret"]
        )
        log.info(
            "Settings updated (api_key=%s, download_dir=%s, openverse_auth=%s)",
            "set" if self.config["api_key"] else "missing",
            self.config["download_dir"],
            "set" if self.config["openverse_client_id"] else "anonymous",
        )

    def is_library_tab(self) -> bool:
        return hasattr(self, "left_tabs") and self.left_tabs.tabText(self.left_tabs.currentIndex()) == "Library"

    def query_changed(self, text: str) -> None:
        if self._syncing_query:
            return
        if self.is_library_tab():
            self.library_filter = text.strip()
            self.populate_library()
            return
        self.results_query = text

    def update_header_mode(self) -> None:
        is_library = self.is_library_tab()
        self._syncing_query = True
        try:
            self.query.setText(self.library_filter if is_library else self.results_query)
        finally:
            self._syncing_query = False

        is_openverse = self.active_source == "openverse"
        placeholder = "Search Library" if is_library else ("Search Openverse" if is_openverse else "Search Freesound")
        self.query.setPlaceholderText(placeholder)
        self.search_button.setText("Filter" if is_library else "Search")
        self.search_button.setEnabled(is_library or not self.loading_search)
        self.source_combo.setVisible(not is_library)
        # Freesound-only filters
        self.sort_combo.setVisible(not is_library and not is_openverse)
        self.cc0_only.setVisible(not is_library and not is_openverse)
        for label in self.search_bar.findChildren(QLabel):
            if label.objectName() == "FieldLabel":
                label.setVisible(not is_library and not is_openverse)
        # Openverse-only filters
        for widget in self.ov_filter_widgets:
            widget.setVisible(not is_library and is_openverse)

    def _make_filter_button(self, text, options, selected_set, key) -> QToolButton:
        button = QToolButton()
        button.setObjectName("FilterButton")
        button.setText(text)
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        for label, value in options:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(value in selected_set)
            action.toggled.connect(lambda checked, v=value, k=key: self.ov_filter_changed(k, v, checked))
        menu.aboutToHide.connect(self.apply_openverse_filters)
        button.setMenu(menu)
        return button

    def _make_category_button(self) -> QToolButton:
        # Category has an explicit "Ohne Kategorie (alle)" entry, because most
        # Openverse audio is uncategorised — picking a category filters hard.
        button = QToolButton()
        button.setObjectName("FilterButton")
        button.setText("Audio-Kategorie")
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        self.ov_all_categories_action = menu.addAction("Ohne Kategorie (alle)")
        self.ov_all_categories_action.setCheckable(True)
        self.ov_all_categories_action.setChecked(not self.ov_categories)
        self.ov_all_categories_action.triggered.connect(self.ov_clear_categories)
        menu.addSeparator()
        self.ov_category_actions = {}
        for label, value in OPENVERSE_CATEGORIES:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(value in self.ov_categories)
            action.toggled.connect(lambda checked, v=value: self.ov_category_toggled(v, checked))
            self.ov_category_actions[value] = action
        menu.aboutToHide.connect(self.apply_openverse_filters)
        button.setMenu(menu)
        return button

    def _sync_all_categories(self) -> None:
        self.ov_all_categories_action.blockSignals(True)
        self.ov_all_categories_action.setChecked(not self.ov_categories)
        self.ov_all_categories_action.blockSignals(False)

    def ov_clear_categories(self, _checked: bool) -> None:
        # "Ohne Kategorie" always means: no category filter (broadest results).
        self.ov_categories.clear()
        for action in self.ov_category_actions.values():
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)
        self._sync_all_categories()
        self._ov_dirty = True

    def ov_category_toggled(self, value: str, checked: bool) -> None:
        if checked:
            self.ov_categories.add(value)
        else:
            self.ov_categories.discard(value)
        self._sync_all_categories()
        self._ov_dirty = True

    def _make_usage_button(self) -> QToolButton:
        button = QToolButton()
        button.setObjectName("FilterButton")
        button.setText("Nutzung")
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        commercial = menu.addAction("Kommerziell nutzen")
        commercial.setCheckable(True)
        commercial.setChecked(True)
        commercial.setEnabled(False)  # enforced: all results must be commercially usable
        modify = menu.addAction("Ändern oder anpassen")
        modify.setCheckable(True)
        modify.setChecked(self.ov_modify)
        modify.toggled.connect(self.ov_modify_changed)
        menu.aboutToHide.connect(self.apply_openverse_filters)
        button.setMenu(menu)
        return button

    def ov_filter_changed(self, key: str, value: str, checked: bool) -> None:
        target = {"sources": self.ov_sources, "categories": self.ov_categories, "licenses": self.ov_licenses}[key]
        if checked:
            target.add(value)
        else:
            target.discard(value)
        self._ov_dirty = True

    def ov_modify_changed(self, checked: bool) -> None:
        self.ov_modify = bool(checked)
        self._ov_dirty = True

    def apply_openverse_filters(self) -> None:
        if not self._ov_dirty:
            return
        self._ov_dirty = False
        self.save_source_config()
        if self.active_source == "openverse" and self.results_query.strip() and not self.is_library_tab():
            self.search()

    def openverse_filters(self) -> dict[str, Any]:
        sources = sorted(self.ov_sources) or list(OPENVERSE_DEFAULT_SOURCES)
        license_type = ["commercial"]
        if self.ov_modify:
            license_type.append("modification")
        return {
            "sources": sources,
            "categories": sorted(self.ov_categories),
            "licenses": sorted(self.ov_licenses),
            "license_type": license_type,
        }

    def source_changed(self) -> None:
        self.active_source = self.source_combo.currentData() or "freesound"
        log.info("Search source changed to %s", self.active_source)
        self.save_source_config()
        self.update_header_mode()
        if self.results_query.strip() and not self.is_library_tab():
            self.search()

    def save_source_config(self) -> None:
        self.config["source"] = self.active_source
        self.config["openverse_filters"] = {
            "sources": sorted(self.ov_sources),
            "categories": sorted(self.ov_categories),
            "licenses": sorted(self.ov_licenses),
            "modify": self.ov_modify,
        }
        save_config(self.config)

    def search(self) -> None:
        query = self.query.text().strip()
        if self.is_library_tab():
            self.library_filter = query
            self.populate_library()
            return
        if not query or self.loading_search:
            return
        self.results_query = query
        self.save_filter_config()
        self.results.clear()
        self.sound_widgets.clear()
        self.current_sound = None
        self.current_preview_file = None
        self.current_waveform_file = None
        self.next_url = None
        self.total_matches = 0
        self.update_detail(None)
        self.update_action_buttons()

        if self.active_source == "openverse":
            client = self.openverse
            filters = self.openverse_filters()
            message = "Searching Openverse…"

            def do_search():
                return client.search(query, filters, DEFAULT_PAGE_SIZE)
        else:
            client = self.client
            cc0 = self.cc0_only.isChecked()
            sort = self.current_sort()
            message = "Searching Freesound..."

            def do_search():
                return client.search(query, cc0, DEFAULT_PAGE_SIZE, sort)

        self.results_client = client
        self.set_busy(True, message)
        self.run_worker(message, do_search, self.populate_results, done_handler=lambda: self.set_busy(False))

    def current_sort(self) -> str:
        return self.sort_combo.currentData() or DEFAULT_SORT

    def sort_changed(self) -> None:
        self.config["sort"] = self.current_sort()
        save_config(self.config)
        log.info("Sort changed to %s", self.config["sort"])
        if not self.is_library_tab() and self.results_query.strip():
            self.search()

    def maybe_load_more(self, value: int) -> None:
        scroll = self.results.verticalScrollBar()
        if value >= scroll.maximum() - 3:
            self.load_more()

    def load_more(self) -> None:
        if not self.next_url or self.loading_more or self.loading_search:
            return
        self.loading_more = True

        client = self.results_client

        def do_load_more():
            return client.fetch_more(self.next_url or "")

        self.run_worker("Loading more results...", do_load_more, self.append_results, done_handler=self.load_more_finished)

    def load_more_finished(self) -> None:
        self.loading_more = False

    def populate_results(self, response: dict[str, Any]) -> None:
        self.results.clear()
        self.append_results(response)

    def append_results(self, response: dict[str, Any]) -> None:
        self.next_url = response.get("next")
        self.total_matches = int(response.get("count") or self.total_matches or 0)
        for sound in response.get("results", []):
            self.add_sound_row(sound, self.results, self.sound_widgets)
        loaded = self.results.count()
        self.status_label.setText(f"{loaded} of {self.total_matches} matches loaded")
        if loaded > 0 and not self.current_sound:
            self.results.setCurrentRow(0)

    def add_sound_row(self, sound: dict[str, Any], target_list: SoundListWidget, widget_map: dict) -> None:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, sound)
        item.setSizeHint(QSize(100, 72))
        widget = SoundRowWidget(sound)
        target_list.addItem(item)
        target_list.setItemWidget(item, widget)
        widget_map[sound_id(sound)] = widget
        self.queue_row_waveform(sound)

    def provider_for(self, sound: dict[str, Any] | None):
        if sound and sound.get("_provider") == "openverse":
            return self.openverse
        return self.client

    def queue_row_waveform(self, sound: dict[str, Any]) -> None:
        provider = self.provider_for(sound)

        def do_waveform():
            return sound_id(sound), provider.download_waveform(sound)

        worker = FunctionWorker(do_waveform, label=f"waveform:{sound_id(sound)}")
        worker.signals.result.connect(self.set_row_waveform)
        worker.signals.error.connect(lambda message: log.debug("Row waveform failed: %s", message))
        self.start_worker(worker)

    def set_row_waveform(self, payload) -> None:
        sid, path = payload
        for widget_map in (self.sound_widgets, self.library_widgets):
            widget = widget_map.get(sid)
            if widget:
                widget.set_waveform(Path(path))
        if self.current_sound and sound_id(self.current_sound) == sid:
            self.show_large_waveform(Path(path))

    def selected_sound(self) -> dict[str, Any] | None:
        item = self.active_list.currentItem() if self.active_list else None
        if not item:
            return None
        return item.data(Qt.UserRole)

    # ----- list / tab routing -----------------------------------------
    def on_list_selection(self, source_list: SoundListWidget) -> None:
        self.active_list = source_list
        self.selection_changed()

    def on_list_double(self, source_list: SoundListWidget) -> None:
        self.active_list = source_list
        self.play_selected()

    def on_tab_changed(self, index: int) -> None:
        is_library = self.left_tabs.tabText(index) == "Library"
        self.update_header_mode()
        if is_library:
            self.active_list = self.library_list
            self.refresh_library_sources()
            self.populate_library()
        else:
            self.active_list = self.results
        self.selection_changed()

    # ----- library -----------------------------------------------------
    def refresh_library_sources(self) -> None:
        # Rebuild the always-visible source chips (Recently used + collections).
        for button in list(self.source_group.buttons()):
            self.source_group.removeButton(button)
        while self.source_layout.count():
            item = self.source_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        sources = [("Recently used", HISTORY_KEY)]
        sources += [(f"★ {name}", name) for name in self.store.collection_names()]
        if self.library_source_key not in [key for _, key in sources]:
            self.library_source_key = HISTORY_KEY

        for label, key in sources:
            chip = QPushButton(label)
            chip.setObjectName("SourceChip")
            chip.setCheckable(True)
            chip.setChecked(key == self.library_source_key)
            chip.setProperty("sourceKey", key)
            chip.clicked.connect(lambda _checked=False, k=key: self.select_library_source(k))
            self.source_group.addButton(chip)
            self.source_layout.addWidget(chip)
        self.source_host.updateGeometry()

    def select_library_source(self, key: str) -> None:
        self.library_source_key = key
        for chip in self.source_group.buttons():
            chip.setChecked(chip.property("sourceKey") == key)
        self.populate_library()

    def library_filter_matches(self, sound: dict[str, Any], query: str) -> bool:
        if not query:
            return True
        parts = [
            str(sound.get("id", "")),
            str(sound.get("name", "")),
            str(sound.get("username", "")),
            str(sound.get("type", "")),
            str(sound.get("description", "")),
            " ".join(str(tag) for tag in sound.get("tags") or []),
        ]
        haystack = " ".join(parts).lower()
        return all(token in haystack for token in query.lower().split())

    def populate_library(self) -> None:
        self.library_list.blockSignals(True)
        self.library_list.clear()
        self.library_widgets.clear()
        source = self.library_source_key or HISTORY_KEY
        sounds = self.store.sounds_for(source)
        query = self.library_filter.strip()
        visible_sounds = [sound for sound in sounds if self.library_filter_matches(sound, query)]
        for sound in visible_sounds:
            self.add_sound_row(sound, self.library_list, self.library_widgets)
        self.library_list.blockSignals(False)
        label = "recently used" if source == HISTORY_KEY else f"'{source}'"
        if query:
            self.status_label.setText(f"{len(visible_sounds)} of {len(sounds)} sounds in {label}")
        else:
            self.status_label.setText(f"{len(sounds)} sounds in {label}")

    def record_current_use(self) -> None:
        if self.current_sound:
            self.store.record_use(self.current_sound)

    def selection_changed(self) -> None:
        sound = self.selected_sound()
        # Switching sounds must not resume the previous (possibly paused) clip
        # or reuse its playback position; always start the new clip from 0.
        if self.player is not None:
            self.player.stop()
        self._apply_seek = False
        self._pending_seek_ms = 0
        self._pending_play = None
        self.current_sound = sound
        self.current_preview_file = None
        self.current_clip_file = None
        self.selection_start = 0.0
        self.selection_end = 1.0
        self.manual_start_fraction = None
        self.large_waveform.set_playhead(0.0)
        self.large_waveform.reset_selection()
        if not sound:
            self.update_detail(None)
            self.update_action_buttons()
            return
        cached = self.cached_preview_by_id.get(sound_id(sound))
        if cached and cached.exists():
            self.current_preview_file = cached
        self.update_detail(sound)
        self.update_action_buttons()
        self.prefetch_selected_preview(sound)
        self.queue_row_waveform(sound)

    def update_detail(self, sound: dict[str, Any] | None) -> None:
        if not sound:
            self.title.setText("No sound selected")
            self.large_waveform.set_waveform(None)
            self.description.setPlainText("")
            self.user_label.setText("")
            self.format_label.setText("")
            self.size_label.setText("")
            return

        self.title.setText(str(sound.get("name", "Untitled")))
        self.user_label.setText(str(sound.get("username", "")))
        self.format_label.setText(
            "  ".join(
                part
                for part in [
                    str(sound.get("type", "")).upper(),
                    format_duration(sound.get("duration")),
                    f"{sound.get('samplerate', '')} Hz" if sound.get("samplerate") else "",
                ]
                if part
            )
        )
        self.size_label.setText(format_size(sound.get("filesize")))
        self.description.setPlainText(self.metadata_text(sound))
        self.large_waveform.set_waveform(None)

    def metadata_text(self, sound: dict[str, Any]) -> str:
        lines = [sound.get("description", "") or "", ""]
        source = source_label(sound)
        if source:
            lines.append(f"Source: {source}")
        if sound.get("_license"):
            lines.append(f"License: {sound['_license']}")
        tags = sound_tags(sound)
        if tags:
            lines.append(f"Tags: {tags}")
        if sound.get("num_downloads"):
            lines.append(f"Downloads: {sound['num_downloads']}")
        try:
            if float(sound.get("avg_rating") or 0) > 0:
                lines.append(f"Rating: {sound['avg_rating']}")
        except (TypeError, ValueError):
            pass
        if sound.get("created"):
            lines.append(f"Created: {sound['created']}")
        if sound.get("url"):
            lines.append(f"URL: {sound['url']}")
        return "\n".join(lines)

    def show_large_waveform(self, path: Path) -> None:
        self.current_waveform_file = Path(path)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.large_waveform.set_waveform(None)
            return
        self.large_waveform.set_waveform(path)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.large_waveform.update()

    def prefetch_selected_preview(self, sound: dict[str, Any]) -> None:
        sid = sound_id(sound)
        cached = self.cached_preview_by_id.get(sid)
        if cached and cached.exists():
            self.current_preview_file = cached
            return

        provider = self.provider_for(sound)

        def do_download():
            return sid, provider.ensure_preview_file(sound)

        worker = FunctionWorker(do_download, label=f"prefetch:{sid}")
        worker.signals.result.connect(self.preview_prefetched)
        worker.signals.error.connect(self.preview_prefetch_failed)
        self.start_worker(worker)

    def preview_prefetch_failed(self, message: str) -> None:
        log.warning("Preview prefetch failed: %s", message)
        if self._pending_play:
            sid, start_fraction = self._pending_play
            self._pending_play = None
            sound = self.current_sound
            if sound and sound_id(sound) == sid and preview_url(sound):
                log.info("Falling back to remote stream for sound %s", sid)
                self._start_playback(QUrl(preview_url(sound)), start_fraction, sid)
                return
        self.update_action_buttons()

    def preview_prefetched(self, payload) -> None:
        sid, path = payload
        path = Path(path)
        self.cached_preview_by_id[sid] = path
        if self.current_sound and sound_id(self.current_sound) == sid:
            self.current_preview_file = path
            self.prepare_selection_clip()
            self.update_action_buttons()
            if self._pending_play and self._pending_play[0] == sid:
                start_fraction = self._pending_play[1]
                self._pending_play = None
                self._start_playback(QUrl.fromLocalFile(str(path)), start_fraction, sid)
            else:
                self.status_label.setText(f"Preview ready: {path.name}")

    def update_action_buttons(self) -> None:
        has_sound = self.current_sound is not None
        self.download_button.setEnabled(has_sound)
        self.import_button.setEnabled(has_sound)
        self.open_button.setEnabled(has_sound)
        self.update_collection_button()

    # ----- collections -------------------------------------------------
    def update_collection_button(self) -> None:
        sound = self.current_sound
        self.collection_button.setEnabled(sound is not None)
        names = self.store.collections_for(sound) if sound else []
        saved = bool(names)
        # Filled amber star only when the sound is in at least one collection.
        self.collection_button.setText("★" if saved else "☆")
        self.collection_button.setProperty("saved", saved)
        self.collection_button.style().unpolish(self.collection_button)
        self.collection_button.style().polish(self.collection_button)
        self.collection_button.setToolTip(
            "In collections: " + ", ".join(names) if saved else "Save to collection"
        )

    def build_collection_menu(self) -> None:
        self.collection_menu.clear()
        sound = self.current_sound
        if not sound:
            action = self.collection_menu.addAction("Select a sound first")
            action.setEnabled(False)
            return
        new_action = self.collection_menu.addAction("New collection…")
        new_action.triggered.connect(self.new_collection_for_current)
        names = self.store.collection_names()
        if names:
            self.collection_menu.addSeparator()
        for name in names:
            action = self.collection_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(self.store.is_in_collection(name, sound))
            action.triggered.connect(lambda checked, n=name: self.toggle_collection(n, checked))

    def toggle_collection(self, name: str, checked: bool) -> None:
        sound = self.current_sound
        if not sound:
            return
        if checked:
            self.store.add_to_collection(name, sound)
            self.status_label.setText(f"Added to '{name}'")
        else:
            self.store.remove_from_collection(name, sound)
            self.status_label.setText(f"Removed from '{name}'")
        self.refresh_library_sources()
        if self.left_tabs.tabText(self.left_tabs.currentIndex()) == "Library":
            self.populate_library()
        self.update_collection_button()

    def new_collection_for_current(self) -> None:
        sound = self.current_sound
        name, ok = QInputDialog.getText(self, "New collection", "Collection name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        self.store.create_collection(name)
        if sound:
            self.store.add_to_collection(name, sound)
            self.status_label.setText(f"Added to '{name}'")
        self.update_collection_button()
        self.show_collection(name)

    def _library_tab_index(self) -> int:
        for i in range(self.left_tabs.count()):
            if self.left_tabs.tabText(i) == "Library":
                return i
        return 0

    def show_collection(self, name: str) -> None:
        """Reveal a collection: open the Library tab and select its chip."""
        self.library_source_key = name
        self.left_tabs.setCurrentIndex(self._library_tab_index())
        self.refresh_library_sources()
        self.select_library_source(name)

    def current_drag_file(self) -> Path | None:
        # The drag source is the fast local cache file (no blocking copy, so it
        # never stutters for longer clips). After a drop, on_drag_finished copies
        # it into the user's Download folder.
        if self.current_clip_file and self.current_clip_file.exists():
            return self.current_clip_file
        if self.current_preview_file and self.current_preview_file.exists():
            if selection_is_full(self.selection_start, self.selection_end):
                return self.current_preview_file
        if self.current_sound:
            cached = self.cached_preview_by_id.get(sound_id(self.current_sound))
            if cached and cached.exists():
                if selection_is_full(self.selection_start, self.selection_end):
                    return cached
        return None

    def on_drag_finished(self, path: str) -> None:
        # After the drag gesture completes, copy the dragged file into the
        # Download folder (in the background) so it also lives there.
        source = Path(path)
        if not source.exists():
            return
        download_dir = Path(self.config.get("download_dir", str(DEFAULT_DOWNLOAD_DIR))).expanduser()

        def do_copy():
            download_dir.mkdir(parents=True, exist_ok=True)
            target = download_dir / source.name
            if not target.exists() or target.stat().st_size != source.stat().st_size:
                shutil.copy2(source, target)
                log.info("Copied dragged sound to %s", target)
            return target

        worker = FunctionWorker(do_copy, label="drag-copy")
        worker.signals.error.connect(lambda message: log.warning("Drag copy failed: %s", message))
        self.start_worker(worker)

    def selection_key(self) -> tuple[str, int, int] | None:
        if not self.current_sound:
            return None
        return (
            sound_id(self.current_sound),
            int(self.selection_start * 100000),
            int(self.selection_end * 100000),
        )

    def selection_changed_on_waveform(self, start: float, end: float) -> None:
        self.selection_start = start
        self.selection_end = end
        self.current_clip_file = None
        self.manual_start_fraction = None
        self.status_label.setText(f"Selection: {int(start * 100)}% - {int(end * 100)}%")
        self.update_action_buttons()
        self.prepare_selection_clip()

    def prepare_selection_clip(self) -> None:
        if not self.current_sound or not self.current_preview_file or not self.current_preview_file.exists():
            return
        key = self.selection_key()
        if key and key in self.cached_clip_by_key and self.cached_clip_by_key[key].exists():
            self.current_clip_file = self.cached_clip_by_key[key]
            self.update_action_buttons()
            return
        if selection_is_full(self.selection_start, self.selection_end):
            self.current_clip_file = None
            self.update_action_buttons()
            return

        sound = self.current_sound
        source = self.current_preview_file
        start = self.selection_start
        end = self.selection_end

        def do_trim():
            return key, trim_preview_file(source, sound, start, end)

        worker = FunctionWorker(do_trim)
        worker.signals.result.connect(self.selection_clip_ready)
        worker.signals.error.connect(lambda message: self.status_label.setText(message))
        self.start_worker(worker)

    def selection_clip_ready(self, payload) -> None:
        key, path = payload
        if key:
            self.cached_clip_by_key[key] = Path(path)
        if key == self.selection_key():
            self.current_clip_file = Path(path)
            self.status_label.setText(f"Selection ready for drag: {Path(path).name}")
            self.update_action_buttons()

    def selection_times_ms(self) -> tuple[int, int]:
        duration = sound_duration_seconds(self.current_sound or {})
        if duration <= 0:
            return 0, 0
        return int(duration * self.selection_start * 1000), int(duration * self.selection_end * 1000)

    def update_playhead_from_position(self, position_ms: int) -> None:
        duration = sound_duration_seconds(self.current_sound or {})
        if duration <= 0:
            return
        self.large_waveform.set_playhead(position_ms / (duration * 1000))

    def stop_at_selection_end(self) -> None:
        if self.player is None or not self.current_sound:
            self.playback_timer.stop()
            return
        _start_ms, end_ms = self.selection_times_ms()
        if end_ms and self.player.position() >= end_ms:
            self.stop_playback()

    def _ms_for_fraction(self, fraction: float) -> int:
        duration = sound_duration_seconds(self.current_sound or {})
        if duration <= 0:
            return 0
        return int(duration * max(0.0, min(1.0, fraction)) * 1000)

    def play_selected(self, start_fraction: float | None = None) -> None:
        sound = self.selected_sound()
        if not sound or self.player is None:
            return
        if not preview_url(sound):
            self.show_worker_error("No preview URL available for this sound.")
            return
        if start_fraction is None:
            start_fraction = (
                self.manual_start_fraction
                if self.manual_start_fraction is not None
                else self.selection_start
            )
        start_fraction = max(0.0, min(1.0, start_fraction))
        sid = sound_id(sound)

        cached = self.cached_preview_by_id.get(sid)
        if cached and cached.exists():
            # Play the local file for instant, glitch-free start.
            self._pending_play = None
            self._start_playback(QUrl.fromLocalFile(str(cached)), start_fraction, sid)
            return

        # Not cached yet: fetch it and play as soon as it lands (avoids the slow
        # remote-stream buffering). prepare_selection_clip/prefetch already runs
        # on selection, so this is usually a very short wait.
        self._pending_play = (sid, start_fraction)
        self.status_label.setText("Loading preview…")
        self.prefetch_selected_preview(sound)

    def _start_playback(self, source: QUrl, start_fraction: float, sid: str) -> None:
        log.info("Play sound %s from %d%% (%s)", sid, int(start_fraction * 100),
                 "local" if source.isLocalFile() else "stream")
        if self.audio_output is not None:
            self.audio_output.setVolume(self.volume.value() / 100.0)
        # Seeking straight after setSource is unreliable because the media is
        # not loaded yet; remember the target and apply it once loaded. The flag
        # ensures we always seek (even to 0) so a fresh clip starts at its start.
        self._pending_seek_ms = self._ms_for_fraction(start_fraction)
        self._apply_seek = True
        self.player.setSource(source)
        self.player.play()
        self.playback_timer.start()
        self.status_label.setText("Playing preview")

    def toggle_play_pause(self) -> None:
        if self.player is None:
            return
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.playback_timer.stop()
            self.status_label.setText("Paused")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.player.play()
            self.playback_timer.start()
            self.status_label.setText("Playing preview")
        else:
            self.play_selected()

    def play_next(self) -> None:
        lst = self.active_list or self.results
        count = lst.count()
        if count == 0:
            return
        next_row = lst.currentRow() + 1
        if next_row >= count:
            self.status_label.setText("End of results")
            return
        lst.setCurrentRow(next_row)
        self.play_selected()

    def on_playback_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        icon = QStyle.SP_MediaPause if playing else QStyle.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))

    def on_media_status_changed(self, status) -> None:
        ready = (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        )
        if status in ready and self._apply_seek:
            self.player.setPosition(self._pending_seek_ms)
            self._apply_seek = False

    def on_waveform_seek(self, fraction: float) -> None:
        self.manual_start_fraction = fraction
        self.large_waveform.set_playhead(fraction)
        if self.player is None:
            return
        state = self.player.playbackState()
        if state in (QMediaPlayer.PlaybackState.PlayingState, QMediaPlayer.PlaybackState.PausedState):
            self.player.setPosition(self._ms_for_fraction(fraction))
            self.status_label.setText(f"Cursor at {int(fraction * 100)}%")
        else:
            self.status_label.setText(f"Cursor at {int(fraction * 100)}% (press Play to start here)")

    def stop_playback(self) -> None:
        self.playback_timer.stop()
        if self.player is not None:
            self.player.stop()
            self.status_label.setText("Stopped")

    def ensure_preview_file(self, result_handler, target_dir: Path | None = None) -> None:
        sound = self.selected_sound()
        if not sound:
            return
        sid = sound_id(sound)
        if target_dir is None:
            current = self.current_drag_file()
            if current and current.exists():
                result_handler(current)
                return

        provider = self.provider_for(sound)

        def do_download():
            source = self.cached_preview_by_id.get(sid)
            if not source or not source.exists():
                source = provider.ensure_preview_file(sound)
            if selection_is_full(self.selection_start, self.selection_end):
                if target_dir is None:
                    return source
                return provider.ensure_preview_file(sound, target_dir)
            return trim_preview_file(source, sound, self.selection_start, self.selection_end, target_dir)

        self.run_worker("Preparing preview file...", do_download, result_handler)

    def download_selected_preview(self) -> None:
        download_dir = Path(self.config.get("download_dir", str(DEFAULT_DOWNLOAD_DIR))).expanduser()
        self.ensure_preview_file(self.preview_downloaded, download_dir)

    def preview_downloaded(self, path: Path) -> None:
        downloaded = Path(path)
        self.record_current_use()
        log.info("Downloaded to %s", downloaded)
        self.status_label.setText(f"Downloaded: {downloaded}")

    def import_selected_to_resolve(self) -> None:
        self.record_current_use()
        self.ensure_preview_file(self.import_preview_file)

    def import_preview_file(self, path: Path) -> None:
        path = Path(path)

        def do_import():
            return import_into_resolve([path])

        self.run_worker("Importing into Resolve...", do_import, self.resolve_import_finished)

    def resolve_import_finished(self, count: int) -> None:
        self.status_label.setText(f"Imported {count} file(s) into Resolve")

    def open_selected_page(self) -> None:
        sound = self.selected_sound()
        if not sound or not sound.get("url"):
            return
        url = sound["url"]
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", url])
        elif os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])

    def prompt_ffmpeg_install(self, force: bool = False) -> None:
        if ffmpeg_available():
            if force:
                QMessageBox.information(self, APP_NAME, "ffmpeg is already installed.")
            return
        command = ffmpeg_install_command()
        intro = "ffmpeg is required to trim selections before download, drag, or import.\n\n"
        if not command:
            QMessageBox.warning(
                self,
                APP_NAME,
                intro + "Automatic install is not available on this system. "
                "Please install ffmpeg manually, then restart the app.",
            )
            return
        reply = QMessageBox.question(
            self,
            APP_NAME,
            intro + "Install it now? You may be asked for your password.\n\nCommand:\n" + " ".join(command),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.install_ffmpeg_action.setEnabled(False)

        def do_install():
            return run_ffmpeg_install(command)

        self.run_worker(
            "Installing ffmpeg…",
            do_install,
            self.ffmpeg_install_done,
            done_handler=lambda: self.install_ffmpeg_action.setEnabled(True),
        )

    def ffmpeg_install_done(self, _output: str) -> None:
        self.status_label.setText("ffmpeg installed.")
        QMessageBox.information(self, APP_NAME, "ffmpeg installed successfully.")


def main() -> int:
    setup_logging(LOG_DIR)
    install_excepthook(log)
    log.info("Starting %s on %s (Python %s)", APP_NAME, sys.platform, sys.version.split()[0])
    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationDisplayName(APP_NAME)
        app.setDesktopFileName("resolve-freesound-browser-wave")
        app.setWindowIcon(make_app_icon())
        window = FreesoundBrowser()
        window.show()
        code = app.exec()
    except Exception:
        log.exception("Fatal error during startup")
        raise
    log.info("Exiting with code %s", code)
    return code
