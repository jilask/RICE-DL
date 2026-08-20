"""
yt_dlp_wrapper.py
------------------
All the actual "talk to yt-dlp.exe" logic lives here, kept independent of
tkinter so it's easy to test or reuse. The GUI never builds a raw command
line itself -- it calls into this module.

Nothing here shells out through cmd.exe / os.system; everything uses
subprocess with an argument list, so paths/titles with spaces or quotes
are handled correctly and there's no shell-injection surface.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading

IS_WINDOWS = sys.platform.startswith("win")

# Hide the flash of a console window on Windows when we spawn yt-dlp.
_STARTUPINFO = None
_CREATIONFLAGS = 0
if IS_WINDOWS:
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _CREATIONFLAGS = subprocess.CREATE_NO_WINDOW

# [download]  42.0% of ~ 12.34MiB at    1.23MiB/s ETA 00:07
PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<pct>\d{1,3}(?:\.\d+)?)%"
    r"(?:\s+of\s+~?\s*(?P<size>[\d.]+\w+))?"
    r"(?:\s+at\s+(?P<speed>[\d.]+\w+/s|Unknown speed))?"
    r"(?:\s+ETA\s+(?P<eta>[\d:]+|Unknown))?"
)
DESTINATION_RE = re.compile(r"\[download\]\s+Destination:\s+(?P<path>.+)")
ALREADY_RE = re.compile(r"\[download\]\s+(?P<path>.+?)\s+has already been downloaded")
MERGE_RE = re.compile(r"\[Merger\]\s+Merging formats into\s+\"(?P<path>.+)\"")


class YtDlpNotFoundError(RuntimeError):
    pass


def find_ytdlp(configured_path=""):
    """
    Resolution order:
      1. explicit path from settings, if it exists
      2. yt-dlp.exe / yt-dlp sitting next to this script (bundled copy)
      3. yt-dlp(.exe) somewhere on PATH
    """
    if configured_path and os.path.isfile(configured_path):
        return configured_path

    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_name = "yt-dlp.exe" if IS_WINDOWS else "yt-dlp"
    local_candidate = os.path.join(base_dir, local_name)
    if os.path.isfile(local_candidate):
        return local_candidate

    on_path = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if on_path:
        return on_path

    raise YtDlpNotFoundError(
        "yt-dlp executable not found. Set its path in the Settings tab, "
        "or drop yt-dlp.exe next to this app."
    )


def get_version(ytdlp_path):
    try:
        out = subprocess.run(
            [ytdlp_path, "--version"], capture_output=True, text=True,
            timeout=10, startupinfo=_STARTUPINFO, creationflags=_CREATIONFLAGS,
        )
        return out.stdout.strip() or out.stderr.strip()
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as text
        return f"unknown ({exc})"


def fetch_info(ytdlp_path, url, timeout=45, download_playlist=False):
    """
    Runs `yt-dlp --dump-json [--flat-playlist | --no-playlist] <url>` and returns
    a parsed dict with the fields the UI cares about. Raises RuntimeError with
    yt-dlp's own stderr on failure so the user sees the *real* reason (geo-block,
    private video, unsupported site, etc).
    """
    cmd = [ytdlp_path, "--dump-json"]
    if download_playlist:
        cmd.append("--flat-playlist")
    else:
        cmd.append("--no-playlist")
    cmd.extend(["--no-warnings", url])

    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        startupinfo=_STARTUPINFO, creationflags=_CREATIONFLAGS,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or "yt-dlp failed to fetch info."
        if not download_playlist and "playlist" in err.lower():
            err += " (check 'Whole playlist' to fetch playlists)"
        raise RuntimeError(err)

    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("yt-dlp returned empty output.")

    try:
        objects = [json.loads(line) for line in lines]
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse yt-dlp output: {exc}") from exc

    first = objects[0]
    if first.get("_type") == "playlist":
        entries = first.get("entries") or []
        preview_entries = [
            {"title": e.get("title", "Unknown title"), "id": e.get("id", "")}
            for e in entries[:5]
            if isinstance(e, dict)
        ]
        return {
            "is_playlist": True,
            "playlist_title": first.get("title") or first.get("playlist_title") or "Unknown playlist",
            "entry_count": first.get("playlist_count") or len(entries),
            "entries": preview_entries,
        }

    if len(objects) > 1 or (
        download_playlist and (
            first.get("playlist_title")
            or first.get("playlist")
            or first.get("playlist_id")
            or first.get("_type") in ("url", "url_transparent")
        )
    ):
        preview_entries = [
            {"title": obj.get("title", "Unknown title"), "id": obj.get("id", "")}
            for obj in objects[:5]
        ]
        playlist_title = (
            first.get("playlist_title")
            or first.get("playlist")
            or "Unknown playlist"
        )
        entry_count = first.get("playlist_count") or len(objects)
        return {
            "is_playlist": True,
            "playlist_title": playlist_title,
            "entry_count": entry_count,
            "entries": preview_entries,
        }

    data = first
    return {
        "is_playlist": False,
        "title": data.get("title", "Unknown title"),
        "uploader": data.get("uploader") or data.get("channel") or "Unknown",
        "duration_string": data.get("duration_string", "?"),
        "webpage_url": data.get("webpage_url", url),
        "extractor": data.get("extractor_key", "?"),
        "is_playlist_entry": bool(data.get("playlist")),
        "view_count": data.get("view_count"),
    }


FORMAT_PRESETS = {
    "best": "bestvideo*+bestaudio/best",
    "audio": "bestaudio/best",
}

QUALITY_HEIGHT_CAP = {
    "Best": None,
    "2160p": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}


def build_format_string(mode, quality_label):
    """
    mode: "best" (video+audio merged) or "audio" (audio only)
    quality_label: one of QUALITY_HEIGHT_CAP keys, ignored for audio mode
    """
    if mode == "audio":
        return FORMAT_PRESETS["audio"]

    cap = QUALITY_HEIGHT_CAP.get(quality_label)
    if cap is None:
        return FORMAT_PRESETS["best"]
    return f"bestvideo*[height<={cap}]+bestaudio/best[height<={cap}]"


def build_download_cmd(ytdlp_path, url, *, mode, quality_label, output_dir,
                        filename_template, ffmpeg_path="", embed_thumbnail=True,
                        write_subs=False, sub_langs="en", download_playlist=False):
    """Builds the full argv list passed to subprocess -- no shell involved."""
    out_template = os.path.join(output_dir, filename_template)
    cmd = [
        ytdlp_path,
        url,
        "-o", out_template,
        "--newline",              # one progress line per update, easy to parse
        "--no-color",
        "--no-mtime",
        "--ignore-errors",
        "--console-title",
    ]

    if download_playlist:
        cmd += ["--yes-playlist"]
    else:
        cmd += ["--no-playlist"]

    if mode == "audio":
        cmd += [
            "-f", build_format_string("audio", quality_label),
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
        ]
    else:
        cmd += [
            "-f", build_format_string("best", quality_label),
            "--merge-output-format", "mp4",
        ]

    if embed_thumbnail:
        cmd += ["--embed-thumbnail"]
    if write_subs:
        cmd += ["--write-subs", "--sub-langs", sub_langs, "--embed-subs"]
    if ffmpeg_path:
        cmd += ["--ffmpeg-location", ffmpeg_path]

    return cmd


class DownloadJob:
    """
    Runs one yt-dlp invocation in a background thread, streaming parsed
    progress events back to the GUI thread via callbacks. All callbacks are
    invoked from the worker thread -- callers (the GUI) are responsible for
    marshalling onto the Tk main thread (e.g. via `root.after`).
    """

    def __init__(self, cmd, on_progress=None, on_line=None, on_done=None):
        self.cmd = cmd
        self.on_progress = on_progress or (lambda **kw: None)
        self.on_line = on_line or (lambda line: None)
        self.on_done = on_done or (lambda **kw: None)
        self._proc = None
        self._thread = None
        self._cancelled = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass

    def _run(self):
        try:
            self._proc = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True,
                startupinfo=_STARTUPINFO, creationflags=_CREATIONFLAGS,
            )
        except FileNotFoundError as exc:
            self.on_done(success=False, cancelled=False, error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.on_done(success=False, cancelled=False, error=str(exc))
            return

        last_dest = None
        for raw_line in self._proc.stdout:
            line = raw_line.rstrip("\n").rstrip("\r")
            if not line:
                continue
            self.on_line(line)

            m = PROGRESS_RE.search(line)
            if m:
                self.on_progress(
                    pct=float(m.group("pct")),
                    size=m.group("size"),
                    speed=m.group("speed"),
                    eta=m.group("eta"),
                )
                continue

            m = DESTINATION_RE.search(line)
            if m:
                last_dest = m.group("path")
                continue
            m = ALREADY_RE.search(line)
            if m:
                last_dest = m.group("path")
                continue
            m = MERGE_RE.search(line)
            if m:
                last_dest = m.group("path")

        returncode = self._proc.wait()
        if self._cancelled:
            self.on_done(success=False, cancelled=True, error=None, path=last_dest)
        elif returncode == 0:
            self.on_done(success=True, cancelled=False, error=None, path=last_dest)
        else:
            self.on_done(success=False, cancelled=False,
                          error=f"yt-dlp exited with code {returncode}", path=last_dest)
