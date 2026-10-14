"""Small, dependency-free visual primitives for the Linux Tk interface."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk


TOKENS = {
    "canvas": "#F8F9FC",
    "surface": "#FFFFFF",
    "sidebar": "#F2F3F7",
    "subtle": "#F4F5F9",
    "border": "#E3E5ED",
    "ink": "#20222B",
    "muted": "#737787",
    "accent": "#5E6AD2",
    "accent_wash": "#ECEEFD",
    "success": "#2E8B65",
    "warning": "#A76A28",
}


def _system_font(root: tk.Misc) -> str:
    """Choose an installed sans font with Chinese glyph coverage when available."""
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        available = set()
    for family in (
        "Noto Sans CJK SC", "Noto Sans CJK JP", "Microsoft YaHei",
        "WenQuanYi Micro Hei", "Noto Sans", "DejaVu Sans", "Arial",
    ):
        if family in available:
            return family
    try:
        return tkfont.nametofont("TkDefaultFont", root=root).actual("-family")
    except tk.TclError:
        return "TkDefaultFont"


def apply_theme(root: tk.Misc) -> str:
    """Apply the light ttk palette and return the selected system font family."""
    family = _system_font(root)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    default = (family, 10)
    small = (family, 9)
    root.configure(background=TOKENS["canvas"])
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(name, root=root).configure(family=family, size=10)
        except tk.TclError:
            continue

    style.configure(".", font=default, background=TOKENS["canvas"], foreground=TOKENS["ink"])
    style.configure("TFrame", background=TOKENS["canvas"])
    style.configure("TLabel", background=TOKENS["canvas"], foreground=TOKENS["ink"])
    style.configure("Panel.TFrame", background=TOKENS["surface"])
    style.configure("Panel.TLabel", background=TOKENS["surface"], foreground=TOKENS["ink"])
    style.configure("Muted.TLabel", background=TOKENS["canvas"], foreground=TOKENS["muted"], font=small)
    style.configure("Title.TLabel", background=TOKENS["canvas"], foreground=TOKENS["ink"],
                    font=(family, 19, "bold"))
    style.configure("Caption.TLabel", background=TOKENS["canvas"], foreground=TOKENS["muted"], font=small)

    style.configure("TEntry", fieldbackground=TOKENS["surface"], foreground=TOKENS["ink"],
                    insertcolor=TOKENS["ink"], bordercolor=TOKENS["border"], lightcolor=TOKENS["border"],
                    darkcolor=TOKENS["border"], padding=(9, 7), relief="flat")
    style.map("TEntry", bordercolor=[("focus", TOKENS["accent"])],
              lightcolor=[("focus", TOKENS["accent"])], darkcolor=[("focus", TOKENS["accent"])])
    style.configure("TCombobox", fieldbackground=TOKENS["surface"], background=TOKENS["surface"],
                    foreground=TOKENS["ink"], arrowcolor=TOKENS["muted"], bordercolor=TOKENS["border"],
                    lightcolor=TOKENS["border"], darkcolor=TOKENS["border"], padding=(8, 6), relief="flat")
    style.map("TCombobox", fieldbackground=[("readonly", TOKENS["surface"])],
              selectbackground=[("readonly", TOKENS["accent_wash"])],
              selectforeground=[("readonly", TOKENS["ink"])],
              bordercolor=[("focus", TOKENS["accent"])], lightcolor=[("focus", TOKENS["accent"])])

    button_base = {"font": (family, 10, "bold"), "padding": (12, 7), "relief": "flat",
                   "borderwidth": 1, "focuscolor": TOKENS["accent"]}
    style.configure("TButton", **button_base, background=TOKENS["surface"], foreground=TOKENS["ink"],
                    bordercolor=TOKENS["border"])
    style.map("TButton", background=[("disabled", TOKENS["subtle"]), ("pressed", TOKENS["subtle"]),
                                      ("active", TOKENS["subtle"])],
              foreground=[("disabled", TOKENS["muted"])],
              bordercolor=[("focus", TOKENS["accent"])])
    style.configure("Accent.TButton", **button_base, background=TOKENS["accent"],
                    foreground=TOKENS["surface"], bordercolor=TOKENS["accent"])
    style.map("Accent.TButton", background=[("disabled", TOKENS["subtle"]),
                                             ("pressed", "#4E59BC"), ("active", "#707BE0")],
              foreground=[("disabled", TOKENS["muted"])],
              bordercolor=[("focus", TOKENS["accent"])])
    style.configure("Quiet.TButton", **button_base, background=TOKENS["subtle"],
                    foreground=TOKENS["ink"], bordercolor=TOKENS["subtle"])
    style.map("Quiet.TButton", background=[("disabled", TOKENS["subtle"]),
                                            ("pressed", TOKENS["border"]), ("active", TOKENS["accent_wash"])],
              foreground=[("disabled", TOKENS["muted"])], bordercolor=[("focus", TOKENS["accent"])])
    style.configure("Danger.TButton", **button_base, background=TOKENS["surface"],
                    foreground="#B74343", bordercolor=TOKENS["border"])
    style.map("Danger.TButton", background=[("disabled", TOKENS["subtle"]),
                                             ("pressed", "#F9EAEA"), ("active", "#FCEFEF")],
              foreground=[("disabled", TOKENS["muted"])], bordercolor=[("focus", "#B74343")])
    style.configure("Nav.TButton", font=(family, 10), background=TOKENS["sidebar"],
                    foreground=TOKENS["muted"], borderwidth=0, padding=(10, 7), anchor="w", relief="flat")
    style.map("Nav.TButton", background=[("disabled", TOKENS["sidebar"]),
                                          ("pressed", TOKENS["accent_wash"]), ("active", TOKENS["subtle"])],
              foreground=[("disabled", TOKENS["muted"])])
    style.configure("Selected.Nav.TButton", font=(family, 10, "bold"), background=TOKENS["accent_wash"],
                    foreground=TOKENS["accent"], borderwidth=0, padding=(10, 7), anchor="w", relief="flat")
    style.map("Selected.Nav.TButton", background=[("disabled", TOKENS["accent_wash"]),
                                                   ("pressed", TOKENS["accent_wash"]),
                                                   ("active", TOKENS["accent_wash"])])

    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, font=default, background=TOKENS["canvas"], foreground=TOKENS["ink"],
                        indicatorcolor=TOKENS["surface"], padding=(2, 3), focuscolor=TOKENS["accent"])
        style.map(name, background=[("active", TOKENS["canvas"])],
                  foreground=[("disabled", TOKENS["muted"])],
                  indicatorcolor=[("selected", TOKENS["accent"]), ("disabled", TOKENS["subtle"])])

    style.configure("Treeview", font=default, rowheight=40, background=TOKENS["surface"],
                    fieldbackground=TOKENS["surface"], foreground=TOKENS["ink"],
                    bordercolor=TOKENS["border"], lightcolor=TOKENS["border"], darkcolor=TOKENS["border"],
                    relief="flat")
    style.map("Treeview", background=[("selected", TOKENS["accent_wash"])],
              foreground=[("selected", TOKENS["ink"])])
    style.configure("Treeview.Heading", font=(family, 9, "bold"), background=TOKENS["subtle"],
                    foreground=TOKENS["muted"], relief="flat", padding=(9, 8), borderwidth=0)
    style.map("Treeview.Heading", background=[("active", TOKENS["subtle"])])
    style.configure("TScrollbar", background=TOKENS["subtle"], troughcolor=TOKENS["canvas"],
                    bordercolor=TOKENS["canvas"], arrowcolor=TOKENS["muted"], relief="flat")
    style.map("TScrollbar", background=[("active", TOKENS["border"])])
    return family


def _rounded_points(left: float, top: float, right: float, bottom: float, radius: float) -> list[float]:
    radius = max(0, min(radius, (right - left) / 2, (bottom - top) / 2))
    return [left + radius, top, right - radius, top, right, top, right, top + radius,
            right, bottom - radius, right, bottom, right - radius, bottom, left + radius, bottom,
            left, bottom, left, bottom - radius, left, top + radius, left, top]


class RoundedPanel(tk.Canvas):
    """A rounded, outlined panel whose body remains an ordinary Tk frame."""

    def __init__(self, parent: tk.Misc, fill: str = TOKENS["surface"], outline: str = TOKENS["border"],
                 radius: int = 12, padding: int = 16, **canvas_kwargs):
        self.fill, self.outline, self.radius, self.padding = fill, outline, radius, padding
        canvas_kwargs.setdefault("background", parent.cget("background") if "background" in parent.keys() else TOKENS["canvas"])
        canvas_kwargs.setdefault("highlightthickness", 0)
        canvas_kwargs.setdefault("borderwidth", 0)
        canvas_kwargs.setdefault("width", 1)
        canvas_kwargs.setdefault("height", 1)
        super().__init__(parent, **canvas_kwargs)
        self.body = tk.Frame(self, background=fill, borderwidth=0, highlightthickness=0)
        self._shape = self.create_polygon(0, 0, 0, 0, smooth=True, splinesteps=16,
                                          fill=fill, outline=outline, width=1)
        self._window = self.create_window(padding, padding, anchor="nw", window=self.body)
        self.bind("<Configure>", self._resize, add="+")
        self.body.bind("<Configure>", self._body_changed, add="+")
        self.after_idle(self._sync_size)

    def set_outline(self, color: str) -> None:
        self.outline = color
        self.itemconfigure(self._shape, outline=color)

    def _body_changed(self, _event=None) -> None:
        self.after_idle(self._sync_size)

    def _sync_size(self) -> None:
        try:
            height = max(1, self.body.winfo_reqheight() + self.padding * 2)
            if int(float(self.cget("height"))) != height:
                self.configure(height=height)
            self._resize()
        except tk.TclError:
            pass

    def _resize(self, _event=None) -> None:
        try:
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
            inset = 0.5
            self.coords(self._shape, *_rounded_points(inset, inset, width - inset, height - inset, self.radius))
            self.itemconfigure(self._window, width=max(1, width - self.padding * 2))
        except tk.TclError:
            pass


class Icon(tk.Canvas):
    """Tiny line icon canvas using native Tk drawing primitives."""

    def __init__(self, parent: tk.Misc, name: str, size: int = 18,
                 color: str = TOKENS["muted"], bg: str = TOKENS["surface"], **kwargs):
        self.name, self.size, self.color = name.lower(), size, color
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("background", bg)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("borderwidth", 0)
        super().__init__(parent, **kwargs)
        self._draw()

    def _draw(self) -> None:
        scale = self.size / 18
        def xy(points):
            return tuple(round(p * scale, 2) for p in points)
        def line(points, **opts):
            self.create_line(*xy(points), fill=self.color, width=max(1, 1.65 * scale),
                             capstyle=tk.ROUND, joinstyle=tk.ROUND, **opts)
        def oval(box, **opts):
            self.create_oval(*xy(box), outline=self.color, width=max(1, 1.6 * scale), **opts)
        n = self.name
        if n == "search":
            oval((3, 3, 11, 11)); line((10, 10, 15, 15))
        elif n == "inbox":
            line((3, 7, 4, 3, 14, 3, 15, 7, 15, 14, 3, 14, 3, 7))
            line((3, 9, 7, 9, 8, 11, 10, 11, 11, 9, 15, 9))
        elif n == "chat":
            self.create_oval(*xy((3, 3, 15, 13)), outline=self.color, width=max(1, 1.6 * scale))
            line((6, 12, 5, 15, 9, 13))
        elif n == "plus":
            line((9, 3, 9, 15)); line((3, 9, 15, 9))
        elif n == "settings":
            oval((5, 5, 13, 13)); oval((8, 8, 10, 10))
            line((9, 2, 9, 4))
            line((9, 14, 9, 16)); line((2, 9, 4, 9)); line((14, 9, 16, 9))
            line((4, 4, 5.5, 5.5)); line((12.5, 12.5, 14, 14)); line((14, 4, 12.5, 5.5)); line((5.5, 12.5, 4, 14))
        elif n == "refresh":
            line((14, 7, 14, 3, 10, 3)); line((14, 4, 11, 3, 8, 3, 5, 5, 4, 8))
            line((4, 11, 4, 15, 8, 15)); line((4, 14, 7, 15, 10, 15, 13, 13, 14, 10))
        elif n == "check":
            line((3, 9, 7, 13, 15, 4))
        elif n == "clock":
            oval((3, 3, 15, 15)); line((9, 5.5, 9, 9, 12, 10.5))
        elif n == "arrow":
            line((3, 9, 15, 9)); line((10, 4, 15, 9, 10, 14))
        else:
            raise ValueError(f"unknown icon: {self.name}")
