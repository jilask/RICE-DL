# RICE-DL

A lightweight, retro terminal-styled GUI for [yt-dlp](https://github.com/yt-dlp/yt-dlp).
No command line needed — paste a URL, pick options, hit download.

Visual style: an i3 / Hyprland / dwm "ricing" desktop (flat panels, hairline
borders, a waybar-style status strip, numbered workspace tabs) crossed with
a retro sci-fi command terminal (amber monochrome readouts, box-drawing
frames, a blinking status glyph, all-caps labels). Four switchable
"workspaces": **1:DOWNLOAD 2:QUEUE 3:LOG 4:SETTINGS**.

Built with **pure Python + tkinter** — no third-party GUI framework, no
`pip install` needed to run it. That keeps it small and easy to freeze into
a single `.exe`.

## Requirements

- Python 3.9+ (Windows: the official installer includes tkinter by default —
  just make sure "tcl/tk and IDLE" stays checked during install)
- `yt-dlp.exe` — download from the
  [yt-dlp releases page](https://github.com/yt-dlp/yt-dlp/releases/latest)
  and drop it in this folder (or point Settings at wherever it lives)
- `ffmpeg.exe` (optional, but needed to merge separate video+audio streams
  or convert to mp3) — the app will use one on your PATH automatically if
  it finds it, or you can point Settings at a specific copy

## Running it

```
python main.py
```

That's it — no other install steps. On first launch it looks for
`yt-dlp.exe` next to `main.py`, then on your PATH. If it can't find one,
the SETTINGS tab lets you browse to it.

## Using the app

- **1:DOWNLOAD** — paste a URL, click **FETCH** to preview the title
  before committing, choose *Video+Audio (mp4)* or *Audio only (mp3)*,
  cap the quality, set thumbnails/subtitles/playlist options, pick a
  destination folder and filename pattern, then **DOWNLOAD NOW** (runs
  immediately) or **+ ADD TO QUEUE** (batches it up).
- **2:QUEUE** — review queued jobs and **START QUEUE** to run them one
  after another.
- **3:LOG** — the raw yt-dlp terminal output, in case something needs
  debugging or you just like watching the scrollback.
- **4:SETTINGS** — set the `yt-dlp.exe` / `ffmpeg.exe` paths, check for
  yt-dlp updates, switch the accent color (amber/green/blue/red), and
  save your defaults.

Settings are stored in a small `config.json` next to the app (or in
`%APPDATA%\ytdlp-gui` if that folder isn't writable, e.g. when installed
under Program Files).

## Building a standalone .exe

On Windows, with this folder as your working directory:

```
build.bat
```

This installs [PyInstaller](https://pyinstaller.org) if needed and
produces `dist\RICE-DL.exe` — a single-file app with no Python
installation required to run it. Copy `yt-dlp.exe` (and `ffmpeg.exe`, if
used) into the same `dist` folder, or set their paths from the Settings
tab once the app is running.

## Project layout

```
main.py             the GUI (tkinter/ttk) — window chrome, tabs, pages
yt_dlp_wrapper.py    talks to yt-dlp.exe: find it, fetch metadata, build
                     commands, stream progress from a background thread
theme.py             color palette, fonts, box-drawing chrome, ttk styles
config.py            loads/saves config.json (paths, defaults, accent)
build.bat            PyInstaller packaging script
```

## Notes

- All yt-dlp invocations use `subprocess` with an argument list (never a
  shell string), so URLs/paths with spaces or special characters are
  handled safely.
- Downloading is only as legal as your use of yt-dlp itself — this tool
  is just a front end and doesn't change what content you're allowed to
  download from a given site.

## License

MIT — see [LICENSE](LICENSE). yt-dlp itself is a separate project with its
own license and isn't bundled in this repo.
