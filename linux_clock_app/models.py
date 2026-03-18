"""Data models for linux-clock-app."""
from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class ClockConfig:
    # Window state — pos_x/pos_y < 0 means "auto position to bottom-right"
    pos_x: int = -1
    pos_y: int = -1
    always_on_top: bool = False

    # Format
    use_24h: bool = True
    show_seconds: bool = False
    show_date: bool = True
    show_lunar: bool = True

    # Appearance
    font_family: str = "Sans"
    font_size: int = 36
    text_color: str = "#FFFFFF"
    bg_color: str = "#000000"
    bg_opacity: float = 0.7

    # Border
    border_width: int = 0          # px, 0 = no border
    border_color: str = "#FFFFFF"  # hex #RRGGBB
    border_radius: int = 8         # px, corner rounding

    # Drag hotkey
    drag_shortcut: str = ""    # e.g. "Ctrl+Shift+m", empty = disabled

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for JSON serialisation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ClockConfig":
        """Build a ClockConfig from a dict, using defaults for missing keys."""
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)
