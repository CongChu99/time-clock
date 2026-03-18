# Drag-Toggle Global Hotkey Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable keyboard shortcut that toggles drag-to-reposition mode on/off for the floating clock window, set via the Settings dialog.

**Architecture:** A global hotkey is grabbed via `XGrabKey` on the X11 root window using a dedicated connection; a `GLib.io_add_watch` watcher fires `_toggle_drag_mode()` on KeyPress. Drag mode enables/disables X11 click-through by symmetrically calling `XShapeCombineRectangles`. The shortcut is captured in `SettingsDialog` via a GTK key controller.

**Tech Stack:** Python 3.10+, GTK4 (PyGObject), ctypes/libX11/libXext, pytest

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `linux_clock_app/models.py` | Modify | Add `drag_shortcut: str = ""` field |
| `linux_clock_app/clock_window.py` | Modify | X11 constants/structs, `_parse_shortcut`, `_x11_unset_click_through`, `_x11_open_grab`; ClockWindow state + toggle/register/teardown/event methods |
| `linux_clock_app/settings_dialog.py` | Modify | Shortcut capture row + `commit=False` on live-preview |
| `tests/test_drag_hotkey.py` | Create | Unit tests for `_parse_shortcut`, `_toggle_drag_mode`, `_on_x11_event`, `_on_drag_begin` guard, SettingsDialog capture |

---

## Chunk 1: Config field + `_parse_shortcut` TDD

### Task 1: Add `drag_shortcut` to ClockConfig

**Files:**
- Modify: `linux_clock_app/models.py`
- Test: `tests/test_drag_hotkey.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_drag_hotkey.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/congcp/Congcp/Project/time-down
python -m pytest tests/test_drag_hotkey.py::test_drag_shortcut_default_empty -v
```

Expected: `FAILED — AttributeError: 'ClockConfig' object has no attribute 'drag_shortcut'`

- [ ] **Step 3: Add `drag_shortcut` field to `ClockConfig`**

In `linux_clock_app/models.py`, after the `border_radius` field (line 29):

```python
    # Drag hotkey
    drag_shortcut: str = ""    # e.g. "Ctrl+Shift+m", empty = disabled
```

- [ ] **Step 4: Run all three config tests**

```bash
python -m pytest tests/test_drag_hotkey.py -k "drag_shortcut" -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add linux_clock_app/models.py tests/test_drag_hotkey.py
git commit -m "feat: add drag_shortcut field to ClockConfig"
```

---

### Task 2: `_parse_shortcut` — TDD

**Files:**
- Modify: `linux_clock_app/clock_window.py` (new module-level function + constants)
- Test: `tests/test_drag_hotkey.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_drag_hotkey.py`:

```python
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
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_drag_hotkey.py -k "parse_shortcut" -v
```

Expected: 7 FAILED — `ImportError: cannot import name '_parse_shortcut'`

- [ ] **Step 3: Fix stale `_get_x11_libs` docstring**

The existing `_get_x11_libs` function (around line 77) has a stale docstring that says `"Return (libX11, libXlib_display_ptr) or (None, None)"` but the body returns a **single** CDLL object or `None`. Update the docstring:

```python
def _get_x11_libs():
    """Return a ctypes CDLL for libX11.so.6, or None on failure."""
```

Run a quick sanity check:

```bash
python -c "from linux_clock_app.clock_window import _get_x11_libs; lib = _get_x11_libs(); print(type(lib))"
```

Expected: `<class 'ctypes.CDLL'>` (or `None` if libX11 is not installed)

- [ ] **Step 4: Add constants, structs, and `_parse_shortcut` to `clock_window.py`**

After the existing `_NET_WM_STATE_*` constants block (around line 61), add:

```python
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
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_drag_hotkey.py -k "parse_shortcut" -v
```

Expected: 7 PASSED

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
python -m pytest tests/ -v
```

Expected: all existing tests still PASS

- [ ] **Step 7: Commit**

```bash
git add linux_clock_app/clock_window.py tests/test_drag_hotkey.py
git commit -m "feat: add _parse_shortcut, X11 constants and structs for drag hotkey"
```

---

## Chunk 2: X11 helpers + ClockWindow toggle/register logic

> **Note:** `GrabModeAsync`, `KeyPress`, `LockMask`, `Mod2Mask`, `_XKeyEvent`, `_XEvent`, and `_MODIFIER_MAP` are all defined in Chunk 1 (Task 2, Step 4). Chunk 2 tasks depend on Chunk 1 being complete.

### Task 3: `_x11_unset_click_through`

**Files:**
- Modify: `linux_clock_app/clock_window.py`

- [ ] **Step 1: Add `_x11_unset_click_through` to `clock_window.py`**

Add after the existing `_x11_set_click_through` function (after line 152):

```python
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
            x_ret = y_ret = ctypes.c_int()
            w_ret = h_ret = border_ret = depth_ret = ctypes.c_uint()
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
```

- [ ] **Step 2: Smoke-test that the module still imports cleanly**

```bash
python -c "from linux_clock_app.clock_window import _x11_unset_click_through; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add linux_clock_app/clock_window.py
git commit -m "feat: add _x11_unset_click_through helper"
```

---

### Task 4: `_x11_open_grab`

**Files:**
- Modify: `linux_clock_app/clock_window.py`

- [ ] **Step 1: Add `_x11_open_grab` after `_x11_unset_click_through`**

```python
def _x11_open_grab(shortcut: str):
    """Open a dedicated X11 connection and grab *shortcut* on the root window.

    Grabs for all NumLock/CapsLock permutations so the hotkey fires regardless
    of lock state.

    Returns ``(conn, keycode, base_mods)`` on success, ``None`` on failure.
    The caller owns *conn* and must close it via ``_x11_close_grab``.
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
```

- [ ] **Step 2: Verify module imports cleanly**

```bash
python -c "from linux_clock_app.clock_window import _x11_open_grab; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add linux_clock_app/clock_window.py
git commit -m "feat: add _x11_open_grab helper (XGrabKey with lock-mask permutations)"
```

---

### Task 5: ClockWindow — state, `_setup_gestures`, `_toggle_drag_mode`

**Files:**
- Modify: `linux_clock_app/clock_window.py`
- Test: `tests/test_drag_hotkey.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_drag_hotkey.py`:

```python
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
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_drag_hotkey.py -k "toggle_drag or drag_begin" -v
```

Expected: 4 FAILED

- [ ] **Step 3: Add new state to `ClockWindow.__init__`**

In `clock_window.py`, inside `ClockWindow.__init__`, after `self._keep_above: bool = config.always_on_top` (around line 468), add:

```python
        # Drag-mode hotkey state
        self._drag_mode: bool = False
        self._x11_grab_conn = None
        self._x11_io_watch_id: int = 0
        self._grab_keycode: int = 0
        self._grab_mods: int = 0
        self._registered_shortcut: str = ""
```

Then call `_setup_gestures()` after `_setup_css()` and before `_apply_config()`:

```python
        self._setup_window()
        self._setup_labels()
        self._setup_css()
        self._setup_gestures()   # NEW — always register gesture controllers
        self._apply_config()
```

- [ ] **Step 4: Add `_toggle_drag_mode` method to `ClockWindow`**

Add after `_apply_keep_above` method:

```python
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
```

- [ ] **Step 5: Modify `_on_drag_begin` to add guard**

Replace the existing `_on_drag_begin` method body (starting at line 698) with:

```python
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
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_drag_hotkey.py -k "toggle_drag or drag_begin" -v
```

Expected: 4 PASSED

- [ ] **Step 7: Run full suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add linux_clock_app/clock_window.py tests/test_drag_hotkey.py
git commit -m "feat: add drag mode state, _toggle_drag_mode, _on_drag_begin guard"
```

---

### Task 6: `_register_drag_hotkey`, `_teardown_drag_hotkey`, `_on_x11_event`

**Files:**
- Modify: `linux_clock_app/clock_window.py`
- Test: `tests/test_drag_hotkey.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_drag_hotkey.py`:

```python
# ---------------------------------------------------------------------------
# Task 6 — _on_x11_event
# ---------------------------------------------------------------------------

from gi.repository import GLib


def _make_xevent_bytes(ev_type: int, keycode: int, state: int) -> bytes:
    """Pack a _XKeyEvent into a 192-byte _XEvent buffer using ctypes (alignment-safe).

    Uses ctypes directly rather than struct.pack to respect the LP64 padding
    between c_int (4 bytes) and c_ulong (8 bytes) fields.
    """
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
    from linux_clock_app.clock_window import ClockWindow, _XEvent, KeyPress
    import ctypes, struct

    win = _make_clock_window_mock()
    win._grab_keycode = 58
    win._grab_mods    = 0x0004  # ControlMask
    fake_conn = MagicMock()

    libx11 = MagicMock()
    # XPending returns 1 then 0
    libx11.XPending.side_effect = [1, 0]

    # Build a matching KeyPress event in the XEvent buffer
    ev_bytes = _make_xevent_bytes(KeyPress, keycode=58, state=0x0004)

    def fake_next_event(conn, buf_ptr):
        # Write event bytes into the ctypes buffer
        ctypes.memmove(buf_ptr, ev_bytes, 192)

    libx11.XNextEvent.side_effect = fake_next_event

    win._x11_grab_conn = fake_conn

    with (
        patch("linux_clock_app.clock_window._get_x11_libs", return_value=libx11),
        patch.object(ClockWindow, "_toggle_drag_mode") as mock_toggle,
    ):
        result = ClockWindow._on_x11_event(win, None, GLib.IO_IN)

    mock_toggle.assert_called_once()
    assert result == GLib.SOURCE_CONTINUE


def test_on_x11_event_non_matching_keycode_does_not_toggle():
    from linux_clock_app.clock_window import ClockWindow, KeyPress
    import ctypes

    win = _make_clock_window_mock()
    win._grab_keycode = 58
    win._grab_mods    = 0x0004
    fake_conn = MagicMock()
    win._x11_grab_conn = fake_conn

    ev_bytes = _make_xevent_bytes(KeyPress, keycode=99, state=0x0004)  # wrong keycode
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
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_drag_hotkey.py -k "x11_event" -v
```

Expected: 3 FAILED

- [ ] **Step 3: Add `_register_drag_hotkey` method**

Add after `_toggle_drag_mode` in `ClockWindow`:

```python
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
            return
        libx11.XConnectionNumber.restype = ctypes.c_int
        fd = libx11.XConnectionNumber(conn)
        self._x11_io_watch_id = GLib.io_add_watch(
            fd,
            GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP,
            self._on_x11_event,
        )
        logger.debug("Drag hotkey %r registered (fd=%d).", shortcut, fd)
```

- [ ] **Step 4: Add `_teardown_drag_hotkey` method**

Add after `_register_drag_hotkey`:

```python
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
```

- [ ] **Step 5: Add `_on_map_register_hotkey` and modify `_on_map`**

Add the one-shot wrapper method:

```python
    def _on_map_register_hotkey(self) -> bool:
        """One-shot GLib timeout callback to register the drag hotkey after map."""
        self._register_drag_hotkey()
        return False
```

Modify `_on_map`:

```python
    def _on_map(self, *_) -> None:
        """Called when the window is mapped — surface exists, safe for X11 calls."""
        GLib.timeout_add(150, self._restore_position)
        GLib.timeout_add(200, self._apply_x11_hints)    # sets click-through
        GLib.timeout_add(300, self._on_map_register_hotkey)  # after click-through
```

- [ ] **Step 6: Add `_on_x11_event` method**

```python
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
```

- [ ] **Step 7: Modify `update_from_config` to add `commit` parameter**

Replace the existing `update_from_config` method:

```python
    def update_from_config(self, config: ClockConfig, commit: bool = True) -> None:
        """Apply a new config (called by SettingsDialog after Task 5).

        *commit=False* skips hotkey re-registration (used during live preview).
        """
        self.config = config
        self._keep_above = config.always_on_top
        self._apply_config()
        self._controller.update_config(config)
        self._update_display()
        config_manager.save(config)
        GLib.idle_add(self._restore_position)

        if commit and config.drag_shortcut != self._registered_shortcut:
            self._teardown_drag_hotkey()
            self._register_drag_hotkey()
```

- [ ] **Step 8: Modify `_on_close` to call `_teardown_drag_hotkey`**

Replace the last two lines of `_on_close` (before `return False`):

```python
        self._teardown_drag_hotkey()  # unregister hotkey before stopping clock
        self._controller.stop()
        return False  # Allow the close to proceed
```

- [ ] **Step 9: Run new tests**

```bash
python -m pytest tests/test_drag_hotkey.py -k "x11_event" -v
```

Expected: 3 PASSED

- [ ] **Step 10: Run full suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 11: Commit**

```bash
git add linux_clock_app/clock_window.py tests/test_drag_hotkey.py
git commit -m "feat: add _register_drag_hotkey, _teardown_drag_hotkey, _on_x11_event to ClockWindow"
```

---

## Chunk 3: SettingsDialog shortcut capture row

### Task 7: Add shortcut capture row to SettingsDialog

**Files:**
- Modify: `linux_clock_app/settings_dialog.py`
- Test: `tests/test_drag_hotkey.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_drag_hotkey.py`:

```python
# ---------------------------------------------------------------------------
# Task 7 — SettingsDialog shortcut formatting helper
# ---------------------------------------------------------------------------

# We test _format_shortcut (a new standalone helper) independently of GTK widgets.

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
    from linux_clock_app.settings_dialog import _format_shortcut
    import gi
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk

    result = _format_shortcut(
        keyval=Gdk.KEY_d,
        mods=Gdk.ModifierType.SUPER_MASK,
    )
    assert result == "Super+d"
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_drag_hotkey.py -k "format_shortcut" -v
```

Expected: 3 FAILED — `ImportError: cannot import name '_format_shortcut'`

- [ ] **Step 3: Add `_format_shortcut` helper to `settings_dialog.py`**

After the existing `_parse_font_string` function (after line 81):

```python
def _format_shortcut(keyval: int, mods) -> str:
    """Convert a GTK keyval + modifier state to a canonical shortcut string.

    Always stores letters as lowercase X11 keysym names regardless of Shift.
    Modifier order: Ctrl, Alt, Shift, Super.
    """
    from gi.repository import Gdk  # local import to avoid circular at module level

    key_name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or ""
    parts: list[str] = []
    if mods & Gdk.ModifierType.CONTROL_MASK:  parts.append("Ctrl")
    if mods & Gdk.ModifierType.ALT_MASK:      parts.append("Alt")
    if mods & Gdk.ModifierType.SHIFT_MASK:    parts.append("Shift")
    if mods & Gdk.ModifierType.SUPER_MASK:    parts.append("Super")
    parts.append(key_name)
    return "+".join(parts)
```

- [ ] **Step 4: Run helper tests**

```bash
python -m pytest tests/test_drag_hotkey.py -k "format_shortcut" -v
```

Expected: 3 PASSED

- [ ] **Step 5: Add shortcut row widgets to `SettingsDialog.__init__`**

After the `show_date_row` block (after line 185, before the separator), add:

```python
        # --- Drag shortcut --------------------------------------------------
        shortcut_row = self._make_row("Drag shortcut:")
        self._shortcut_btn = Gtk.Button()
        self._shortcut_btn.set_label(cfg.drag_shortcut or "Not set")
        self._shortcut_btn.set_hexpand(True)
        self._shortcut_btn.connect("clicked", self._on_shortcut_btn_clicked)
        shortcut_row.append(self._shortcut_btn)
        content.append(shortcut_row)
```

Also add capture controller state variable near the top of `__init__` (after `self._original_config`):

```python
        self._capture_key_controller: Gtk.EventControllerKey | None = None
```

- [ ] **Step 6: Add capture mode methods to `SettingsDialog`**

Add after `_on_window_close`:

```python
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
        from gi.repository import Gdk

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
        _MODIFIER_KEYSYMS = {
            Gdk.KEY_Control_L, Gdk.KEY_Control_R,
            Gdk.KEY_Shift_L,   Gdk.KEY_Shift_R,
            Gdk.KEY_Alt_L,     Gdk.KEY_Alt_R,
            Gdk.KEY_Super_L,   Gdk.KEY_Super_R,
            Gdk.KEY_ISO_Level3_Shift,
        }
        if keyval in _MODIFIER_KEYSYMS:
            return True

        # Priority 4: require at least one modifier
        _REQUIRED = (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.ALT_MASK
            | Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.SUPER_MASK
        )
        if not (mods & _REQUIRED):
            return True

        shortcut = _format_shortcut(keyval, mods)
        if shortcut:
            self._accept_shortcut(shortcut)
        return True

    def _cancel_capture(self) -> None:
        """Cancel capture mode and restore the current shortcut label."""
        if self._capture_key_controller:
            self.remove_controller(self._capture_key_controller)
            self._capture_key_controller = None
        current = self._clock_window.config.drag_shortcut
        self._shortcut_btn.set_label(current or "Not set")

    def _accept_shortcut(self, shortcut: str) -> None:
        """Accept the captured shortcut and trigger live preview."""
        if self._capture_key_controller:
            self.remove_controller(self._capture_key_controller)
            self._capture_key_controller = None
        self._shortcut_btn.set_label(shortcut or "Not set")
        self._on_any_change()
```

- [ ] **Step 7: Update `_build_config` to include `drag_shortcut`**

Inside `_build_config`, add before the `return replace(...)` call:

```python
        # Drag shortcut
        raw_label = self._shortcut_btn.get_label()
        drag_shortcut = "" if raw_label == "Not set" else raw_label
```

Add `drag_shortcut=drag_shortcut` to the `replace(...)` keyword arguments.

Full updated `return` statement:

```python
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
```

- [ ] **Step 8: Update `_on_any_change` to pass `commit=False`**

Replace:

```python
    def _on_any_change(self, *_args) -> None:
        """Read all widget values, build a new ClockConfig, live-preview it."""
        new_config = self._build_config()
        self._clock_window.update_from_config(new_config)
```

With:

```python
    def _on_any_change(self, *_args) -> None:
        """Read all widget values, build a new ClockConfig, live-preview it."""
        new_config = self._build_config()
        self._clock_window.update_from_config(new_config, commit=False)
```

- [ ] **Step 9: Run format_shortcut tests**

```bash
python -m pytest tests/test_drag_hotkey.py -k "format_shortcut" -v
```

Expected: 3 PASSED

- [ ] **Step 10: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 11: Commit**

```bash
git add linux_clock_app/settings_dialog.py tests/test_drag_hotkey.py
git commit -m "feat: add drag shortcut capture row to SettingsDialog"
```

---

### Task 8: Final integration verification

**Files:** (no code changes — verification only)

- [ ] **Step 1: Run full test suite with coverage**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all PASS, no errors

- [ ] **Step 2: Verify the app imports cleanly**

```bash
python -c "
from linux_clock_app.models import ClockConfig
from linux_clock_app.clock_window import (
    _parse_shortcut, _x11_unset_click_through, _x11_open_grab,
    _XKeyEvent, _XEvent, GrabModeAsync, KeyPress, LockMask, Mod2Mask,
)
from linux_clock_app.settings_dialog import _format_shortcut
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify drag-toggle hotkey feature complete"
```

---

## Manual Smoke Test (after implementation)

1. Launch the app: `python -m linux_clock_app`
2. Right-click → Settings → scroll to "Drag shortcut"
3. Click the button → it shows "Press keys…"
4. Press `Ctrl+Shift+m` → button shows `Ctrl+Shift+m`, click OK
5. Press `Ctrl+Shift+m` globally → window becomes draggable (cursor changes)
6. Drag the window to a new position → release → position saved
7. Press `Ctrl+Shift+m` again → click-through restored, window not draggable
8. Open Settings → clear shortcut (Backspace in capture) → OK → hotkey no longer works
