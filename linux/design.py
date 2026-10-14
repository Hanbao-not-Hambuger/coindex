"""Small, dependency-free visual primitives for the Linux Tk interface."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

try:  # package import in the app, direct import in the standalone preview
    from .palette import TOKENS
except ImportError:
    from palette import TOKENS


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


def _rounded_image(root: tk.Misc, fill: str, border: str, focus: str | None = None,
                   radius: int = 6) -> tk.PhotoImage:
    """Rasterize a tiny rounded tile; ttk stretches its center while keeping corners."""
    size = 24
    image = tk.PhotoImage(master=root, width=size, height=size)

    def inside(x: int, y: int, left: int, top: int, right: int, bottom: int, r: int) -> bool:
        cx = min(max(x, left + r), right - r - 1)
        cy = min(max(y, top + r), bottom - r - 1)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    for y in range(size):
        row: list[str | None] = []
        for x in range(size):
            if focus and inside(x, y, 0, 0, size, size, radius):
                color = focus
                if inside(x, y, 2, 2, size - 2, size - 2, max(1, radius - 2)):
                    color = border if border != fill else focus
                    if inside(x, y, 3, 3, size - 3, size - 3, max(1, radius - 3)):
                        color = fill
            elif inside(x, y, 0, 0, size, size, radius):
                color = border
                if inside(x, y, 1, 1, size - 1, size - 1, max(1, radius - 1)):
                    color = fill
            else:
                color = None
            row.append(color)
        x = 0
        while x < size:
            color = row[x]
            if color is None:
                x += 1
                continue
            end = x + 1
            while end < size and row[end] == color:
                end += 1
            image.put("{" + " ".join([color] * (end - x)) + "}", to=(x, y))
            x = end
    return image


def _button_element(style: ttk.Style, root: tk.Misc, element: str, colors: dict[str, str],
                    radius: int = 6) -> list[tk.PhotoImage]:
    normal = colors["normal"]
    border = colors.get("border", normal)
    focus = colors.get("focus", TOKENS["accent"])
    images = [
        _rounded_image(root, normal, border, radius=radius),
        _rounded_image(root, colors.get("active", normal), border, radius=radius),
        _rounded_image(root, colors.get("pressed", normal), border, radius=radius),
        _rounded_image(root, colors.get("disabled", TOKENS["subtle"]),
                       colors.get("disabled_border", TOKENS["border"]), radius=radius),
        _rounded_image(root, normal, border, focus=focus, radius=radius),
    ]
    style.element_create(element, "image", images[0],
                         ("disabled", images[3]), ("focus", images[4]),
                         ("pressed", images[2]), ("active", images[1]),
                         border=(8, 8, 8, 8), sticky="nsew")
    return images


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
    style.configure("Search.TEntry", fieldbackground=TOKENS["surface"], foreground=TOKENS["ink"],
                    insertcolor=TOKENS["ink"], bordercolor=TOKENS["surface"],
                    lightcolor=TOKENS["surface"], darkcolor=TOKENS["surface"],
                    borderwidth=0, padding=0, relief="flat")
    style.layout("Search.TEntry", [("Entry.field", {"sticky": "nswe", "children": [
        ("Entry.padding", {"sticky": "nswe", "children": [
            ("Entry.textarea", {"sticky": "nswe"})]})]})])
    style.configure("TCombobox", fieldbackground=TOKENS["surface"], background=TOKENS["surface"],
                    foreground=TOKENS["ink"], arrowcolor=TOKENS["muted"], bordercolor=TOKENS["border"],
                    lightcolor=TOKENS["border"], darkcolor=TOKENS["border"], padding=(8, 6), relief="flat")
    style.map("TCombobox", fieldbackground=[("readonly", TOKENS["surface"])],
              selectbackground=[("readonly", TOKENS["accent_wash"])],
              selectforeground=[("readonly", TOKENS["ink"])],
              bordercolor=[("focus", TOKENS["accent"])], lightcolor=[("focus", TOKENS["accent"])])

    if not hasattr(root, "_coindex_button_images"):
        root._coindex_button_images = []
    button_specs = {
        "TButton": {"normal": TOKENS["surface"], "border": TOKENS["border"],
                    "active": TOKENS["subtle"], "pressed": TOKENS["accent_wash"]},
        "Accent.TButton": {"normal": TOKENS["accent"], "border": TOKENS["accent"],
                           "active": "#707BE0", "pressed": "#4E59BC",
                           "disabled": TOKENS["subtle"], "focus": TOKENS["surface"]},
        "Quiet.TButton": {"normal": TOKENS["subtle"], "border": TOKENS["subtle"],
                          "active": TOKENS["accent_wash"], "pressed": TOKENS["border"]},
        "Danger.TButton": {"normal": TOKENS["surface"], "border": TOKENS["border"],
                           "active": "#FCEFEF", "pressed": "#F9EAEA"},
        "Nav.TButton": {"normal": TOKENS["sidebar"], "border": TOKENS["sidebar"],
                        "active": TOKENS["subtle"], "pressed": TOKENS["accent_wash"]},
        "Selected.Nav.TButton": {"normal": TOKENS["accent_wash"], "border": TOKENS["accent_wash"],
                                 "active": TOKENS["accent_wash"], "pressed": TOKENS["accent_wash"]},
    }
    foregrounds = {
        "TButton": TOKENS["ink"], "Accent.TButton": TOKENS["surface"],
        "Quiet.TButton": TOKENS["ink"], "Danger.TButton": "#B74343",
        "Nav.TButton": TOKENS["muted"], "Selected.Nav.TButton": TOKENS["accent"],
    }
    button_base = {"font": (family, 10, "bold"), "padding": (12, 7),
                   "borderwidth": 0, "focuscolor": TOKENS["accent"]}
    for button_style, colors in button_specs.items():
        element = "Coindex." + button_style.replace(".", "_") + ".button"
        if element not in style.element_names():
            root._coindex_button_images.extend(_button_element(style, root, element, colors,
                                                               radius=5 if "Nav" in button_style else 6))
        style.layout(button_style, [(element, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [
                ("Button.label", {"sticky": "nswe"})]})]})])
        style.configure(button_style, **button_base, background=colors["normal"],
                        foreground=foregrounds[button_style])
        style.map(button_style, background=[("disabled", colors.get("disabled", TOKENS["subtle"])),
                                            ("pressed", colors.get("pressed", colors["normal"])),
                                            ("active", colors.get("active", colors["normal"]))],
                  foreground=[("disabled", TOKENS["muted"])])
    for button_style in ("Nav.TButton", "Selected.Nav.TButton"):
        style.configure(button_style, font=(family, 10, "bold" if button_style.startswith("Selected") else "normal"),
                        padding=(10, 7), anchor="w")

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
