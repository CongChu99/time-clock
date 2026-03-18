"""ClockWindow — main GTK4 window for the linux-clock-app.

Features:
- Undecorated floating window (no titlebar/frame)
- Displays time and date via Gtk.Label, driven by ClockController
- Drag-to-reposition via Gtk.GestureDrag (GTK4 way)
- Right-click context menu (always-on-top toggle, settings, about, quit)
- Always-on-top toggle via X11 _NET_WM_STATE_ABOVE (with Wayland warning)
- Loads/saves window position and state to ClockConfig
"""
from __future__ import annotations

import ctypes
import logging
import os
import signal
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gdk, Gio, GLib, Gtk

from linux_clock_app import config_manager
from linux_clock_app.clock_controller import ClockController
from linux_clock_app.models import ClockConfig

logger = logging.getLogger(__name__)

# Date label is displayed at half the main clock font size, minimum 12pt
_DATE_FONT_RATIO = 0.5
_DATE_FONT_MIN_PT = 12

import re as _re
_HEX_COLOR_RE = _re.compile(r'^#[0-9a-fA-F]{6}$')
_SAFE_FONT_RE = _re.compile(r'^[A-Za-z0-9 _\-]+$')


def _safe_css_font(family: str) -> str:
    """Return family if it contains only safe characters, else fallback to Sans."""
    return family if _SAFE_FONT_RE.match(family) else "Sans"


def _safe_css_color(color: str) -> str:
    """Return color if it is a valid #RRGGBB hex value, else fallback to white."""
    return color if _HEX_COLOR_RE.match(color) else "#FFFFFF"


def _safe_css_int(value: int, lo: int, hi: int) -> int:
    """Clamp *value* to [lo, hi] to prevent CSS injection via integer fields."""
    return max(lo, min(hi, int(value)))

# ---------------------------------------------------------------------------
# X11 helpers (only used when running under X11/XWayland)
# ---------------------------------------------------------------------------

_NET_WM_STATE_REMOVE = 0
_NET_WM_STATE_ADD = 1
_NET_WM_STATE_TOGGLE = 2

# ---------------------------------------------------------------------------
# Drag-hotkey X11 constants and structs
# ---------------------------------------------------------------------------

GrabModeAsync = 1        # X11 <X11/X.h>
KeyPress      = 2        # X11 event type
LockMask      = 0x0002   # CapsLock modifier mask
Mod2Mask      = 0x0010   # NumLock modifier mask

# Modifier name → X11 mask mapping (canonical order: Ctrl, Alt, Shift, Super)
_MODIFIER_MAP: dict[str, int] = {
    "ctrl":    0x0004,   # ControlMask
    "control": 0x0004,
    "alt":     0x0008,   # Mod1Mask
    "mod1":    0x0008,
    "shift":   0x0001,   # ShiftMask
    "super":   0x0040,   # Mod4Mask
    "mod4":    0x0040,
}


class _XKeyEvent(ctypes.Structure):
    """X11 XKeyEvent struct (64-bit LP64 Linux layout)."""

    _fields_ = [
        ("type",        ctypes.c_int),
        ("serial",      ctypes.c_ulong),
        ("send_event",  ctypes.c_int),
        ("display",     ctypes.c_void_p),
        ("window",      ctypes.c_ulong),
        ("root",        ctypes.c_ulong),
        ("subwindow",   ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("x",           ctypes.c_int),
        ("y",           ctypes.c_int),
        ("x_root",      ctypes.c_int),
        ("y_root",      ctypes.c_int),
        ("state",       ctypes.c_uint),
        ("keycode",     ctypes.c_uint),
        ("same_screen", ctypes.c_int),
    ]


# 192 bytes = 24 × sizeof(long) on 64-bit LP64 Linux (x86_64/aarch64).
# This is correct for 64-bit only; the app targets 64-bit Linux.
_XEvent = ctypes.c_ubyte * 192


def _parse_shortcut(display, shortcut: str) -> Optional[tuple[int, int]]:
    """Parse ``"Ctrl+Shift+m"`` → ``(keycode, modifier_mask)`` or ``None``.

    *display* is an already-open ctypes X11 Display* used only for
    ``XKeysymToKeycode``.  Returns ``None`` on any parse failure.
    """
    if not shortcut or not shortcut.strip():
        return None

    tokens = shortcut.split("+")
    if len(tokens) < 2:
        # No modifier — bare key shortcuts are out of scope
        return None

    mods = 0
    for token in tokens[:-1]:
        mask = _MODIFIER_MAP.get(token.lower())
        if mask is None:
            logger.warning("_parse_shortcut: unknown modifier %r in %r", token, shortcut)
            return None
        mods |= mask

    key_name = tokens[-1]
    libx11 = _get_x11_libs()
    if libx11 is None:
        return None

    libx11.XStringToKeysym.restype = ctypes.c_ulong
    keysym = libx11.XStringToKeysym(key_name.encode())
    if keysym == 0:
        logger.warning("_parse_shortcut: unknown key name %r in %r", key_name, shortcut)
        return None

    libx11.XKeysymToKeycode.restype = ctypes.c_uint
    keycode = libx11.XKeysymToKeycode(display, keysym)
    if keycode == 0:
        logger.warning("_parse_shortcut: no keycode for keysym %d in %r", keysym, shortcut)
        return None

    return int(keycode), mods


def _is_x11() -> bool:
    """Return True when the GDK backend is X11 (not pure Wayland)."""
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11  # noqa: F401

        display = Gdk.Display.get_default()
        return isinstance(display, GdkX11.X11Display)
    except Exception:
        return False


def _get_x11_libs():
    """Return a ctypes CDLL for libX11.so.6, or None on failure."""
    try:
        lib = ctypes.CDLL("libX11.so.6")
        return lib
    except OSError:
        return None


def _x11_screen_size() -> tuple[int, int] | None:
    """Return (screen_width, screen_height) in pixels via X11, or None."""
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        display = Gdk.Display.get_default()
        if not isinstance(display, GdkX11.X11Display):
            return None
        xdisplay = display.get_xdisplay()
        libx11 = _get_x11_libs()
        if libx11 is None:
            return None
        libx11.XDisplayWidth.restype = ctypes.c_int
        libx11.XDisplayHeight.restype = ctypes.c_int
        w = libx11.XDisplayWidth(xdisplay, 0)
        h = libx11.XDisplayHeight(xdisplay, 0)
        return int(w), int(h)
    except Exception as exc:
        logger.debug("_x11_screen_size failed: %s", exc)
        return None


def _x11_set_click_through(window: Gtk.Window) -> bool:
    """Make *window* click-through via an empty X11 ShapeInput region.

    All mouse/pointer events will pass through to whatever is below the window.
    Keyboard events are also ignored because the window can never receive focus.
    """
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        surface = window.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return False

        xid = surface.get_xid()
        libx11 = _get_x11_libs()
        if libx11 is None:
            return False

        try:
            libxext = ctypes.CDLL("libXext.so.6")
        except OSError:
            return False

        libx11.XOpenDisplay.restype = ctypes.c_void_p
        display_name = os.environ.get("DISPLAY", ":0").encode()
        xdpy = libx11.XOpenDisplay(display_name)
        if not xdpy:
            return False

        try:
            ShapeInput = 2
            ShapeSet = 0
            # Empty rectangle list → zero input area → all events pass through
            libxext.XShapeCombineRectangles(
                xdpy, xid, ShapeInput, 0, 0, None, 0, ShapeSet, 0
            )
            libx11.XFlush(xdpy)
        finally:
            libx11.XCloseDisplay(xdpy)
        return True
    except Exception as exc:
        logger.debug("_x11_set_click_through failed: %s", exc)
        return False


def _x11_unset_click_through(window: Gtk.Window) -> bool:
    """Restore full pointer/keyboard input by applying a full-window ShapeInput rect.

    Symmetric inverse of ``_x11_set_click_through``.  Uses ``XGetGeometry`` to
    obtain physical pixel dimensions (HiDPI-safe).
    """
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        surface = window.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return False

        xid = surface.get_xid()
        libx11 = _get_x11_libs()
        if libx11 is None:
            return False

        try:
            libxext = ctypes.CDLL("libXext.so.6")
        except OSError:
            return False

        libx11.XOpenDisplay.restype = ctypes.c_void_p
        display_name = os.environ.get("DISPLAY", ":0").encode()
        xdpy = libx11.XOpenDisplay(display_name)
        if not xdpy:
            return False

        try:
            # Get physical pixel size via XGetGeometry (avoids GTK HiDPI logical pixels)
            root_ret = ctypes.c_ulong()
            x_ret      = ctypes.c_int()
            y_ret      = ctypes.c_int()
            w_ret      = ctypes.c_uint()
            h_ret      = ctypes.c_uint()
            border_ret = ctypes.c_uint()
            depth_ret  = ctypes.c_uint()
            libx11.XGetGeometry(
                xdpy, xid,
                ctypes.byref(root_ret), ctypes.byref(x_ret), ctypes.byref(y_ret),
                ctypes.byref(w_ret), ctypes.byref(h_ret),
                ctypes.byref(border_ret), ctypes.byref(depth_ret),
            )
            width  = int(w_ret.value) or 200
            height = int(h_ret.value) or 80

            class XRectangle(ctypes.Structure):
                _fields_ = [
                    ("x",      ctypes.c_short),
                    ("y",      ctypes.c_short),
                    ("width",  ctypes.c_ushort),
                    ("height", ctypes.c_ushort),
                ]

            rect = XRectangle(0, 0, width, height)
            ShapeInput = 2
            ShapeSet   = 0
            libxext.XShapeCombineRectangles(
                xdpy, xid, ShapeInput, 0, 0, ctypes.byref(rect), 1, ShapeSet, 0
            )
            libx11.XFlush(xdpy)
        finally:
            libx11.XCloseDisplay(xdpy)
        return True
    except Exception as exc:
        logger.debug("_x11_unset_click_through failed: %s", exc)
        return False


def _x11_open_grab(shortcut: str):
    """Open a dedicated X11 connection and grab *shortcut* on the root window.

    Grabs for all NumLock/CapsLock permutations so the hotkey fires regardless
    of lock state.

    Returns ``(conn, keycode, base_mods)`` on success, ``None`` on failure.
    The caller owns *conn* and must close it via ``_teardown_drag_hotkey``.
    """
    try:
        libx11 = _get_x11_libs()
        if libx11 is None:
            return None

        libx11.XOpenDisplay.restype       = ctypes.c_void_p
        libx11.XDefaultRootWindow.restype = ctypes.c_ulong
        libx11.XConnectionNumber.restype  = ctypes.c_int

        display_name = os.environ.get("DISPLAY", ":0").encode()
        conn = libx11.XOpenDisplay(display_name)
        if not conn:
            return None

        success = False
        try:
            root = libx11.XDefaultRootWindow(conn)
            result = _parse_shortcut(conn, shortcut)
            if result is None:
                return None   # finally closes conn (success=False)
            keycode, base_mods = result
            # Grab for all NumLock / CapsLock permutations
            for extra in (0, LockMask, Mod2Mask, LockMask | Mod2Mask):
                libx11.XGrabKey(
                    conn, keycode, base_mods | extra, root,
                    False,          # owner_events
                    GrabModeAsync,  # pointer_mode  = 1
                    GrabModeAsync,  # keyboard_mode = 1
                )
            libx11.XFlush(conn)
            success = True
            return conn, keycode, base_mods
        except Exception as exc:
            logger.debug("_x11_open_grab inner: %s", exc)
            return None
        finally:
            if not success:
                libx11.XCloseDisplay(conn)
    except Exception as exc:
        logger.debug("_x11_open_grab failed: %s", exc)
        return None


def _x11_set_wm_hints(window: Gtk.Window) -> bool:
    """Set _NET_WM_STATE: above + skip_taskbar + skip_pager."""
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        surface = window.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return False

        xid = surface.get_xid()
        libx11 = _get_x11_libs()
        if libx11 is None:
            return False

        libx11.XOpenDisplay.restype = ctypes.c_void_p
        display_name = os.environ.get("DISPLAY", ":0").encode()
        xdpy = libx11.XOpenDisplay(display_name)
        if not xdpy:
            return False

        try:
            libx11.XDefaultRootWindow.restype = ctypes.c_ulong
            libx11.XInternAtom.restype = ctypes.c_ulong
            root_win = libx11.XDefaultRootWindow(xdpy)

            wm_state      = libx11.XInternAtom(xdpy, b"_NET_WM_STATE", False)
            atom_above    = libx11.XInternAtom(xdpy, b"_NET_WM_STATE_ABOVE", False)
            atom_skip_tb  = libx11.XInternAtom(xdpy, b"_NET_WM_STATE_SKIP_TASKBAR", False)
            atom_skip_pg  = libx11.XInternAtom(xdpy, b"_NET_WM_STATE_SKIP_PAGER", False)

            class XClientMessageEvent(ctypes.Structure):
                _fields_ = [
                    ("type", ctypes.c_int),
                    ("serial", ctypes.c_ulong),
                    ("send_event", ctypes.c_int),
                    ("display", ctypes.c_void_p),
                    ("window", ctypes.c_ulong),
                    ("message_type", ctypes.c_ulong),
                    ("format", ctypes.c_int),
                    ("data", ctypes.c_long * 5),
                ]

            mask = (1 << 19) | (1 << 20)
            _NET_WM_STATE_ADD = 1

            for atom in (atom_above, atom_skip_tb, atom_skip_pg):
                ev = XClientMessageEvent()
                ev.type = 33
                ev.send_event = True
                ev.display = xdpy
                ev.window = xid
                ev.message_type = wm_state
                ev.format = 32
                ev.data[0] = _NET_WM_STATE_ADD
                ev.data[1] = atom
                ev.data[2] = 0
                ev.data[3] = 1
                ev.data[4] = 0
                libx11.XSendEvent(xdpy, root_win, False, mask, ctypes.byref(ev))

            libx11.XFlush(xdpy)
        finally:
            libx11.XCloseDisplay(xdpy)
        return True
    except Exception as exc:
        logger.debug("_x11_set_wm_hints failed: %s", exc)
        return False


def _x11_move_window(window: Gtk.Window, x: int, y: int) -> bool:
    """Move *window* to (*x*, *y*) via _NET_MOVERESIZE_WINDOW.

    Opens a dedicated X11 connection (GDK's get_xdisplay() is not directly
    usable as a ctypes Display* pointer on all GI binding versions).
    Returns True on success.
    """
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        surface = window.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return False

        xid = surface.get_xid()
        libx11 = _get_x11_libs()
        if libx11 is None:
            return False

        # Open a fresh connection; avoids GDK pointer incompatibility with ctypes
        libx11.XOpenDisplay.restype = ctypes.c_void_p
        display_name = os.environ.get("DISPLAY", ":0").encode()
        xdpy = libx11.XOpenDisplay(display_name)
        if not xdpy:
            return False

        try:
            libx11.XDefaultRootWindow.restype = ctypes.c_ulong
            libx11.XInternAtom.restype = ctypes.c_ulong
            root_win = libx11.XDefaultRootWindow(xdpy)
            moveresize_atom = libx11.XInternAtom(
                xdpy, b"_NET_MOVERESIZE_WINDOW", False
            )

            class XClientMessageEvent(ctypes.Structure):
                _fields_ = [
                    ("type", ctypes.c_int),
                    ("serial", ctypes.c_ulong),
                    ("send_event", ctypes.c_int),
                    ("display", ctypes.c_void_p),
                    ("window", ctypes.c_ulong),
                    ("message_type", ctypes.c_ulong),
                    ("format", ctypes.c_int),
                    ("data", ctypes.c_long * 5),
                ]

            event = XClientMessageEvent()
            event.type = 33  # ClientMessage
            event.serial = 0
            event.send_event = True
            event.display = xdpy
            event.window = xid
            event.message_type = moveresize_atom
            event.format = 32
            # NorthWest gravity (1) | x present (bit 8) | y present (bit 9)
            event.data[0] = 1 | (1 << 8) | (1 << 9)
            event.data[1] = x
            event.data[2] = y
            event.data[3] = 0
            event.data[4] = 0

            SubstructureNotifyMask = 1 << 19
            SubstructureRedirectMask = 1 << 20
            mask = SubstructureNotifyMask | SubstructureRedirectMask
            libx11.XSendEvent(xdpy, root_win, False, mask, ctypes.byref(event))
            libx11.XFlush(xdpy)
        finally:
            libx11.XCloseDisplay(xdpy)
        return True
    except Exception as exc:
        logger.debug("_x11_move_window failed: %s", exc)
        return False


def _x11_get_window_position(window: Gtk.Window) -> Optional[tuple[int, int]]:
    """Return the current (*x*, *y*) position of *window* on screen via X11.

    Returns None if X11 is not available or on error.
    """
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        surface = window.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return None
        display = Gdk.Display.get_default()
        if not isinstance(display, GdkX11.X11Display):
            return None

        xdisplay = display.get_xdisplay()
        xid = surface.get_xid()

        libx11 = _get_x11_libs()
        if libx11 is None:
            return None

        # XGetGeometry returns (status, root, x, y, width, height, border, depth)
        root = ctypes.c_ulong()
        x = ctypes.c_int()
        y = ctypes.c_int()
        width = ctypes.c_uint()
        height = ctypes.c_uint()
        border = ctypes.c_uint()
        depth = ctypes.c_uint()

        libx11.XGetGeometry(
            xdisplay,
            xid,
            ctypes.byref(root),
            ctypes.byref(x),
            ctypes.byref(y),
            ctypes.byref(width),
            ctypes.byref(height),
            ctypes.byref(border),
            ctypes.byref(depth),
        )

        # XGetGeometry gives position relative to parent; translate to root
        child = ctypes.c_ulong()
        dest_x = ctypes.c_int()
        dest_y = ctypes.c_int()
        libx11.XDefaultRootWindow.restype = ctypes.c_ulong
        root_win = libx11.XDefaultRootWindow(xdisplay)
        libx11.XTranslateCoordinates(
            xdisplay,
            xid,
            root_win,
            0,
            0,
            ctypes.byref(dest_x),
            ctypes.byref(dest_y),
            ctypes.byref(child),
        )
        return int(dest_x.value), int(dest_y.value)
    except Exception as exc:
        logger.debug("_x11_get_window_position failed: %s", exc)
        return None


def _x11_set_keep_above(window: Gtk.Window, keep_above: bool) -> bool:
    """Toggle _NET_WM_STATE_ABOVE on *window* via an X11 client message.

    Returns True on success.
    """
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        surface = window.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return False
        display = Gdk.Display.get_default()
        if not isinstance(display, GdkX11.X11Display):
            return False

        xdisplay = display.get_xdisplay()
        xid = surface.get_xid()
        libx11 = _get_x11_libs()
        if libx11 is None:
            return False

        libx11.XDefaultRootWindow.restype = ctypes.c_ulong
        root_win = libx11.XDefaultRootWindow(xdisplay)

        # Intern the atoms we need
        libx11.XInternAtom.restype = ctypes.c_ulong
        wm_state = libx11.XInternAtom(xdisplay, b"_NET_WM_STATE", False)
        wm_state_above = libx11.XInternAtom(
            xdisplay, b"_NET_WM_STATE_ABOVE", False
        )

        # Build the ClientMessage event
        class XClientMessageEvent(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_int),
                ("serial", ctypes.c_ulong),
                ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong),
                ("message_type", ctypes.c_ulong),
                ("format", ctypes.c_int),
                ("data", ctypes.c_long * 5),
            ]

        action = _NET_WM_STATE_ADD if keep_above else _NET_WM_STATE_REMOVE
        event = XClientMessageEvent()
        X_CLIENT_MESSAGE = 33
        event.type = X_CLIENT_MESSAGE
        event.serial = 0
        event.send_event = True
        event.display = xdisplay
        event.window = xid
        event.message_type = wm_state
        event.format = 32
        event.data[0] = action
        event.data[1] = wm_state_above
        event.data[2] = 0
        event.data[3] = 1  # source: normal application
        event.data[4] = 0

        SubstructureNotifyMask = 1 << 19
        SubstructureRedirectMask = 1 << 20
        mask = SubstructureNotifyMask | SubstructureRedirectMask

        libx11.XSendEvent(
            xdisplay,
            root_win,
            False,
            mask,
            ctypes.byref(event),
        )
        libx11.XFlush(xdisplay)
        return True
    except Exception as exc:
        logger.debug("_x11_set_keep_above failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# ClockWindow
# ---------------------------------------------------------------------------


class ClockWindow(Gtk.Window):
    """Main floating clock window."""

    # Track whether we have shown the Wayland keep-above warning once
    _wayland_warning_shown: bool = False

    def __init__(self, app: Gtk.Application, config: ClockConfig) -> None:
        super().__init__(application=app)
        self.config = config
        self._controller = ClockController(on_tick=self._update_display)

        # Drag state
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0
        self._drag_win_x: int = config.pos_x
        self._drag_win_y: int = config.pos_y

        # Keep-above state
        self._keep_above: bool = config.always_on_top

        # Drag-mode hotkey state
        self._drag_mode: bool = False
        self._x11_grab_conn = None
        self._x11_io_watch_id: int = 0
        self._grab_keycode: int = 0
        self._grab_mods: int = 0
        self._registered_shortcut: str = ""

        self._setup_window()
        self._setup_labels()
        self._setup_css()
        self._setup_gestures()   # NEW — always register gesture controllers
        self._apply_config()

        # Connect close handler
        self.connect("close-request", self._on_close)

        # Position + click-through AFTER window is mapped (surface exists then)
        self.connect("map", self._on_map)

        # Reload config on SIGUSR1 (sent by `linux-clock-app set ...`)
        GLib.unix_signal_add(
            GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._on_sigusr1
        )

        # Start the clock
        self._controller.start(config)

        # Do an immediate display update so the labels show correct time
        self._update_display()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        """Configure the window as undecorated and floating."""
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_title("Linux Clock")

    def _setup_labels(self) -> None:
        """Create the time and date labels inside a vertical Gtk.Box."""
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._box.set_margin_top(12)
        self._box.set_margin_bottom(12)
        self._box.set_margin_start(16)
        self._box.set_margin_end(16)

        self._time_label = Gtk.Label(label="--:--")
        self._time_label.set_halign(Gtk.Align.CENTER)
        self._time_label.add_css_class("clock-time")

        self._date_label = Gtk.Label(label="")
        self._date_label.set_halign(Gtk.Align.CENTER)
        self._date_label.add_css_class("clock-date")

        self._lunar_label = Gtk.Label(label="")
        self._lunar_label.set_halign(Gtk.Align.CENTER)
        self._lunar_label.add_css_class("clock-lunar")

        self._box.append(self._time_label)
        self._box.append(self._date_label)
        self._box.append(self._lunar_label)
        self.set_child(self._box)

    def _setup_gestures(self) -> None:
        """Attach GestureDrag (move) and GestureClick button=3 (menu)."""
        # Left-button drag for repositioning
        self._drag = Gtk.GestureDrag()
        self._drag.set_button(1)
        self._drag.connect("drag-begin", self._on_drag_begin)
        self._drag.connect("drag-update", self._on_drag_update)
        self._drag.connect("drag-end", self._on_drag_end)
        self.add_controller(self._drag)

        # Right-click for context menu
        self._right_click = Gtk.GestureClick()
        self._right_click.set_button(3)
        self._right_click.connect("pressed", self._on_right_click)
        self.add_controller(self._right_click)

    def _setup_css(self) -> None:
        """Create a CSS provider (populated later by _apply_config)."""
        self._css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _apply_config(self) -> None:
        """Apply font, color, opacity, position and always-on-top from config."""
        cfg = self.config
        # Parse bg_color to RGBA for the CSS rgba() value
        bg_rgba = self._hex_to_rgb(cfg.bg_color)
        r, g, b = bg_rgba

        safe_family = _safe_css_font(cfg.font_family)
        safe_text_color = _safe_css_color(cfg.text_color)
        safe_opacity = max(0.0, min(1.0, float(cfg.bg_opacity)))
        date_font_size = max(cfg.font_size * _DATE_FONT_RATIO, _DATE_FONT_MIN_PT)
        lunar_font_size = date_font_size

        safe_radius = _safe_css_int(cfg.border_radius, 0, 64)
        safe_bwidth = _safe_css_int(cfg.border_width, 0, 20)
        safe_bcolor = _safe_css_color(cfg.border_color)

        border_css = (
            f"border: {safe_bwidth}px solid {safe_bcolor};"
            if safe_bwidth > 0
            else "border: none;"
        )

        css = f"""
window {{
    background-color: rgba({r}, {g}, {b}, {safe_opacity});
    border-radius: {safe_radius}px;
    {border_css}
}}
.clock-time {{
    font-family: {safe_family};
    font-size: {cfg.font_size}pt;
    color: {safe_text_color};
}}
.clock-date {{
    font-family: {safe_family};
    font-size: {date_font_size}pt;
    color: {safe_text_color};
    opacity: 0.85;
}}
.clock-lunar {{
    font-family: {safe_family};
    font-size: {lunar_font_size}pt;
    color: {safe_text_color};
    opacity: 0.75;
}}
"""
        self._css_provider.load_from_string(css)

        # Update label visibility
        self._date_label.set_visible(cfg.show_date)
        self._lunar_label.set_visible(cfg.show_lunar)

        # Apply always-on-top (only after window is mapped)
        if cfg.always_on_top:
            GLib.idle_add(self._apply_keep_above, cfg.always_on_top)

    # ------------------------------------------------------------------
    # Position helpers
    # ------------------------------------------------------------------

    def _on_map(self, *_) -> None:
        """Called when the window is mapped — surface exists, safe for X11 calls."""
        GLib.timeout_add(150, self._restore_position)
        GLib.timeout_add(200, self._apply_x11_hints)    # sets click-through
        GLib.timeout_add(300, self._on_map_register_hotkey)  # after click-through

    def _apply_x11_hints(self) -> bool:
        """Apply click-through and WM state hints after the WM has processed the window."""
        _x11_set_click_through(self)
        _x11_set_wm_hints(self)
        return False  # run once

    def _restore_position(self) -> bool:
        """Move the window to the saved position (called via idle_add).

        When pos_x or pos_y is negative, auto-position to the bottom-right
        corner with a 16 px margin.
        """
        x, y = self.config.pos_x, self.config.pos_y
        if x < 0 or y < 0:
            # Find the rightmost monitor edge for bottom-right positioning
            monitors = Gdk.Display.get_default().get_monitors()
            n = monitors.get_n_items()
            sw, sh = 1920, 1080
            if n > 0:
                # Use the monitor with the largest x offset (rightmost)
                best = monitors.get_item(0)
                best_g = best.get_geometry()
                for i in range(1, n):
                    m = monitors.get_item(i)
                    g = m.get_geometry()
                    if g.x > best_g.x:
                        best = m
                        best_g = g
                sw = best_g.x + best_g.width
                sh = best_g.height
            margin = 16
            _, nat = self._box.get_preferred_size()
            win_w = nat.width + 32   # add box left+right margins
            win_h = nat.height + 24  # add box top+bottom margins
            x = max(0, sw - win_w - margin)
            y = max(0, sh - win_h - margin)
            self.config.pos_x = x
            self.config.pos_y = y
            config_manager.save(self.config)
            logger.debug("Auto-positioned to bottom-right (%d, %d).", x, y)
        _x11_move_window(self, x, y)
        return False  # Run only once

    def _apply_keep_above(self, keep: bool) -> bool:
        """Apply keep-above state (called via idle_add after realise)."""
        _x11_set_keep_above(self, keep)
        return False

    def _toggle_drag_mode(self) -> None:
        """Toggle drag-to-reposition mode on/off."""
        if self._drag_mode:
            _x11_set_click_through(self)
            self._drag_mode = False
            logger.debug("Drag mode OFF.")
        else:
            _x11_unset_click_through(self)
            self._drag_mode = True
            logger.debug("Drag mode ON.")

    def _register_drag_hotkey(self) -> None:
        """Register the global hotkey from config.drag_shortcut, if set."""
        shortcut = self.config.drag_shortcut
        if not shortcut:
            return
        result = _x11_open_grab(shortcut)
        if result is None:
            logger.warning("Could not grab hotkey %r — drag toggle unavailable.", shortcut)
            return
        conn, kc, mods = result
        self._x11_grab_conn       = conn
        self._grab_keycode        = kc
        self._grab_mods           = mods
        self._registered_shortcut = shortcut

        libx11 = _get_x11_libs()
        if libx11 is None:
            logger.warning("_register_drag_hotkey: libx11 unavailable after grab.")
            return
        libx11.XConnectionNumber.restype = ctypes.c_int
        fd = libx11.XConnectionNumber(conn)
        self._x11_io_watch_id = GLib.io_add_watch(
            fd,
            GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP,
            self._on_x11_event,
        )
        logger.debug("Drag hotkey %r registered (fd=%d).", shortcut, fd)

    def _teardown_drag_hotkey(self) -> None:
        """Unregister the global hotkey and close the X11 grab connection."""
        if self._x11_io_watch_id:
            GLib.source_remove(self._x11_io_watch_id)   # detach FIRST
            self._x11_io_watch_id = 0

        if self._x11_grab_conn is None:
            return

        conn = self._x11_grab_conn
        self._x11_grab_conn = None

        libx11 = _get_x11_libs()
        if libx11:
            ev = _XEvent()
            while libx11.XPending(conn) > 0:
                libx11.XNextEvent(conn, ctypes.byref(ev))
            libx11.XDefaultRootWindow.restype = ctypes.c_ulong
            root = libx11.XDefaultRootWindow(conn)
            for extra in (0, LockMask, Mod2Mask, LockMask | Mod2Mask):
                libx11.XUngrabKey(conn, self._grab_keycode, self._grab_mods | extra, root)
            libx11.XFlush(conn)
            libx11.XCloseDisplay(conn)

        self._grab_keycode        = 0
        self._grab_mods           = 0
        self._registered_shortcut = ""

        # If drag mode was ON, restore click-through so window is not stuck
        if self._drag_mode:
            _x11_set_click_through(self)
            self._drag_mode = False

        logger.debug("Drag hotkey torn down.")

    def _on_map_register_hotkey(self) -> bool:
        """One-shot GLib timeout callback to register the drag hotkey after map."""
        self._register_drag_hotkey()
        return False

    def _on_x11_event(self, fd, condition) -> bool:
        """GLib IO callback — dispatch KeyPress events from the grab connection."""
        libx11 = _get_x11_libs()

        if condition & (GLib.IO_ERR | GLib.IO_HUP):
            logger.warning("X11 grab connection lost — drag hotkey disabled.")
            self._x11_io_watch_id = 0   # being removed by SOURCE_REMOVE
            conn = self._x11_grab_conn
            self._x11_grab_conn = None
            if conn and libx11:
                ev = _XEvent()
                while libx11.XPending(conn) > 0:
                    libx11.XNextEvent(conn, ctypes.byref(ev))
                libx11.XDefaultRootWindow.restype = ctypes.c_ulong
                root = libx11.XDefaultRootWindow(conn)
                for extra in (0, LockMask, Mod2Mask, LockMask | Mod2Mask):
                    libx11.XUngrabKey(conn, self._grab_keycode, self._grab_mods | extra, root)
                libx11.XCloseDisplay(conn)
            self._grab_keycode        = 0
            self._grab_mods           = 0
            self._registered_shortcut = ""
            return GLib.SOURCE_REMOVE

        conn = self._x11_grab_conn
        if conn is None or libx11 is None:
            return GLib.SOURCE_REMOVE

        ev_buf = _XEvent()
        while libx11.XPending(conn) > 0:
            libx11.XNextEvent(conn, ctypes.byref(ev_buf))
            ev = ctypes.cast(
                ctypes.byref(ev_buf), ctypes.POINTER(_XKeyEvent)
            ).contents
            if ev.type != KeyPress:
                continue
            pressed_mods = ev.state & ~(LockMask | Mod2Mask)
            if ev.keycode == self._grab_keycode and pressed_mods == self._grab_mods:
                self._toggle_drag_mode()

        return GLib.SOURCE_CONTINUE

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Parse ``#RRGGBB`` to ``(r, g, b)`` integers 0-255."""
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except (ValueError, IndexError):
            return 0, 0, 0

    def _on_sigusr1(self) -> bool:
        """Reload config file when SIGUSR1 is received (from `linux-clock-app set`)."""
        new_config = config_manager.load()
        self.update_from_config(new_config)
        logger.debug("Config reloaded via SIGUSR1.")
        return GLib.SOURCE_CONTINUE  # keep the signal handler registered

    # ------------------------------------------------------------------
    # Clock tick
    # ------------------------------------------------------------------

    def _update_display(self) -> None:
        """Callback invoked by ClockController on every tick."""
        self._time_label.set_text(self._controller.get_formatted_time(self.config))
        self._date_label.set_text(self._controller.get_formatted_date(self.config))
        self._lunar_label.set_text(self._controller.get_formatted_lunar(self.config))

    # ------------------------------------------------------------------
    # Drag handlers
    # ------------------------------------------------------------------

    def _on_drag_begin(
        self, gesture: Gtk.GestureDrag, start_x: float, start_y: float
    ) -> None:
        """Record window position at drag start. Deny gesture if not in drag mode."""
        if not self._drag_mode:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        pos = _x11_get_window_position(self)
        if pos is not None:
            self._drag_win_x, self._drag_win_y = pos
        else:
            self._drag_win_x = self.config.pos_x
            self._drag_win_y = self.config.pos_y

    def _on_drag_update(
        self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float
    ) -> None:
        """Move the window by the current drag offset."""
        new_x = int(self._drag_win_x + offset_x)
        new_y = int(self._drag_win_y + offset_y)
        _x11_move_window(self, new_x, new_y)

    def _on_drag_end(
        self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float
    ) -> None:
        """Save the final window position to config."""
        new_x = int(self._drag_win_x + offset_x)
        new_y = int(self._drag_win_y + offset_y)
        self.config.pos_x = new_x
        self.config.pos_y = new_y
        config_manager.save(self.config)
        logger.debug("Window moved to (%d, %d) — config saved.", new_x, new_y)

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------

    def _on_right_click(
        self,
        gesture: Gtk.GestureClick,
        n_press: int,
        x: float,
        y: float,
    ) -> None:
        """Show a context menu at the click position."""
        menu_model = Gio.Menu()

        # Settings
        settings_item = Gio.MenuItem.new("Settings", "win.open-settings")
        menu_model.append_item(settings_item)

        # Always on top (show current state)
        aot_label = (
            "Always on top: ON" if self._keep_above else "Always on top: OFF"
        )
        aot_item = Gio.MenuItem.new(aot_label, "win.toggle-always-on-top")
        menu_model.append_item(aot_item)

        # About
        about_item = Gio.MenuItem.new("About", "win.show-about")
        menu_model.append_item(about_item)

        # Separator section for Quit
        quit_section = Gio.Menu()
        quit_section.append("Quit", "win.quit-app")
        menu_model.append_section(None, quit_section)

        # Wire up actions on this window
        self._register_menu_actions()

        popover = Gtk.PopoverMenu.new_from_model(menu_model)
        popover.set_parent(self)

        # Position the popover at the click coordinates
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.set_has_arrow(False)
        popover.popup()

    def _register_menu_actions(self) -> None:
        """Register Gio.SimpleAction instances on this window for the menu."""
        def _add(name: str, callback):
            # Avoid duplicating actions on repeated right-clicks
            existing = self.lookup_action(name)
            if existing is not None:
                return
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        _add("open-settings", lambda a, p: self.open_settings())
        _add("toggle-always-on-top", lambda a, p: self._toggle_always_on_top())
        _add("show-about", lambda a, p: self._show_about())
        _add(
            "quit-app",
            lambda a, p: self.get_application().quit(),
        )

    # ------------------------------------------------------------------
    # Menu action handlers
    # ------------------------------------------------------------------

    def _toggle_always_on_top(self) -> None:
        """Toggle the always-on-top window state."""
        self._keep_above = not self._keep_above

        if _is_x11():
            success = _x11_set_keep_above(self, self._keep_above)
            if not success:
                logger.warning("Failed to set always-on-top via X11.")
        else:
            # Running under Wayland — show a one-time tooltip/dialog warning
            if not ClockWindow._wayland_warning_shown:
                ClockWindow._wayland_warning_shown = True
                self._show_wayland_warning()

        # Persist state
        self.config.always_on_top = self._keep_above
        config_manager.save(self.config)
        logger.debug("Always-on-top set to %s.", self._keep_above)

    def _show_wayland_warning(self) -> None:
        """Show a one-time info dialog warning about Wayland always-on-top."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Always on top",
        )
        dialog.format_secondary_text(
            "The always-on-top feature is not supported under Wayland.\n"
            "This setting will be applied the next time the app is launched "
            "under an X11 session."
        )
        dialog.connect("response", lambda d, _: d.destroy())
        dialog.present()

    def _show_about(self) -> None:
        """Display a simple About dialog."""
        about = Gtk.AboutDialog()
        about.set_transient_for(self)
        about.set_modal(True)
        about.set_program_name("Linux Clock App")
        about.set_version("0.1.0")
        about.set_comments("A lightweight floating desktop clock for Linux.")
        about.set_license_type(Gtk.License.MIT_X11)
        about.set_website("https://github.com/user/linux-clock-app")
        about.set_website_label("GitHub")
        about.connect("response", lambda d, _: d.destroy())
        about.present()

    def open_settings(self) -> None:
        """Open the SettingsDialog for live-preview customisation."""
        from linux_clock_app.settings_dialog import SettingsDialog

        dialog = SettingsDialog(clock_window=self)
        dialog.present()

    # ------------------------------------------------------------------
    # Close handler
    # ------------------------------------------------------------------

    def _on_close(self, *_args) -> bool:
        """Save window position and stop the clock before closing."""
        # Read current position from X11
        pos = _x11_get_window_position(self)
        if pos is not None:
            self.config.pos_x, self.config.pos_y = pos

        self.config.always_on_top = self._keep_above
        config_manager.save(self.config)
        logger.debug(
            "Window closed — position (%d, %d) saved.",
            self.config.pos_x,
            self.config.pos_y,
        )

        self._teardown_drag_hotkey()  # unregister hotkey before stopping clock
        self._controller.stop()
        return False  # Allow the close to proceed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_from_config(self, config: ClockConfig, commit: bool = True) -> None:
        """Apply a new config (called by SettingsDialog).

        *commit=False* skips hotkey re-registration (used during live preview).
        """
        self.config = config
        self._keep_above = config.always_on_top
        self._apply_config()
        self._controller.update_config(config)
        self._update_display()
        if commit:
            config_manager.save(config)
        GLib.idle_add(self._restore_position)

        if commit and config.drag_shortcut != self._registered_shortcut:
            self._teardown_drag_hotkey()
            self._register_drag_hotkey()
