#!/usr/bin/env python3
"""
RICE-DL :: a retro terminal-styled GUI for yt-dlp.

Visual language: i3/Hyprland/dwm "ricing" (flat panels, hairline borders,
a waybar-style status strip, workspace-numbered tabs) crossed with a
retro sci-fi terminal aesthetic (monochrome amber readouts, box-drawing
frames, blinking status glyph, all-caps labels).

Pure stdlib: tkinter + ttk. No external dependencies -- keeps the tool
lightweight and trivial to freeze into a single .exe with PyInstaller.

Run:      python main.py
Freeze:   pyinstaller --onefile --noconsole --name RICE-DL main.py
          (drop yt-dlp.exe next to the resulting exe, or point Settings
          at it)
"""

import os
import queue as pyqueue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import config
import theme
import yt_dlp_wrapper as ytw
from theme import BG0, FG_DIM, Fonts, Theme

APP_TITLE = "RICE-DL"
APP_VERSION = "1.0"


# ------------------------------------------------------------------
# Small reusable widgets
# ------------------------------------------------------------------
class StatusDot(tk.Canvas):
    """Small blinking status glyph, retro terminal console style."""

    STATES = {
        "idle": theme.FG_DIM,
        "ok": theme.OK_GREEN,
        "busy": None,   # animated -> accent color, handled specially
        "error": theme.ERR_RED,
    }

    def __init__(self, master, size=10, **kw):
        super().__init__(master, width=size, height=size, bg=BG0,
                          highlightthickness=0, **kw)
        self.size = size
        self._state = "idle"
        self._blink_on = True
        self._oval = self.create_oval(1, 1, size - 1, size - 1,
                                       fill=theme.FG_DIM, outline="")
        self._tick()

    def set_state(self, state):
        self._state = state
        self._blink_on = True
        self._redraw()

    def _redraw(self):
        if self._state == "busy":
            color = Theme.accent() if self._blink_on else BG0
        else:
            color = self.STATES.get(self._state, theme.FG_DIM)
        self.itemconfig(self._oval, fill=color)

    def _tick(self):
        if self._state == "busy":
            self._blink_on = not self._blink_on
            self._redraw()
        self.after(550, self._tick)


class SectionFrame(ttk.Frame):
    """
    A bordered panel with a box-drawing-styled header label, e.g.:
        ╭─ SOURCE ───────────────────────────────╮
    Purely cosmetic chrome around a content frame.
    """

    def __init__(self, master, title, **kw):
        super().__init__(master, style="Panel.TFrame", **kw)
        header = ttk.Label(self, style="Accent.TLabel",
                            text=f"\u25c8 {title.upper()}")
        header.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        sep = ttk.Separator(self, orient="horizontal")
        sep.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.body = ttk.Frame(self, style="Panel.TFrame")
        self.body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.columnconfigure(0, weight=1)
        self.configure(borderwidth=1, relief="solid")


# ------------------------------------------------------------------
# Main Application
# ------------------------------------------------------------------
class App(tk.Tk):
    PAGES = ["DOWNLOAD", "QUEUE", "LOG", "SETTINGS"]

    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        Theme.accent_name = self.cfg.get("accent", "amber")

        self.title(APP_TITLE)
        self.geometry("980x680")
        self.minsize(860, 600)
        self.configure(bg=BG0)

        Fonts.init(self)
        self.style = ttk.Style(self)
        theme.apply_ttk_style(self.style)

        self._darken_windows_titlebar()

        self.ytdlp_path = None
        self.ytdlp_version = "unknown"
        self._resolve_ytdlp(startup=True)

        self.download_queue = []   # list[dict] queued jobs
        self.current_job = None
        self.ui_queue = pyqueue.Queue()  # worker-thread -> UI-thread events

        self._build_chrome()
        self._build_tabbar()
        self._build_pages()
        self._select_page("DOWNLOAD")

        self.after(80, self._pump_ui_queue)
        self._tick_clock()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- platform polish -------------------------------------------------
    def _darken_windows_titlebar(self):
        """Best-effort dark titlebar on Windows 10/11 (no-op elsewhere)."""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:  # noqa: BLE001 - purely cosmetic, never fatal
            pass

    def _resolve_ytdlp(self, startup=False):
        try:
            self.ytdlp_path = ytw.find_ytdlp(self.cfg.get("ytdlp_path", ""))
            self.ytdlp_version = ytw.get_version(self.ytdlp_path)
        except ytw.YtDlpNotFoundError:
            self.ytdlp_path = None
            self.ytdlp_version = None
            if not startup:
                messagebox.showwarning(
                    APP_TITLE,
                    "yt-dlp executable not found.\n\n"
                    "Set its location in the SETTINGS tab, or place "
                    "yt-dlp.exe in this app's folder.",
                )

    # -- decorative top chrome -------------------------------------------
    def _build_chrome(self):
        chrome = ttk.Frame(self, style="Chrome.TFrame")
        chrome.pack(side="top", fill="x")

        art = tk.Text(chrome, height=3, bg=BG0, fg=Theme.accent(),
                       font=Fonts.mono_small, bd=0, highlightthickness=0,
                       relief="flat", wrap="none")
        line1 = theme.framed_title(f"{APP_TITLE} // yt-dlp interface terminal", 70)
        line2 = f"\u2502  status: OPERATIONAL  |  mode: NON-INTERACTIVE  |  build v{APP_VERSION}"
        line2 = line2.ljust(69) + "\u2502"
        line3 = theme.framed_bottom(70)
        art.insert("1.0", f"{line1}\n{line2}\n{line3}")
        art.configure(state="disabled")
        art.pack(side="left", padx=16, pady=(10, 2))

        right = ttk.Frame(chrome, style="Chrome.TFrame")
        right.pack(side="right", padx=16, pady=(10, 2))
        self.status_dot = StatusDot(right)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = ttk.Label(right, style="BarAccent.TLabel", text="IDLE")
        self.status_label.pack(side="left")

    # -- waybar-style workspace tab bar ----------------------------------
    def _build_tabbar(self):
        bar = ttk.Frame(self, style="BorderedChrome.TFrame")
        bar.pack(side="top", fill="x")

        left = ttk.Frame(bar, style="Chrome.TFrame")
        left.pack(side="left", padx=10, pady=6)

        self.tab_buttons = {}
        for i, name in enumerate(self.PAGES, start=1):
            b = ttk.Button(left, text=f"{i}:{name}", style="Tab.TButton",
                            command=lambda n=name: self._select_page(n))
            b.pack(side="left", padx=(0, 2))
            self.tab_buttons[name] = b

        mid = ttk.Frame(bar, style="Chrome.TFrame")
        mid.pack(side="left", padx=20)
        self.queue_badge = ttk.Label(mid, style="Bar.TLabel", text="\u2261 queue: 0")
        self.queue_badge.pack(side="left")

        right = ttk.Frame(bar, style="Chrome.TFrame")
        right.pack(side="right", padx=14, pady=6)
        self.clock_label = ttk.Label(right, style="BarAccent.TLabel", text="")
        self.clock_label.pack(side="right")
        ttk.Label(right, style="Dim.TLabel", text="\u2502").pack(side="right", padx=8)
        ver_text = f"yt-dlp {self.ytdlp_version}" if self.ytdlp_version else "yt-dlp NOT FOUND"
        self.ver_label = ttk.Label(right, style="Bar.TLabel", text=ver_text)
        self.ver_label.pack(side="right")

    def _tick_clock(self):
        self.clock_label.configure(text=time.strftime("%H:%M:%S  %Y-%m-%d"))
        self.after(1000, self._tick_clock)

    def _select_page(self, name):
        for n, b in self.tab_buttons.items():
            b.configure(style="TabActive.TButton" if n == name else "Tab.TButton")
        for n, f in self.pages.items():
            if n == name:
                f.pack(fill="both", expand=True)
            else:
                f.pack_forget()

    # -- page construction -------------------------------------------------
    def _build_pages(self):
        container = ttk.Frame(self, style="Panel.TFrame")
        container.pack(side="top", fill="both", expand=True)
        self.pages = {}
        self.pages["DOWNLOAD"] = self._build_download_page(container)
        self.pages["QUEUE"] = self._build_queue_page(container)
        self.pages["LOG"] = self._build_log_page(container)
        self.pages["SETTINGS"] = self._build_settings_page(container)

    # ---------------- DOWNLOAD PAGE ----------------
    def _build_download_page(self, parent):
        page = ttk.Frame(parent, style="Panel.TFrame")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        # -- Source panel --
        src = SectionFrame(page, "source")
        src.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        src.body.columnconfigure(1, weight=1)

        ttk.Label(src.body, text="url >", style="Accent.TLabel").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(src.body, textvariable=self.url_var, font=Fonts.mono)
        url_entry.grid(row=0, column=1, sticky="ew", padx=8)
        url_entry.bind("<Return>", lambda e: self._fetch_info())
        ttk.Button(src.body, text="FETCH", style="Accent.TButton",
                   command=self._fetch_info).grid(row=0, column=2, padx=(4, 0))

        self.info_label = ttk.Label(src.body, style="Muted.TLabel", text="", wraplength=820,
                                     justify="left")
        self.info_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # -- Options panel --
        opts = SectionFrame(page, "options")
        opts.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        for c in range(4):
            opts.body.columnconfigure(c, weight=1)

        ttk.Label(opts.body, text="format", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.mode_var = tk.StringVar(value="best")
        ttk.Radiobutton(opts.body, text="Video + Audio (mp4)", variable=self.mode_var,
                         value="best", command=self._sync_quality_state).grid(
            row=1, column=0, sticky="w", pady=(2, 10))
        ttk.Radiobutton(opts.body, text="Audio only (mp3)", variable=self.mode_var,
                         value="audio", command=self._sync_quality_state).grid(
            row=2, column=0, sticky="w")

        ttk.Label(opts.body, text="quality cap", style="Muted.TLabel").grid(
            row=0, column=1, sticky="w")
        self.quality_var = tk.StringVar(value="Best")
        self.quality_combo = ttk.Combobox(opts.body, textvariable=self.quality_var,
                                           values=list(ytw.QUALITY_HEIGHT_CAP.keys()),
                                           state="readonly", width=10)
        self.quality_combo.grid(row=1, column=1, sticky="w")

        ttk.Label(opts.body, text="extras", style="Muted.TLabel").grid(
            row=0, column=2, sticky="w")
        self.embed_thumb_var = tk.BooleanVar(value=self.cfg.get("embed_thumbnail", True))
        ttk.Checkbutton(opts.body, text="Embed thumbnail", variable=self.embed_thumb_var
                         ).grid(row=1, column=2, sticky="w")
        self.subs_var = tk.BooleanVar(value=self.cfg.get("write_subs", False))
        ttk.Checkbutton(opts.body, text="Download subtitles", variable=self.subs_var
                         ).grid(row=2, column=2, sticky="w")
        self.playlist_var = tk.BooleanVar(value=self.cfg.get("download_playlist", False))
        ttk.Checkbutton(opts.body, text="Whole playlist", variable=self.playlist_var
                         ).grid(row=3, column=2, sticky="w")

        ttk.Label(opts.body, text="sub langs", style="Muted.TLabel").grid(
            row=0, column=3, sticky="w")
        self.sublang_var = tk.StringVar(value=self.cfg.get("sub_langs", "en"))
        ttk.Entry(opts.body, textvariable=self.sublang_var, width=10).grid(
            row=1, column=3, sticky="w")

        # -- Destination panel --
        dest = SectionFrame(page, "destination")
        dest.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        dest.body.columnconfigure(1, weight=1)

        ttk.Label(dest.body, text="folder", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.outdir_var = tk.StringVar(value=self.cfg.get("output_dir", ""))
        ttk.Entry(dest.body, textvariable=self.outdir_var).grid(
            row=0, column=1, sticky="ew", padx=8)
        ttk.Button(dest.body, text="BROWSE", command=self._browse_outdir).grid(row=0, column=2)

        ttk.Label(dest.body, text="filename", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        self.template_var = tk.StringVar(value=self.cfg.get("filename_template",
                                                              config.DEFAULTS["filename_template"]))
        ttk.Entry(dest.body, textvariable=self.template_var).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(8, 0))

        # -- Action row + progress --
        actions = ttk.Frame(page, style="Panel.TFrame")
        actions.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 4))
        actions.columnconfigure(2, weight=1)

        ttk.Button(actions, text="+ ADD TO QUEUE", command=self._add_to_queue
                   ).grid(row=0, column=0, padx=(0, 8))
        self.download_btn = ttk.Button(actions, text="\u25b6 DOWNLOAD NOW", style="Accent.TButton",
                                        command=self._download_now)
        self.download_btn.grid(row=0, column=1)
        self.cancel_btn = ttk.Button(actions, text="\u25a0 CANCEL", style="Danger.TButton",
                                      command=self._cancel_current, state="disabled")
        self.cancel_btn.grid(row=0, column=3, padx=(8, 0))

        prog_frame = ttk.Frame(page, style="Panel.TFrame")
        prog_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 14))
        prog_frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate",
                                         style="Horizontal.TProgressbar")
        self.progress.grid(row=0, column=0, sticky="ew")
        self.progress_label = ttk.Label(prog_frame, style="Muted.TLabel",
                                         text="0.0%  \u2022  --  \u2022  ETA --")
        self.progress_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self._sync_quality_state()
        return page

    def _sync_quality_state(self):
        self.quality_combo.configure(
            state="disabled" if self.mode_var.get() == "audio" else "readonly")

    # ---------------- QUEUE PAGE ----------------
    def _build_queue_page(self, parent):
        page = ttk.Frame(parent, style="Panel.TFrame")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        header = ttk.Frame(page, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        ttk.Label(header, text="\u25c8 DOWNLOAD QUEUE", style="Accent.TLabel").pack(side="left")
        ttk.Button(header, text="\u25b6 START QUEUE", style="Accent.TButton",
                   command=self._start_queue).pack(side="right", padx=(6, 0))
        ttk.Button(header, text="CLEAR", command=self._clear_queue).pack(side="right", padx=(6, 0))
        ttk.Button(header, text="REMOVE SELECTED", command=self._remove_selected_queue
                   ).pack(side="right", padx=(6, 0))

        cols = ("status", "mode", "quality", "url")
        self.queue_tree = ttk.Treeview(page, columns=cols, show="headings", height=16)
        for c, w, anchor in [("status", 110, "w"), ("mode", 90, "w"),
                              ("quality", 80, "w"), ("url", 560, "w")]:
            self.queue_tree.heading(c, text=c.upper())
            self.queue_tree.column(c, width=w, anchor=anchor)
        self.queue_tree.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        scroll = ttk.Scrollbar(page, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ns", pady=(0, 16))
        return page

    # ---------------- LOG PAGE ----------------
    def _build_log_page(self, parent):
        page = ttk.Frame(parent, style="Panel.TFrame")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        header = ttk.Frame(page, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        ttk.Label(header, text="\u25c8 RAW TERMINAL OUTPUT", style="Accent.TLabel").pack(side="left")
        ttk.Button(header, text="CLEAR", command=self._clear_log).pack(side="right")

        wrap = ttk.Frame(page, style="BorderedPanel.TFrame")
        wrap.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        self.log_text = tk.Text(wrap, bg=BG0, fg=theme.OK_GREEN, insertbackground=Theme.accent(),
                                 font=Fonts.mono_small, bd=0, highlightthickness=0,
                                 wrap="none", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self.log_text.tag_configure("err", foreground=theme.ERR_RED)
        self.log_text.tag_configure("warn", foreground=theme.WARN_AMBER)
        self.log_text.tag_configure("dim", foreground=FG_DIM)

        vscroll = ttk.Scrollbar(wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=vscroll.set)
        vscroll.grid(row=0, column=1, sticky="ns")
        return page

    # ---------------- SETTINGS PAGE ----------------
    def _build_settings_page(self, parent):
        page = ttk.Frame(parent, style="Panel.TFrame")
        page.columnconfigure(0, weight=1)

        paths = SectionFrame(page, "binaries")
        paths.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        paths.body.columnconfigure(1, weight=1)

        ttk.Label(paths.body, text="yt-dlp.exe", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.set_ytdlp_var = tk.StringVar(value=self.cfg.get("ytdlp_path", "") or (self.ytdlp_path or ""))
        ttk.Entry(paths.body, textvariable=self.set_ytdlp_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(paths.body, text="BROWSE", command=self._browse_ytdlp).grid(row=0, column=2)

        ttk.Label(paths.body, text="ffmpeg (optional)", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        self.set_ffmpeg_var = tk.StringVar(value=self.cfg.get("ffmpeg_path", ""))
        ttk.Entry(paths.body, textvariable=self.set_ffmpeg_var).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(paths.body, text="BROWSE", command=self._browse_ffmpeg).grid(
            row=1, column=2, pady=(8, 0))

        actions = ttk.Frame(paths.body, style="Panel.TFrame")
        actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(actions, text="TEST / DETECT", command=self._test_ytdlp).pack(side="left")
        ttk.Button(actions, text="CHECK FOR UPDATE", command=self._update_ytdlp).pack(
            side="left", padx=(8, 0))
        self.settings_status = ttk.Label(paths.body, style="Ok.TLabel", text="")
        self.settings_status.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        appearance = SectionFrame(page, "appearance")
        appearance.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        ttk.Label(appearance.body, text="accent color", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w")
        accent_row = ttk.Frame(appearance.body, style="Panel.TFrame")
        accent_row.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.accent_var = tk.StringVar(value=Theme.accent_name)
        for name in theme.PALETTES:
            ttk.Radiobutton(accent_row, text=name.upper(), variable=self.accent_var,
                             value=name, command=self._apply_accent).pack(side="left", padx=(0, 12))

        about = SectionFrame(page, "about")
        about.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        ttk.Label(about.body, style="Muted.TLabel", justify="left", text=(
            f"{APP_TITLE} v{APP_VERSION} \u2014 a lightweight retro front-end for yt-dlp.\n"
            "Built with Python + tkinter only (no external runtime deps).\n"
            "This tool does not modify yt-dlp itself; it just builds and runs "
            "commands for it."
        )).grid(row=0, column=0, sticky="w")
        link = ttk.Label(about.body, style="Accent.TLabel", text="yt-dlp project on GitHub \u2197",
                          cursor="hand2")
        link.grid(row=1, column=0, sticky="w", pady=(6, 0))
        link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/yt-dlp/yt-dlp"))

        save_row = ttk.Frame(page, style="Panel.TFrame")
        save_row.grid(row=3, column=0, sticky="w", padx=16, pady=(8, 16))
        ttk.Button(save_row, text="SAVE SETTINGS", style="Accent.TButton",
                   command=self._save_settings).pack(side="left")
        return page

    # ------------------------------------------------------------------
    # Behaviour: fetching info
    # ------------------------------------------------------------------
    def _fetch_info(self):
        url = self.url_var.get().strip()
        if not url:
            return
        if not self._require_ytdlp():
            return
        self.info_label.configure(text="fetching metadata...", style="Muted.TLabel")
        self.status_dot.set_state("busy")
        self.status_label.configure(text="FETCHING")

        def work():
            try:
                info = ytw.fetch_info(self.ytdlp_path, url)
                self.ui_queue.put(("info_ok", info))
            except Exception as exc:  # noqa: BLE001
                self.ui_queue.put(("info_err", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _require_ytdlp(self):
        if self.ytdlp_path:
            return True
        self._resolve_ytdlp()
        if self.ytdlp_path:
            self.ver_label.configure(text=f"yt-dlp {self.ytdlp_version}")
            return True
        messagebox.showerror(APP_TITLE, "yt-dlp executable not found.\n"
                                         "Set its path in the SETTINGS tab.")
        return False

    # ------------------------------------------------------------------
    # Behaviour: building a job spec from current form state
    # ------------------------------------------------------------------
    def _current_job_spec(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo(APP_TITLE, "Enter a URL first.")
            return None
        outdir = self.outdir_var.get().strip() or config.default_output_dir()
        os.makedirs(outdir, exist_ok=True)
        return {
            "url": url,
            "mode": self.mode_var.get(),
            "quality": self.quality_var.get(),
            "outdir": outdir,
            "template": self.template_var.get().strip() or config.DEFAULTS["filename_template"],
            "embed_thumbnail": self.embed_thumb_var.get(),
            "write_subs": self.subs_var.get(),
            "sub_langs": self.sublang_var.get().strip() or "en",
            "playlist": self.playlist_var.get(),
            "status": "PENDING",
        }

    def _add_to_queue(self):
        spec = self._current_job_spec()
        if not spec:
            return
        self.download_queue.append(spec)
        self.queue_tree.insert("", "end", values=(
            spec["status"], spec["mode"], spec["quality"], spec["url"]))
        self.queue_badge.configure(text=f"\u2261 queue: {len(self.download_queue)}")
        self.url_var.set("")
        self.info_label.configure(text="")

    def _clear_queue(self):
        if self.current_job:
            messagebox.showinfo(APP_TITLE, "Cannot clear while a download is running.")
            return
        self.download_queue.clear()
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        self.queue_badge.configure(text="\u2261 queue: 0")

    def _remove_selected_queue(self):
        sel = self.queue_tree.selection()
        for item in sel:
            idx = self.queue_tree.index(item)
            self.queue_tree.delete(item)
            if 0 <= idx < len(self.download_queue):
                del self.download_queue[idx]
        self.queue_badge.configure(text=f"\u2261 queue: {len(self.download_queue)}")

    def _start_queue(self):
        if self.current_job:
            return
        if not self.download_queue:
            messagebox.showinfo(APP_TITLE, "Queue is empty.")
            return
        self._select_page("QUEUE")
        self._run_next_in_queue()

    def _run_next_in_queue(self):
        if not self.download_queue:
            self._append_log("[queue] all jobs complete.", tag="dim")
            return
        spec = self.download_queue[0]
        self._update_queue_row(0, "DOWNLOADING")
        self._launch_job(spec, on_finished=self._on_queue_job_finished)

    def _on_queue_job_finished(self, success):
        if self.download_queue:
            self._update_queue_row(0, "DONE" if success else "ERROR")
            self.download_queue.pop(0)
        self.queue_badge.configure(text=f"\u2261 queue: {len(self.download_queue)}")
        self.after(400, self._run_next_in_queue)

    def _update_queue_row(self, index, status):
        children = self.queue_tree.get_children()
        if index >= len(children):
            return
        item = children[index]
        vals = list(self.queue_tree.item(item, "values"))
        vals[0] = status
        self.queue_tree.item(item, values=vals)

    # ------------------------------------------------------------------
    # Behaviour: running a download
    # ------------------------------------------------------------------
    def _download_now(self):
        if self.current_job:
            messagebox.showinfo(APP_TITLE, "A download is already in progress.")
            return
        spec = self._current_job_spec()
        if not spec:
            return
        self._launch_job(spec, on_finished=None)

    def _launch_job(self, spec, on_finished):
        if not self._require_ytdlp():
            if on_finished:
                on_finished(False)
            return

        cmd = ytw.build_download_cmd(
            self.ytdlp_path, spec["url"],
            mode=spec["mode"], quality_label=spec["quality"],
            output_dir=spec["outdir"], filename_template=spec["template"],
            ffmpeg_path=self.cfg.get("ffmpeg_path", ""),
            embed_thumbnail=spec["embed_thumbnail"],
            write_subs=spec["write_subs"], sub_langs=spec["sub_langs"],
            download_playlist=spec["playlist"],
        )
        self._append_log(f"$ {' '.join(cmd)}", tag="dim")

        self.progress.configure(value=0)
        self.progress_label.configure(text="0.0%  \u2022  starting...  \u2022  ETA --")
        self.status_dot.set_state("busy")
        self.status_label.configure(text="DOWNLOADING")
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")

        def on_progress(**kw):
            self.ui_queue.put(("progress", kw))

        def on_line(line):
            self.ui_queue.put(("log", line))

        def on_done(**kw):
            self.ui_queue.put(("done", kw))

        self.current_job = ytw.DownloadJob(
            cmd, on_progress=on_progress, on_line=on_line, on_done=on_done
        ).start()
        self._on_job_finished_cb = on_finished

    def _cancel_current(self):
        if self.current_job:
            self.current_job.cancel()
            self._append_log("[cancel] user requested cancel...", tag="warn")

    def _job_wrapup(self, success, cancelled, error, path):
        self.current_job = None
        self.download_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        if cancelled:
            self.status_dot.set_state("idle")
            self.status_label.configure(text="CANCELLED")
            self._append_log("[cancel] download cancelled.", tag="warn")
        elif success:
            self.status_dot.set_state("ok")
            self.status_label.configure(text="DONE")
            self.progress.configure(value=100)
            self.progress_label.configure(text="100.0%  \u2022  complete")
            self._append_log(f"[done] saved: {path or '(see destination folder)'}", tag=None)
        else:
            self.status_dot.set_state("error")
            self.status_label.configure(text="ERROR")
            self._append_log(f"[error] {error}", tag="err")
            messagebox.showerror(APP_TITLE, f"Download failed:\n{error}")

        cb = getattr(self, "_on_job_finished_cb", None)
        self._on_job_finished_cb = None
        if cb:
            cb(success)

    # ------------------------------------------------------------------
    # UI-thread event pump (worker threads never touch widgets directly)
    # ------------------------------------------------------------------
    def _pump_ui_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "progress":
                    self._on_progress_event(payload)
                elif kind == "log":
                    tag = "err" if "ERROR" in payload.upper() else None
                    self._append_log(payload, tag=tag)
                elif kind == "done":
                    self._job_wrapup(payload.get("success"), payload.get("cancelled"),
                                      payload.get("error"), payload.get("path"))
                elif kind == "info_ok":
                    self._on_info_ok(payload)
                elif kind == "info_err":
                    self._on_info_err(payload)
                elif kind == "update_ok":
                    self.settings_status.configure(text=payload, style="Ok.TLabel")
                elif kind == "update_err":
                    self.settings_status.configure(text=payload, style="Err.TLabel")
        except pyqueue.Empty:
            pass
        self.after(80, self._pump_ui_queue)

    def _on_progress_event(self, kw):
        pct = kw.get("pct")
        if pct is not None:
            self.progress.configure(value=pct)
        speed = kw.get("speed") or "--"
        eta = kw.get("eta") or "--"
        size = kw.get("size") or ""
        self.progress_label.configure(
            text=f"{pct:.1f}%  \u2022  {size}  \u2022  {speed}  \u2022  ETA {eta}")

    def _on_info_ok(self, info):
        self.status_dot.set_state("idle")
        self.status_label.configure(text="IDLE")
        text = (f"\u2713 {info['title']}   [{info['uploader']}]   "
                f"duration {info['duration_string']}   via {info['extractor']}")
        self.info_label.configure(text=text, style="Ok.TLabel")

    def _on_info_err(self, err):
        self.status_dot.set_state("error")
        self.status_label.configure(text="ERROR")
        self.info_label.configure(text=f"\u2717 {err}", style="Err.TLabel")

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def _append_log(self, line, tag=None):
        self.log_text.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {line}\n", tag or ())
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Settings page behaviour
    # ------------------------------------------------------------------
    def _browse_outdir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get() or os.path.expanduser("~"))
        if d:
            self.outdir_var.set(d)

    def _browse_ytdlp(self):
        filetypes = [("yt-dlp executable", "*.exe")] if ytw.IS_WINDOWS else [("All files", "*")]
        f = filedialog.askopenfilename(title="Locate yt-dlp", filetypes=filetypes)
        if f:
            self.set_ytdlp_var.set(f)

    def _browse_ffmpeg(self):
        filetypes = [("ffmpeg executable", "*.exe")] if ytw.IS_WINDOWS else [("All files", "*")]
        f = filedialog.askopenfilename(title="Locate ffmpeg", filetypes=filetypes)
        if f:
            self.set_ffmpeg_var.set(f)

    def _test_ytdlp(self):
        path = self.set_ytdlp_var.get().strip()
        try:
            resolved = ytw.find_ytdlp(path)
            version = ytw.get_version(resolved)
            self.settings_status.configure(
                text=f"OK: {resolved}  (version {version})", style="Ok.TLabel")
            self.ytdlp_path = resolved
            self.ytdlp_version = version
            self.ver_label.configure(text=f"yt-dlp {version}")
        except ytw.YtDlpNotFoundError as exc:
            self.settings_status.configure(text=str(exc), style="Err.TLabel")

    def _update_ytdlp(self):
        if not self.ytdlp_path:
            self._test_ytdlp()
            if not self.ytdlp_path:
                return
        self.settings_status.configure(text="checking for update...", style="Muted.TLabel")

        def work():
            try:
                out = subprocess.run(
                    [self.ytdlp_path, "-U"], capture_output=True, text=True, timeout=60,
                    startupinfo=ytw._STARTUPINFO, creationflags=ytw._CREATIONFLAGS,
                )
                msg = (out.stdout.strip() or out.stderr.strip()).splitlines()[-1] \
                    if (out.stdout.strip() or out.stderr.strip()) else "no output"
                self.ui_queue.put(("update_ok", msg))
            except Exception as exc:  # noqa: BLE001
                self.ui_queue.put(("update_err", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _apply_accent(self):
        Theme.accent_name = self.accent_var.get()
        theme.apply_ttk_style(self.style)
        self.log_text.configure(fg=theme.OK_GREEN, insertbackground=Theme.accent())
        self._append_log(f"[theme] accent set to {Theme.accent_name}", tag="dim")

    def _save_settings(self):
        self.cfg.update({
            "ytdlp_path": self.set_ytdlp_var.get().strip(),
            "ffmpeg_path": self.set_ffmpeg_var.get().strip(),
            "output_dir": self.outdir_var.get().strip(),
            "filename_template": self.template_var.get().strip(),
            "accent": self.accent_var.get(),
            "embed_thumbnail": self.embed_thumb_var.get(),
            "write_subs": self.subs_var.get(),
            "sub_langs": self.sublang_var.get().strip(),
            "download_playlist": self.playlist_var.get(),
        })
        ok = config.save(self.cfg)
        self.settings_status.configure(
            text="settings saved." if ok else "could not write config file.",
            style="Ok.TLabel" if ok else "Err.TLabel")
        self._resolve_ytdlp()

    def _on_close(self):
        if self.current_job:
            if not messagebox.askyesno(APP_TITLE, "A download is in progress. Quit anyway?"):
                return
            self.current_job.cancel()
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
