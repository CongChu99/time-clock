"""SettingsDialog — font/color/opacity/format settings with live preview.

Opens a Gtk.Window dialog that lets the user customise the clock's appearance
and format.  Every widget change immediately calls
``clock_window.update_from_config()`` so the main clock window acts as a
live preview.

OK / Apply  → keep the new config (already saved by update_from_config)
Cancel      → restore the original config and close
"""
from __future__ import annotations

import copy
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk

if TYPE_CHECKING:
    from linux_clock_app.clock_window import ClockWindow

from linux_clock_app.models import ClockConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> Gdk.RGBA:
    """Convert a ``#RRGGBB`` string to a :class:`Gdk.RGBA`."""
    rgba = Gdk.RGBA()
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
    except (ValueError, IndexError):
        r = g = b = 0.0
    rgba.red = r
    rgba.green = g
    rgba.blue = b
    rgba.alpha = alpha
    return rgba


def _rgba_to_hex(rgba: Gdk.RGBA) -> str:
    """Convert a :class:`Gdk.RGBA` to ``#RRGGBB`` (alpha is ignored)."""
    r = max(0, min(255, int(round(rgba.red * 255))))
    g = max(0, min(255, int(round(rgba.green * 255))))
    b = max(0, min(255, int(round(rgba.blue * 255))))
    return f"#{r:02X}{g:02X}{b:02X}"


def _parse_font_string(font_str: str) -> tuple[str, int]:
    """Extract ``(family, size)`` from a Pango font description string.

    Examples
    --------
    "Sans 36"          → ("Sans", 36)
    "DejaVu Sans 14"   → ("DejaVu Sans", 14)
    "Monospace Bold 12"→ ("Monospace Bold", 12)
    """
    parts = font_str.rsplit(" ", 1)
    if len(parts) == 2:
        try:
            size = int(parts[1])
            return parts[0], size
        except ValueError:
            pass
    return font_str, 12


_SHORTCUT_UNSET_LABEL = "Not set"

_MODIFIER_KEYSYMS: frozenset[int] = frozenset({
    Gdk.KEY_Control_L, Gdk.KEY_Control_R,
    Gdk.KEY_Shift_L,   Gdk.KEY_Shift_R,
    Gdk.KEY_Alt_L,     Gdk.KEY_Alt_R,
    Gdk.KEY_Super_L,   Gdk.KEY_Super_R,
    Gdk.KEY_ISO_Level3_Shift,
})

_SHORTCUT_REQUIRED_MODS = (
    Gdk.ModifierType.CONTROL_MASK
    | Gdk.ModifierType.ALT_MASK
    | Gdk.ModifierType.SHIFT_MASK
    | Gdk.ModifierType.SUPER_MASK
)


def _format_shortcut(keyval: int, mods) -> str:
    """Convert a GTK keyval + modifier state to a canonical shortcut string.

    Always stores letters as lowercase X11 keysym names regardless of Shift.
    Modifier order: Ctrl, Alt, Shift, Super.
    """
    key_name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or ""
    parts: list[str] = []
    if mods & Gdk.ModifierType.CONTROL_MASK:  parts.append("Ctrl")
    if mods & Gdk.ModifierType.ALT_MASK:      parts.append("Alt")
    if mods & Gdk.ModifierType.SHIFT_MASK:    parts.append("Shift")
    if mods & Gdk.ModifierType.SUPER_MASK:    parts.append("Super")
    parts.append(key_name)
    return "+".join(parts)


# ---------------------------------------------------------------------------
# SettingsDialog
# ---------------------------------------------------------------------------


class SettingsDialog(Gtk.Window):
    """Settings dialog with live preview wired to *clock_window*."""

    def __init__(self, clock_window: "ClockWindow") -> None:
        super().__init__()

        self._clock_window = clock_window
        # Keep a pristine copy so Cancel can restore the original state.
        self._original_config: ClockConfig = copy.copy(clock_window.config)
        self._capture_key_controller: Gtk.EventControllerKey | None = None

        # ---- Window chrome --------------------------------------------------
        self.set_title("Clock Settings")
        self.set_modal(True)
        self.set_transient_for(clock_window)
        self.set_resizable(False)
        self.set_default_size(400, -1)

        # ---- Build UI -------------------------------------------------------
        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(outer_box)

        # Content area
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(16)
        content.set_margin_bottom(8)
        content.set_margin_start(16)
        content.set_margin_end(16)
        outer_box.append(content)

        cfg = clock_window.config

        # --- Font -----------------------------------------------------------
        font_row = self._make_row("Font:")
        self._font_btn = Gtk.FontButton()
        self._font_btn.set_font(f"{cfg.font_family} {cfg.font_size}")
        self._font_btn.set_hexpand(True)
        font_row.append(self._font_btn)
        content.append(font_row)

        # --- Text colour ----------------------------------------------------
        text_color_row = self._make_row("Text colour:")
        self._text_color_btn = Gtk.ColorButton()
        self._text_color_btn.set_rgba(_hex_to_rgba(cfg.text_color))
        self._text_color_btn.set_hexpand(True)
        text_color_row.append(self._text_color_btn)
        content.append(text_color_row)

        # --- Background colour ----------------------------------------------
        bg_color_row = self._make_row("Background colour:")
        self._bg_color_btn = Gtk.ColorButton()
        self._bg_color_btn.set_rgba(_hex_to_rgba(cfg.bg_color))
        self._bg_color_btn.set_hexpand(True)
        bg_color_row.append(self._bg_color_btn)
        content.append(bg_color_row)

        # --- Opacity --------------------------------------------------------
        opacity_row = self._make_row("Opacity:")
        opacity_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        opacity_box.set_hexpand(True)

        self._opacity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01
        )
        self._opacity_scale.set_value(cfg.bg_opacity)
        self._opacity_scale.set_draw_value(False)
        self._opacity_scale.set_hexpand(True)

        self._opacity_label = Gtk.Label(label=f"{int(cfg.bg_opacity * 100)}%")
        self._opacity_label.set_width_chars(5)
        self._opacity_label.set_xalign(1.0)

        opacity_box.append(self._opacity_scale)
        opacity_box.append(self._opacity_label)
        opacity_row.append(opacity_box)
        content.append(opacity_row)

        # --- 24 h toggle ----------------------------------------------------
        use24h_row = self._make_row("24-hour clock:")
        self._use24h_switch = Gtk.Switch()
        self._use24h_switch.set_active(cfg.use_24h)
        self._use24h_switch.set_halign(Gtk.Align.START)
        use24h_row.append(self._use24h_switch)
        content.append(use24h_row)

        # --- Show seconds ---------------------------------------------------
        show_secs_row = self._make_row("Show seconds:")
        self._show_seconds_check = Gtk.CheckButton()
        self._show_seconds_check.set_active(cfg.show_seconds)
        show_secs_row.append(self._show_seconds_check)
        content.append(show_secs_row)

        # --- Show date ------------------------------------------------------
        show_date_row = self._make_row("Show date:")
        self._show_date_check = Gtk.CheckButton()
        self._show_date_check.set_active(cfg.show_date)
        show_date_row.append(self._show_date_check)
        content.append(show_date_row)

        # --- Drag shortcut --------------------------------------------------
        shortcut_row = self._make_row("Drag shortcut:")
        self._shortcut_btn = Gtk.Button()
        self._shortcut_btn.set_label(cfg.drag_shortcut or _SHORTCUT_UNSET_LABEL)
        self._shortcut_btn.set_hexpand(True)
        self._shortcut_btn.connect("clicked", self._on_shortcut_btn_clicked)
        shortcut_row.append(self._shortcut_btn)
        content.append(shortcut_row)

        # ---- Separator + button bar ----------------------------------------
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        outer_box.append(sep)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_bar.set_margin_top(8)
        btn_bar.set_margin_bottom(12)
        btn_bar.set_margin_start(16)
        btn_bar.set_margin_end(16)
        btn_bar.set_halign(Gtk.Align.END)
        outer_box.append(btn_bar)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self._on_cancel)
        btn_bar.append(cancel_btn)

        ok_btn = Gtk.Button(label="OK")
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", self._on_ok)
        btn_bar.append(ok_btn)

        # ---- Connect live-preview signals ----------------------------------
        self._font_btn.connect("font-set", self._on_any_change)
        self._text_color_btn.connect("color-set", self._on_any_change)
        self._bg_color_btn.connect("color-set", self._on_any_change)
        self._opacity_scale.connect("value-changed", self._on_opacity_changed)
        self._use24h_switch.connect("notify::active", self._on_any_change)
        self._show_seconds_check.connect("toggled", self._on_any_change)
        self._show_date_check.connect("toggled", self._on_any_change)

        # Handle window close button (X) as Cancel
        self.connect("close-request", self._on_window_close)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_row(label_text: str) -> Gtk.Box:
        """Return a horizontal box with a right-aligned label on the left."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lbl = Gtk.Label(label=label_text)
        lbl.set_width_chars(20)
        lbl.set_xalign(1.0)
        row.append(lbl)
        return row

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_opacity_changed(self, scale: Gtk.Scale) -> None:
        """Update the percentage label, then trigger live preview."""
        value = scale.get_value()
        self._opacity_label.set_label(f"{int(value * 100)}%")
        self._on_any_change()

    def _on_any_change(self, *_args) -> None:
        """Read all widget values, build a new ClockConfig, live-preview it."""
        new_config = self._build_config()
        self._clock_window.update_from_config(new_config, commit=False)

    def _on_ok(self, *_args) -> None:
        """Finalise the new config (already saved) and close."""
        # update_from_config already called save() during live preview;
        # call once more to be safe with the final widget state.
        new_config = self._build_config()
        self._clock_window.update_from_config(new_config)
        logger.debug("SettingsDialog: OK — config saved.")
        self.destroy()

    def _on_cancel(self, *_args) -> None:
        """Restore the original config and close."""
        self._clock_window.update_from_config(self._original_config)
        logger.debug("SettingsDialog: Cancel — original config restored.")
        self.destroy()

    def _on_window_close(self, *_args) -> bool:
        """Treat the window-manager close button as Cancel."""
        self._on_cancel()
        return True  # Prevent default close; destroy() handles it

    def _on_shortcut_btn_clicked(self, *_) -> None:
        """Enter shortcut-capture mode."""
        self._shortcut_btn.set_label("Press keys…")
        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-pressed", self._on_capture_key)
        self.add_controller(ctrl)
        self._capture_key_controller = ctrl

    def _on_capture_key(
        self,
        ctrl: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state,
    ) -> bool:
        """Handle key events during shortcut-capture mode."""
        # Strip NumLock and CapsLock from the effective modifier state
        mods = state & ~(Gdk.ModifierType.LOCK_MASK | Gdk.ModifierType.MOD2_MASK)

        # Priority 1: Escape → cancel capture
        if keyval == Gdk.KEY_Escape:
            self._cancel_capture()
            return True

        # Priority 2: Backspace with no modifiers → clear shortcut
        if keyval == Gdk.KEY_BackSpace and not mods:
            self._accept_shortcut("")
            return True

        # Priority 3: bare modifier key alone → wait for the actual key
        if keyval in _MODIFIER_KEYSYMS:
            return True

        # Priority 4: require at least one modifier
        if not (mods & _SHORTCUT_REQUIRED_MODS):
            return True

        shortcut = _format_shortcut(keyval, mods)
        if shortcut:
            self._accept_shortcut(shortcut)
        # Unknown keyval → stay in capture mode, await another key
        return True

    def _cancel_capture(self) -> None:
        """Cancel capture mode and restore the current shortcut label."""
        if self._capture_key_controller:
            self.remove_controller(self._capture_key_controller)
            self._capture_key_controller = None
        current = self._clock_window.config.drag_shortcut
        self._shortcut_btn.set_label(current or _SHORTCUT_UNSET_LABEL)

    def _accept_shortcut(self, shortcut: str) -> None:
        """Accept the captured shortcut and trigger live preview."""
        if self._capture_key_controller:
            self.remove_controller(self._capture_key_controller)
            self._capture_key_controller = None
        self._shortcut_btn.set_label(shortcut or _SHORTCUT_UNSET_LABEL)
        self._on_any_change()

    # ------------------------------------------------------------------
    # Config builder
    # ------------------------------------------------------------------

    def _build_config(self) -> ClockConfig:
        """Read all widget values and return a new :class:`ClockConfig`."""
        # Font
        font_str = self._font_btn.get_font()
        font_family, font_size = _parse_font_string(font_str)

        # Colours
        text_rgba = self._text_color_btn.get_rgba()
        bg_rgba = self._bg_color_btn.get_rgba()
        text_color = _rgba_to_hex(text_rgba)
        bg_color = _rgba_to_hex(bg_rgba)

        # Opacity
        bg_opacity = self._opacity_scale.get_value()

        # Format toggles
        use_24h = self._use24h_switch.get_active()
        show_seconds = self._show_seconds_check.get_active()
        show_date = self._show_date_check.get_active()

        # Drag shortcut
        raw_label = self._shortcut_btn.get_label()
        drag_shortcut = "" if raw_label == _SHORTCUT_UNSET_LABEL else raw_label

        # Build a new config, preserving fields we do not touch (pos, aot…)
        return replace(
            self._clock_window.config,
            font_family=font_family,
            font_size=font_size,
            text_color=text_color,
            bg_color=bg_color,
            bg_opacity=bg_opacity,
            use_24h=use_24h,
            show_seconds=show_seconds,
            show_date=show_date,
            drag_shortcut=drag_shortcut,
        )
