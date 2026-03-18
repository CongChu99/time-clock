"""Tests for drag-toggle hotkey feature."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from linux_clock_app.models import ClockConfig


# ---------------------------------------------------------------------------
# Task 1 — ClockConfig.drag_shortcut
# ---------------------------------------------------------------------------

def test_drag_shortcut_default_empty():
    cfg = ClockConfig()
    assert cfg.drag_shortcut == ""


def test_drag_shortcut_round_trips_via_dict():
    cfg = ClockConfig(drag_shortcut="Ctrl+Shift+m")
    d = cfg.to_dict()
    cfg2 = ClockConfig.from_dict(d)
    assert cfg2.drag_shortcut == "Ctrl+Shift+m"


def test_drag_shortcut_from_dict_missing_key_uses_default():
    """Dicts without 'drag_shortcut' (old saved configs) fall back to ''."""
    cfg = ClockConfig.from_dict({})
    assert cfg.drag_shortcut == ""


# ---------------------------------------------------------------------------
# Task 2 — _parse_shortcut
# ---------------------------------------------------------------------------

# We import the function under test after mocking ctypes/X11 so tests run
# without a real display. The function reads libx11 from _get_x11_libs().

def _make_mock_libx11(keysym: int = 99, keycode: int = 50):
    """Return a mock libx11 where XStringToKeysym → keysym, XKeysymToKeycode → keycode."""
    lib = MagicMock()
    lib.XStringToKeysym.return_value = keysym
    lib.XKeysymToKeycode.return_value = keycode
    return lib


def test_parse_shortcut_ctrl_m():
    from linux_clock_app.clock_window import _parse_shortcut
    lib = _make_mock_libx11(keysym=109, keycode=58)   # 'm'
    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=lib):
        result = _parse_shortcut(MagicMock(), "Ctrl+m")
    assert result == (58, 0x0004)   # ControlMask


def test_parse_shortcut_ctrl_shift_m():
    from linux_clock_app.clock_window import _parse_shortcut
    lib = _make_mock_libx11(keysym=109, keycode=58)
    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=lib):
        result = _parse_shortcut(MagicMock(), "Ctrl+Shift+m")
    assert result == (58, 0x0004 | 0x0001)  # ControlMask | ShiftMask


def test_parse_shortcut_super_f1():
    from linux_clock_app.clock_window import _parse_shortcut
    lib = _make_mock_libx11(keysym=0xFFBE, keycode=67)
    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=lib):
        result = _parse_shortcut(MagicMock(), "Super+F1")
    assert result == (67, 0x0040)   # Mod4Mask


def test_parse_shortcut_unknown_key_returns_none():
    from linux_clock_app.clock_window import _parse_shortcut
    lib = _make_mock_libx11(keysym=0, keycode=0)   # XStringToKeysym returns NoSymbol
    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=lib):
        result = _parse_shortcut(MagicMock(), "Ctrl+NOSUCHKEY")
    assert result is None


def test_parse_shortcut_no_modifier_returns_none():
    from linux_clock_app.clock_window import _parse_shortcut
    lib = _make_mock_libx11()
    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=lib):
        result = _parse_shortcut(MagicMock(), "m")
    assert result is None


def test_parse_shortcut_empty_returns_none():
    from linux_clock_app.clock_window import _parse_shortcut
    lib = _make_mock_libx11()
    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=lib):
        result = _parse_shortcut(MagicMock(), "")
    assert result is None


def test_parse_shortcut_unknown_modifier_returns_none():
    from linux_clock_app.clock_window import _parse_shortcut
    lib = _make_mock_libx11()
    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=lib):
        result = _parse_shortcut(MagicMock(), "Windows+m")
    assert result is None


# ---------------------------------------------------------------------------
# Task 5 — _toggle_drag_mode + _on_drag_begin guard
# ---------------------------------------------------------------------------

def _make_clock_window_mock():
    """Return a MagicMock that mimics the relevant ClockWindow interface."""
    win = MagicMock()
    win._drag_mode = False
    win._x11_grab_conn = None
    win._x11_io_watch_id = 0
    win._grab_keycode = 0
    win._grab_mods = 0
    win._registered_shortcut = ""
    return win


def test_toggle_drag_mode_on():
    """First call sets _drag_mode=True and calls _x11_unset_click_through."""
    from linux_clock_app.clock_window import ClockWindow
    win = _make_clock_window_mock()
    with (
        patch("linux_clock_app.clock_window._x11_set_click_through") as mock_ct_on,
        patch("linux_clock_app.clock_window._x11_unset_click_through") as mock_ct_off,
    ):
        ClockWindow._toggle_drag_mode(win)
    mock_ct_off.assert_called_once_with(win)
    mock_ct_on.assert_not_called()
    assert win._drag_mode is True


def test_toggle_drag_mode_off():
    """Second call sets _drag_mode=False and calls _x11_set_click_through."""
    from linux_clock_app.clock_window import ClockWindow
    win = _make_clock_window_mock()
    win._drag_mode = True
    with (
        patch("linux_clock_app.clock_window._x11_set_click_through") as mock_ct_on,
        patch("linux_clock_app.clock_window._x11_unset_click_through") as mock_ct_off,
    ):
        ClockWindow._toggle_drag_mode(win)
    mock_ct_on.assert_called_once_with(win)
    mock_ct_off.assert_not_called()
    assert win._drag_mode is False


def test_on_drag_begin_denied_when_not_in_drag_mode():
    """_on_drag_begin must deny the gesture sequence when _drag_mode is False."""
    from linux_clock_app.clock_window import ClockWindow
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    win = _make_clock_window_mock()
    win._drag_mode = False
    gesture = MagicMock(spec=Gtk.GestureDrag)
    ClockWindow._on_drag_begin(win, gesture, 0.0, 0.0)
    gesture.set_state.assert_called_once_with(Gtk.EventSequenceState.DENIED)


def test_on_drag_begin_proceeds_when_in_drag_mode():
    """_on_drag_begin must NOT deny the gesture when _drag_mode is True."""
    from linux_clock_app.clock_window import ClockWindow
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    win = _make_clock_window_mock()
    win._drag_mode = True
    win.config = MagicMock()
    win.config.pos_x = 100
    win.config.pos_y = 200
    gesture = MagicMock(spec=Gtk.GestureDrag)
    with patch("linux_clock_app.clock_window._x11_get_window_position", return_value=None):
        ClockWindow._on_drag_begin(win, gesture, 0.0, 0.0)
    # DENIED must NOT be called
    for c in gesture.set_state.call_args_list:
        assert c.args[0] != Gtk.EventSequenceState.DENIED


# ---------------------------------------------------------------------------
# Task 6 — _on_x11_event
# ---------------------------------------------------------------------------

from gi.repository import GLib


def _make_xevent_bytes(ev_type: int, keycode: int, state: int) -> bytes:
    """Pack a _XKeyEvent into a 192-byte _XEvent buffer using ctypes (alignment-safe)."""
    import ctypes
    from linux_clock_app.clock_window import _XEvent, _XKeyEvent
    ev = _XKeyEvent()
    ev.type    = ev_type
    ev.keycode = keycode
    ev.state   = state
    buf = _XEvent()
    ctypes.memmove(buf, ctypes.byref(ev), ctypes.sizeof(_XKeyEvent))
    return bytes(buf)


def test_on_x11_event_matching_keypress_calls_toggle():
    from linux_clock_app.clock_window import ClockWindow, KeyPress
    import ctypes

    win = _make_clock_window_mock()
    win._grab_keycode = 58
    win._grab_mods    = 0x0004  # ControlMask
    fake_conn = MagicMock()

    libx11 = MagicMock()
    libx11.XPending.side_effect = [1, 0]

    ev_bytes = _make_xevent_bytes(KeyPress, keycode=58, state=0x0004)

    def fake_next_event(conn, buf_ptr):
        ctypes.memmove(buf_ptr, ev_bytes, 192)

    libx11.XNextEvent.side_effect = fake_next_event
    win._x11_grab_conn = fake_conn

    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=libx11):
        result = ClockWindow._on_x11_event(win, None, GLib.IO_IN)

    win._toggle_drag_mode.assert_called_once()
    assert result == GLib.SOURCE_CONTINUE


def test_on_x11_event_non_matching_keycode_does_not_toggle():
    from linux_clock_app.clock_window import ClockWindow, KeyPress
    import ctypes

    win = _make_clock_window_mock()
    win._grab_keycode = 58
    win._grab_mods    = 0x0004
    fake_conn = MagicMock()
    win._x11_grab_conn = fake_conn

    ev_bytes = _make_xevent_bytes(KeyPress, keycode=99, state=0x0004)
    libx11 = MagicMock()
    libx11.XPending.side_effect = [1, 0]

    def fake_next_event(conn, buf_ptr):
        ctypes.memmove(buf_ptr, ev_bytes, 192)

    libx11.XNextEvent.side_effect = fake_next_event

    with (
        patch("linux_clock_app.clock_window._get_x11_libs", return_value=libx11),
        patch.object(ClockWindow, "_toggle_drag_mode") as mock_toggle,
    ):
        result = ClockWindow._on_x11_event(win, None, GLib.IO_IN)

    mock_toggle.assert_not_called()
    assert result == GLib.SOURCE_CONTINUE


def test_on_x11_event_io_err_returns_source_remove():
    from linux_clock_app.clock_window import ClockWindow

    win = _make_clock_window_mock()
    win._x11_grab_conn = MagicMock()
    win._grab_keycode  = 58
    win._grab_mods     = 0x0004

    libx11 = MagicMock()
    libx11.XPending.return_value = 0
    libx11.XDefaultRootWindow.return_value = 1

    with patch("linux_clock_app.clock_window._get_x11_libs", return_value=libx11):
        result = ClockWindow._on_x11_event(win, None, GLib.IO_ERR)

    assert result == GLib.SOURCE_REMOVE
    assert win._x11_grab_conn is None
    assert win._grab_keycode == 0
    assert win._registered_shortcut == ""


# ---------------------------------------------------------------------------
# Task 7 — SettingsDialog shortcut formatting helper
# ---------------------------------------------------------------------------

def test_format_shortcut_ctrl_shift_m():
    """Ctrl+Shift pressed with 'm' key → stored as 'Ctrl+Shift+m'."""
    from linux_clock_app.settings_dialog import _format_shortcut
    import gi
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk

    result = _format_shortcut(
        keyval=Gdk.KEY_M,   # uppercase M (from Shift held)
        mods=Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK,
    )
    assert result == "Ctrl+Shift+m"


def test_format_shortcut_ctrl_alt_f1():
    """Ctrl+Alt pressed with F1 → stored as 'Ctrl+Alt+F1'."""
    from linux_clock_app.settings_dialog import _format_shortcut
    import gi
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk

    result = _format_shortcut(
        keyval=Gdk.KEY_F1,
        mods=Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK,
    )
    assert result == "Ctrl+Alt+F1"


def test_format_shortcut_super_d():
    """Super pressed with 'd' → stored as 'Super+d'."""
    from linux_clock_app.settings_dialog import _format_shortcut
    import gi
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk

    result = _format_shortcut(
        keyval=Gdk.KEY_d,
        mods=Gdk.ModifierType.SUPER_MASK,
    )
    assert result == "Super+d"
