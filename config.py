"""
config.py
---------
Small persistent settings store (JSON on disk). No external deps.

File lives next to the app (or in %APPDATA%\\ytdlp-gui on Windows if
the app directory isn't writable, e.g. when frozen into Program Files).
"""

import json
import os
import sys

APP_DIR_NAME = "ytdlp-gui"
CONFIG_FILENAME = "config.json"

DEFAULTS = {
    "ytdlp_path": "",          # path to yt-dlp.exe ("" = auto-detect)
    "ffmpeg_path": "",         # optional, "" = let yt-dlp find it on PATH
    "output_dir": "",          # "" = resolved to ~/Downloads/yt-dlp-gui
    "filename_template": "%(title)s [%(id)s].%(ext)s",
    "accent": "amber",         # amber | green | blue | red
    "embed_thumbnail": True,
    "write_subs": False,
    "sub_langs": "en",
    "download_playlist": False,
}


def _app_base_dir():
    """Directory the script/exe lives in (for portable, next-to-exe config)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _config_path():
    base = _app_base_dir()
    candidate = os.path.join(base, CONFIG_FILENAME)
    # Prefer portable (next-to-exe) config if that folder is writable.
    if os.access(base, os.W_OK):
        return candidate
    # Fall back to a per-user app-data directory (Windows-friendly, but
    # works cross-platform since we only use os.path / os.makedirs).
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    fallback_dir = os.path.join(appdata, APP_DIR_NAME)
    os.makedirs(fallback_dir, exist_ok=True)
    return os.path.join(fallback_dir, CONFIG_FILENAME)


def default_output_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads", "yt-dlp-gui")


def load():
    path = _config_path()
    data = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass  # corrupt/unreadable config -> fall back to defaults silently
    if not data["output_dir"]:
        data["output_dir"] = default_output_dir()
    return data


def save(data):
    path = _config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False
