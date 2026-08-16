"""
theme.py
--------
Central palette / typography / ttk styling for the retro terminal-WM look.

Aesthetic references:
  - i3 / Hyprland / dwm "ricing": flat panels, hard borders, no gradients,
    workspace-style tab bar, waybar-style status strip.
  - Retro sci-fi command terminal: amber-on-black monochrome readouts,
    box-drawing frames, blinking status glyphs, all-caps labels.

Only stdlib (tkinter/ttk) is used — no external theming libs — to keep
the app a single lightweight, dependency-free script.
"""

import tkinter.font as tkfont

# ----------------------------------------------------------------------
# Palette --- swap ACCENT to re-skin the whole app (see Settings tab)
# ----------------------------------------------------------------------
PALETTES = {
    "amber": {
        "accent": "#ffb454",     # warm amber, classic terminal phosphor
        "accent_dim": "#8a611f",
        "accent_bright": "#ffd08a",
    },
    "green": {
        "accent": "#9ece6a",     # classic phosphor green
        "accent_dim": "#4d6b2e",
        "accent_bright": "#c3e88d",
    },
    "blue": {
        "accent": "#7aa2f7",     # i3/waybar cool blue
        "accent_dim": "#3b4f80",
        "accent_bright": "#a9c1fb",
    },
    "red": {
        "accent": "#f7768e",     # alert red
        "accent_dim": "#7a3946",
        "accent_bright": "#ff9fb2",
    },
}

BG0 = "#0a0b0d"      # deepest background (root window)
BG1 = "#0f1114"      # panel background
BG2 = "#15181c"      # raised panel / entry background
BG3 = "#1c2025"      # hover / selected row
BORDER = "#2a2f36"   # default hairline border
BORDER_LIT = "#454c56"

FG0 = "#c9d1d9"       # primary text
FG1 = "#8b949e"       # secondary / muted text
FG_DIM = "#565d66"    # faint labels, separators

OK_GREEN = "#9ece6a"
WARN_AMBER = "#e0af68"
ERR_RED = "#f7768e"

FONT_FAMILY_CANDIDATES = [
    "Cascadia Mono", "Cascadia Code", "Consolas",
    "JetBrains Mono", "Fira Code", "Courier New", "monospace",
]


class Fonts:
    """Resolved once a Tk root exists (font.families() needs a root)."""
    base = None
    mono = None
    mono_bold = None
    mono_small = None
    mono_large = None
    title = None

    @classmethod
    def init(cls, root):
        available = set(tkfont.families(root))
        family = next((f for f in FONT_FAMILY_CANDIDATES if f in available), "Courier New")
        cls.family = family
        cls.mono = tkfont.Font(family=family, size=10)
        cls.mono_bold = tkfont.Font(family=family, size=10, weight="bold")
        cls.mono_small = tkfont.Font(family=family, size=9)
        cls.mono_large = tkfont.Font(family=family, size=13, weight="bold")
        cls.title = tkfont.Font(family=family, size=11, weight="bold")


class Theme:
    """Mutable current-theme state (accent color is switchable at runtime)."""
    accent_name = "amber"

    @classmethod
    def accent(cls):
        return PALETTES[cls.accent_name]["accent"]

    @classmethod
    def accent_dim(cls):
        return PALETTES[cls.accent_name]["accent_dim"]

    @classmethod
    def accent_bright(cls):
        return PALETTES[cls.accent_name]["accent_bright"]


# ----------------------------------------------------------------------
# Box-drawing helpers for decorative terminal-chrome headers
# ----------------------------------------------------------------------
def hline(width, ch="\u2500"):
    return ch * width


def framed_title(text, width=54):
    text = f" {text} "
    pad = max(width - len(text) - 2, 0)
    left = pad // 2
    right = pad - left
    return "\u256d" + ("\u2500" * left) + text + ("\u2500" * right) + "\u256e"


def framed_bottom(width=54):
    return "\u2570" + ("\u2500" * (width - 2)) + "\u256f"


def apply_ttk_style(style):
    """Configure ttk widget styles to match the palette. Call after Fonts.init()."""
    accent = Theme.accent()
    style.theme_use("clam")

    style.configure(".", background=BG1, foreground=FG0,
                     fieldbackground=BG2, font=Fonts.mono, borderwidth=0)

    style.configure("TFrame", background=BG1)
    style.configure("Panel.TFrame", background=BG1, bordercolor=BORDER,
                     lightcolor=BORDER, darkcolor=BORDER)
    style.configure("Chrome.TFrame", background=BG0)
    # Bordered variants -- ttk.Frame has no highlightthickness option like
    # classic tk.Frame, so hairline borders are done via relief+bordercolor.
    style.configure("BorderedChrome.TFrame", background=BG0, borderwidth=1,
                     relief="solid", bordercolor=BORDER)
    style.configure("BorderedPanel.TFrame", background=BG1, borderwidth=1,
                     relief="solid", bordercolor=BORDER)

    style.configure("TLabel", background=BG1, foreground=FG0, font=Fonts.mono)
    style.configure("Muted.TLabel", background=BG1, foreground=FG1, font=Fonts.mono_small)
    style.configure("Dim.TLabel", background=BG1, foreground=FG_DIM, font=Fonts.mono_small)
    style.configure("Accent.TLabel", background=BG1, foreground=accent, font=Fonts.mono_bold)
    style.configure("Title.TLabel", background=BG0, foreground=accent, font=Fonts.title)
    style.configure("Bar.TLabel", background=BG0, foreground=FG1, font=Fonts.mono_small)
    style.configure("BarAccent.TLabel", background=BG0, foreground=accent, font=Fonts.mono_small)
    style.configure("Ok.TLabel", background=BG1, foreground=OK_GREEN, font=Fonts.mono_bold)
    style.configure("Warn.TLabel", background=BG1, foreground=WARN_AMBER, font=Fonts.mono_bold)
    style.configure("Err.TLabel", background=BG1, foreground=ERR_RED, font=Fonts.mono_bold)

    style.configure("TEntry", fieldbackground=BG2, foreground=FG0,
                     insertcolor=accent, bordercolor=BORDER, lightcolor=BORDER,
                     darkcolor=BORDER, borderwidth=1, relief="flat")
    style.map("TEntry", bordercolor=[("focus", accent)])

    style.configure("TButton", background=BG2, foreground=FG0,
                     bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                     borderwidth=1, relief="flat", padding=(10, 6), font=Fonts.mono)
    style.map("TButton",
              background=[("active", BG3), ("pressed", BG3)],
              bordercolor=[("active", accent)],
              foreground=[("disabled", FG_DIM)])

    style.configure("Accent.TButton", background=BG2, foreground=accent,
                     bordercolor=accent, lightcolor=accent, darkcolor=accent,
                     borderwidth=1, relief="flat", padding=(12, 7), font=Fonts.mono_bold)
    style.map("Accent.TButton",
              background=[("active", accent), ("pressed", accent)],
              foreground=[("active", BG0), ("pressed", BG0)])

    style.configure("Danger.TButton", background=BG2, foreground=ERR_RED,
                     bordercolor=ERR_RED, borderwidth=1, relief="flat",
                     padding=(10, 6), font=Fonts.mono)
    style.map("Danger.TButton", background=[("active", ERR_RED)],
              foreground=[("active", BG0)])

    style.configure("Tab.TButton", background=BG0, foreground=FG1,
                     borderwidth=0, relief="flat", padding=(12, 6), font=Fonts.mono)
    style.map("Tab.TButton", background=[("active", BG1)], foreground=[("active", FG0)])

    style.configure("TabActive.TButton", background=BG1, foreground=accent,
                     borderwidth=0, relief="flat", padding=(12, 6), font=Fonts.mono_bold)

    style.configure("TCombobox", fieldbackground=BG2, background=BG2,
                     foreground=FG0, bordercolor=BORDER, arrowcolor=accent,
                     borderwidth=1, relief="flat", padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", BG2)],
              bordercolor=[("focus", accent)])

    style.configure("TCheckbutton", background=BG1, foreground=FG0,
                     font=Fonts.mono, focuscolor=BG1)
    style.map("TCheckbutton", foreground=[("active", accent)])

    style.configure("TRadiobutton", background=BG1, foreground=FG0,
                     font=Fonts.mono, focuscolor=BG1)
    style.map("TRadiobutton", foreground=[("active", accent)])

    style.configure("Horizontal.TProgressbar", background=accent,
                     troughcolor=BG2, bordercolor=BORDER,
                     lightcolor=accent, darkcolor=accent, thickness=16)

    style.configure("Treeview", background=BG2, fieldbackground=BG2,
                     foreground=FG0, bordercolor=BORDER, borderwidth=1,
                     rowheight=24, font=Fonts.mono_small)
    style.configure("Treeview.Heading", background=BG1, foreground=accent,
                     font=Fonts.mono_bold, borderwidth=1, relief="flat")
    style.map("Treeview", background=[("selected", BG3)],
              foreground=[("selected", accent)])

    style.configure("TSeparator", background=BORDER)
    style.configure("Vertical.TScrollbar", background=BG2, troughcolor=BG1,
                     bordercolor=BG1, arrowcolor=FG1)
