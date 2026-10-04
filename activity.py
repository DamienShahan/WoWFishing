"""Readable activity cards with drawn icons, independent of emoji font support."""
from datetime import datetime

import customtkinter as ctk
from PIL import Image, ImageDraw

PANEL = "#1e1e2e"
CARD = "#252537"
TEXT = "#f2f3ff"
MUTED = "#a5a8bd"
STYLES = {
    "ready": ("#73d9b1", "#233c37"),
    "start": ("#a9b9ff", "#303851"),
    "audio": ("#9fb6fa", "#303851"),
    "cast": ("#81c8fa", "#263b50"),
    "bite": ("#73d9b1", "#233c37"),
    "lure": ("#c6a5f7", "#3a304b"),
    "wait": ("#e5bf7b", "#443b2d"),
    "timeout": ("#e5bf7b", "#443b2d"),
    "error": ("#ff9aa9", "#4a2c3a"),
    "warning": ("#e5bf7b", "#443b2d"),
    "stop": ("#c6a5f7", "#3a304b"),
    "summary": ("#73d9b1", "#233c37"),
    "info": ("#b4b9d0", "#343749"),
}


def make_icon(kind, color):
    """Supersampled line art stays crisp at Windows display scaling levels."""
    image = Image.new("RGBA", (96, 96))
    draw = ImageDraw.Draw(image)

    def line(points):
        draw.line([(x * 4, y * 4) for x, y in points], fill=color, width=7, joint="curve")

    def oval(box):
        draw.ellipse(tuple(n * 4 for n in box), outline=color, width=7)

    if kind == "bite":
        oval((5, 7, 19, 17))
        line([(5, 12), (2, 8), (2, 16), (5, 12)])
        draw.ellipse((60, 39, 68, 47), fill=color)
    elif kind == "cast":
        line([(4, 19), (15, 4), (19, 4), (19, 14)])
        draw.arc((44, 40, 80, 76), 0, 180, fill=color, width=7)
        line([(4, 21), (20, 21)])
    elif kind in ("wait", "timeout"):
        oval((3, 3, 21, 21))
        line([(12, 6), (12, 12), (16, 14)])
    elif kind in ("error", "warning"):
        line([(12, 3), (22, 20), (2, 20), (12, 3)])
        line([(12, 9), (12, 13)])
        draw.ellipse((44, 62, 52, 70), fill=color)
    elif kind == "start":
        line([(7, 4), (20, 12), (7, 20), (7, 4)])
    elif kind == "stop":
        line([(5, 21), (5, 3), (13, 3), (13, 5), (21, 5), (18, 9), (21, 13), (12, 13), (12, 11), (5, 11)])
    elif kind == "chevron_down":
        line([(6, 9), (12, 15), (18, 9)])
    elif kind == "chevron_up":
        line([(6, 15), (12, 9), (18, 15)])
    elif kind == "audio":
        line([(3, 10), (7, 10), (12, 5), (12, 19), (7, 14), (3, 14), (3, 10)])
        draw.arc((36, 20, 84, 76), -60, 60, fill=color, width=7)
    elif kind == "lure":
        line([(6, 4), (15, 4), (15, 13)])
        draw.arc((20, 32, 64, 80), 0, 180, fill=color, width=7)
        line([(5, 14), (5, 12)])
    elif kind == "summary":
        line([(4, 5), (4, 20), (21, 20)])
        line([(9, 15), (9, 10)])
        line([(14, 15), (14, 5)])
        line([(19, 15), (19, 8)])
    elif kind == "ready":
        oval((3, 3, 21, 21))
        line([(7, 12), (11, 16), (17, 9)])
    else:
        oval((3, 3, 21, 21))
        line([(12, 11), (12, 17)])
        draw.ellipse((44, 25, 52, 33), fill=color)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(24, 24))


class ActivityCard(ctk.CTkFrame):
    def __init__(self, parent, event, icon):
        super().__init__(parent, fg_color=CARD, corner_radius=12)
        self.event = event
        self.grid_columnconfigure(1, weight=1)
        self.wrapped = []
        kind = event.get("kind", "info")
        color, tint = STYLES.get(kind, STYLES["info"])
        ctk.CTkLabel(self, text="", image=icon, width=32, height=32,
                     fg_color=tint, corner_radius=8).grid(row=0, column=0, padx=(12, 10), pady=10)
        # A fixed-height text area keeps long messages from enlarging the row.
        # The complete message remains available through the disclosure button.
        self.line = ctk.CTkFrame(self, height=28, width=1, fg_color="transparent")
        self.line.grid(row=0, column=1, sticky="ew")
        self.title_font = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.body_font = ctk.CTkFont(family="Segoe UI", size=13)
        self.title = ctk.CTkLabel(self.line, text="", height=28, font=self.title_font,
                                  text_color=color, anchor="w")
        self.title.place(x=0, y=0)
        self.body = ctk.CTkLabel(self.line, text="", height=28, font=self.body_font,
                                 text_color=TEXT, anchor="w")
        self.line.bind("<Configure>", self.reflow_line)
        ctk.CTkLabel(self, text=event.get("time", datetime.now().strftime("%H:%M:%S")),
                     font=("Segoe UI", 11), text_color=MUTED).grid(row=0, column=3, padx=(6, 12))
        if "stats" in event:
            self.add_stats(event["stats"])
        if event.get("body") or event.get("details"):
            self.chevron_down = make_icon("chevron_down", MUTED)
            self.chevron_up = make_icon("chevron_up", MUTED)
            self.details_button = ctk.CTkButton(self, text="", image=self.chevron_down, width=28, height=28,
                                               corner_radius=6, fg_color="transparent",
                                               hover_color="#343449", text_color=MUTED, command=self.toggle_details)
            self.details_button.grid(row=0, column=2, padx=(8, 0))
            detail_text = "\n".join(text for text in (event["title"], event.get("body"), event.get("details")) if text)
            self.details = ctk.CTkLabel(self, text=detail_text, font=("Segoe UI", 12),
                                        text_color=MUTED, anchor="w", justify="left", wraplength=380)
            self.wrapped.append((self.details, 68))
            self.details_visible = False
        self.bind("<Configure>", self.reflow)

    def add_stats(self, stats):
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.grid(row=2, column=0, columnspan=4, sticky="ew", padx=14, pady=(0, 14))
        for column in range(3):
            grid.grid_columnconfigure(column, weight=1, uniform="stats")
        for index, (label, value) in enumerate(stats):
            tile = ctk.CTkFrame(grid, fg_color="#1d1e2e", corner_radius=8)
            tile.grid(row=index // 3, column=index % 3, sticky="nsew", padx=3, pady=3)
            ctk.CTkLabel(tile, text=str(value), font=("Segoe UI", 22, "bold"), text_color=TEXT).pack(padx=8, pady=(8, 0))
            ctk.CTkLabel(tile, text=label, font=("Segoe UI", 11), text_color=MUTED).pack(padx=8, pady=(0, 9))

    def reflow(self, event):
        width = self._reverse_widget_scaling(event.width)
        for label, margin in self.wrapped:
            label.configure(wraplength=max(100, width - margin))

    @staticmethod
    def fit_text(text, font, width):
        text = " ".join(text.split())
        if font.measure(text) <= width:
            return text
        if width < font.measure("…"):
            return ""
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.measure(text[:middle] + "…") <= width:
                low = middle
            else:
                high = middle - 1
        return text[:low].rstrip() + "…"

    def reflow_line(self, event):
        width = max(0, self._reverse_widget_scaling(event.width) - 4)
        body = self.event.get("body", "")
        title_width = min(self.title_font.measure(self.event["title"]), width * .65 if body else width)
        self.title.configure(text=self.fit_text(self.event["title"], self.title_font, title_width), width=title_width)
        if body:
            body_width = max(0, width - title_width - 10)
            self.body.configure(text=self.fit_text("· " + body, self.body_font, body_width), width=body_width)
            self.body.place(x=title_width + 10, y=0)

    def toggle_details(self):
        self.details_visible = not self.details_visible
        if self.details_visible:
            self.details.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(0, 14), pady=(0, 12))
        else:
            self.details.grid_remove()
        self.details_button.configure(image=self.chevron_up if self.details_visible else self.chevron_down)


class ActivityFeed(ctk.CTkFrame):
    MAX_CARDS = 100

    def __init__(self, parent):
        super().__init__(parent, fg_color=PANEL, corner_radius=14, border_color="#36364f", border_width=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self.cards = []
        self.icons = {kind: make_icon(kind, color) for kind, (color, _) in STYLES.items()}
        ctk.CTkLabel(self, text="Activity", font=("Segoe UI", 19, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 12))
        ctk.CTkButton(self, text="Clear history", width=105, height=30, fg_color="#28283c",
                      hover_color="#36364f", command=self.clear).grid(row=0, column=1, padx=20, pady=(16, 12))
        self.current = ctk.CTkFrame(self, fg_color="#242e37", corner_radius=12)
        self.current.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16)
        self.current.grid_columnconfigure(1, weight=1)
        self.current_icon = ctk.CTkLabel(self.current, text="", image=self.icons["ready"], width=48, height=48,
                                        fg_color="#233c37", corner_radius=12)
        self.current_icon.grid(row=0, column=0, rowspan=3, padx=16, pady=18, sticky="n")
        ctk.CTkLabel(self.current, text="RIGHT NOW", font=("Segoe UI", 10, "bold"), text_color=MUTED,
                     anchor="w").grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(12, 0))
        self.current_title = ctk.CTkLabel(self.current, text="Ready to fish", font=("Segoe UI", 22, "bold"),
                                          anchor="w", justify="left", text_color=TEXT)
        self.current_title.grid(row=1, column=1, sticky="ew", padx=(0, 16))
        self.current_body = ctk.CTkLabel(self.current, text="Choose your game window and audio output, then start.",
                                         font=("Segoe UI", 13), anchor="w", justify="left", text_color="#c5c9d8", wraplength=380)
        self.current_body.grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=(2, 16))
        self.current.bind("<Configure>", self.reflow_current)
        ctk.CTkLabel(self, text="RECENT ACTIVITY  ·  NEWEST FIRST", font=("Segoe UI", 10, "bold"),
                     text_color=MUTED).grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=(17, 9))
        self.history = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.history.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 12))
        self.empty = ctk.CTkLabel(self.history, text="Your fishing activity will appear here.", font=("Segoe UI", 13), text_color=MUTED)
        self.empty.pack(pady=25)

    def reflow_current(self, event):
        width = max(100, self._reverse_widget_scaling(event.width) - 100)
        self.current_title.configure(wraplength=width)
        self.current_body.configure(wraplength=width)

    def set_current(self, title, body, kind="info"):
        self.current.configure(fg_color="#2e273e" if kind == "stop" else "#242e37")
        self.current_title.configure(text=title, text_color=STYLES["stop"][0] if kind == "stop" else TEXT)
        self.current_body.configure(text=body)
        self.current_icon.configure(image=self.icons.get(kind, self.icons["info"]),
                                    fg_color=STYLES.get(kind, STYLES["info"])[1])

    def add(self, event):
        event = dict(event)
        event.setdefault("time", datetime.now().strftime("%H:%M:%S"))
        kind = event.get("kind", "info")
        if event.get("current", True):
            self.set_current(event["title"], event.get("body", ""), kind)
        self.empty.pack_forget()
        card = ActivityCard(self.history, event, self.icons.get(kind, self.icons["info"]))
        options = {"before": self.cards[0]} if self.cards else {}
        card.pack(fill="x", padx=4, pady=(0, 8), **options)
        self.cards.insert(0, card)
        if len(self.cards) > self.MAX_CARDS:
            self.cards.pop().destroy()

    def summary(self, data):
        seconds = max(0, int(data["elapsed"]))
        duration = f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
        self.set_current("Session ended" if not data["failed"] else "Session stopped with an error",
                         data["reason"], "stop" if not data["failed"] else "error")
        self.add({"kind": "summary", "title": "Session summary", "body": data["reason"], "current": False,
                  "stats": [("Run time", duration), ("Casts", data["casts"]), ("Fish reeled in", data["bites"]),
                            ("Timed out", data["timeouts"]), ("Interrupted", data["interrupted"]), ("Lure uses", data["lures"])],
                  "details": "Fish reeled in counts detections followed by a reel-in key press, not confirmed catches.\n"
                             "Interrupted casts ended before a reel-in or timeout."})

    def clear(self):
        for card in self.cards:
            card.destroy()
        self.cards.clear()
        self.empty.pack(pady=25)
