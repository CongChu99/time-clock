# Design: Drag-Toggle Global Hotkey

**Date:** 2026-03-17
**Feature:** Keyboard shortcut to toggle drag-to-reposition mode on/off

---

## Overview

Add a configurable keyboard shortcut that toggles drag-to-reposition mode for the floating clock window. First press enables drag mode (user can move the window); second press disables it and restores click-through.

---

## Context

The clock window runs in X11 click-through mode (`XShapeCombineRectangles` with zero rectangles on `ShapeInput`), meaning all pointer and keyboard events pass through to windows below. Because of this, a **global hotkey** captured at the root window level via `XGrabKey` is required — the clock window itself cannot receive input events in its default state.

`_setup_gestures()` is currently defined but never called. This feature calls it unconditionally in `__init__`.

---

## Constants (new, to be defined at module level)

```python
GrabModeAsync   = 1      # X11 <X11/X.h>
ShapeInput      = 2      # already used
ShapeSet        = 0      # already used
KeyPress        = 2      # X11 event type
LockMask        = 0x0002 # CapsLock — stripped from modifiers
Mod2Mask        = 0x0010 # NumLock  — stripped from modifiers
```

Modifier mask table (canonical order for storage: Ctrl, Alt, Shift, Super):

| Token | Constant | Value |
|---|---|---|
| `Ctrl` / `Control` | `ControlMask` | `0x0004` |
| `Alt` / `Mod1` | `Mod1Mask` | `0x0008` |
| `Shift` | `ShiftMask` | `0x0001` |
| `Super` / `Mod4` | `Mod4Mask` | `0x0040` |

---

## Components

### 1. `ClockConfig` (`models.py`)

Add one new field:

```python
drag_shortcut: str = ""   # e.g. "Ctrl+Shift+m", empty = disabled
```

Serialises/deserialises automatically via existing `to_dict` / `from_dict`.

---

### 2. `ClockWindow` (`clock_window.py`)

#### New instance state

```python
self._drag_mode: bool = False
self._x11_grab_conn = None              # ctypes void* — dedicated X11 connection for XGrabKey
self._x11_io_watch_id: int = 0          # GLib.io_add_watch handle; 0 = not registered
self._grab_keycode: int = 0             # currently grabbed keycode
self._grab_mods: int = 0                # currently grabbed modifier mask
self._registered_shortcut: str = ""     # shortcut string currently grabbed (used for change detection)
```

#### `__init__` change

Call `_setup_gestures()` unconditionally (before `_apply_config()`), so the right-click menu and drag gesture controllers are always registered regardless of X11 availability. The `_on_drag_begin` guard prevents accidental moves when drag mode is off.

#### New X11 helpers (module-level functions)

All helpers follow the existing pattern in `clock_window.py`: open a dedicated `XOpenDisplay` connection, operate in a `try/finally` block, close with `XCloseDisplay` in the `finally` clause.

---

**`_parse_shortcut(display, shortcut) -> tuple[int, int] | None`**

Accepts a ctypes `display` pointer (already opened by the caller) and a shortcut string such as `"Ctrl+Shift+m"`.

- Empty string or whitespace-only → return `None`.
- Split on `+`. Result must have ≥ 2 tokens (at least one modifier + one key); bare single token with no modifier → return `None` (non-modifier shortcuts are out of scope).
- All tokens except the last → modifier names. Build `mods` integer using the constant table above. Unknown modifier token → return `None`, log warning.
- Last token → key name passed to `XStringToKeysym(name.encode())`. Returns `NoSymbol (0)` on failure → return `None`, log warning.
- Convert keysym to keycode via `XKeysymToKeycode(display, keysym)`. Returns `0` on failure → return `None`.
- Return `(keycode, mods)`.

**Key name convention:** always the lowercase X11 keysym name for letters (e.g. `"m"` not `"M"`). The SettingsDialog enforces this when formatting the stored string (see Section 3).

---

**`_x11_unset_click_through(window: Gtk.Window) -> bool`**

Follows the **exact same structure** as `_x11_set_click_through`: requires `GdkX11`, gets `surface = window.get_surface()`, checks `isinstance(surface, GdkX11.X11Surface)`, gets `xid = surface.get_xid()`, opens a dedicated `XOpenDisplay`, operates in a `try/finally` block, closes with `XCloseDisplay`.

Restores full input region using the X11 window geometry (not GTK logical pixels, to avoid HiDPI mismatch). Use `XGetGeometry` to get the physical pixel dimensions, then apply a rectangle of that size:

```python
# Get physical pixel size via X11 (consistent with other helpers)
root_ret   = ctypes.c_ulong()
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
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]
rect = XRectangle(0, 0, width, height)
libxext.XShapeCombineRectangles(
    xdpy, xid, ShapeInput, 0, 0, ctypes.byref(rect), 1, ShapeSet, 0
)
libx11.XFlush(xdpy)
```

This is the exact symmetric inverse of `_x11_set_click_through`.

---

**`_x11_open_grab(shortcut: str) -> tuple[ctypes.c_void_p, int, int] | None`**

Opens a dedicated X11 connection, grabs the key for all lock-modifier permutations, and returns `(conn, keycode, base_mods)` for later use. Returns `None` on any failure; uses an explicit `success` flag to ensure `XCloseDisplay` is always called on the failure path.

Because `XGrabKey` only fires for the exact modifier mask, the grab is registered four times to handle any combination of NumLock (`Mod2Mask`) and CapsLock (`LockMask`) that may be active at press time:

```python
libx11.XOpenDisplay.restype        = ctypes.c_void_p
libx11.XDefaultRootWindow.restype  = ctypes.c_ulong
libx11.XConnectionNumber.restype   = ctypes.c_int
display_name = os.environ.get("DISPLAY", ":0").encode()
conn = libx11.XOpenDisplay(display_name)
if not conn:
    return None
success = False
try:
    root   = libx11.XDefaultRootWindow(conn)
    result = _parse_shortcut(conn, shortcut)
    if result is None:
        return None   # success=False → finally closes conn
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
    logger.debug("_x11_open_grab failed: %s", exc)
    return None
finally:
    if not success:
        libx11.XCloseDisplay(conn)
```

---

**`XKeyEvent` ctypes structure** (defined at module level, used in `_on_x11_event`):

```python
class _XKeyEvent(ctypes.Structure):
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
        ("state",       ctypes.c_uint),   # modifier mask
        ("keycode",     ctypes.c_uint),   # hardware keycode
        ("same_screen", ctypes.c_int),
    ]

# XEvent generic union — 192 bytes = 24 × sizeof(long) on 64-bit LP64 Linux.
# This is correct for 64-bit x86_64/aarch64 but would be 96 bytes on 32-bit.
# The app targets 64-bit Linux only; this assumption is intentional.
_XEvent = ctypes.c_ubyte * 192
```

In `_on_x11_event`, cast the raw buffer to `_XKeyEvent` after checking `type`.

---

#### New methods on `ClockWindow`

**`_register_drag_hotkey()`** *(plain method, no return value)*

Called directly from `_on_map` timeout wrapper and from `update_from_config`. Registers the hotkey if `config.drag_shortcut` is set:

```python
def _register_drag_hotkey(self) -> None:
    shortcut = self.config.drag_shortcut
    if not shortcut:
        return
    result = _x11_open_grab(shortcut)
    if result is None:
        logger.warning("Could not grab hotkey '%s'.", shortcut)
        return
    conn, kc, mods = result
    self._x11_grab_conn   = conn
    self._grab_keycode    = kc
    self._grab_mods       = mods
    self._registered_shortcut = shortcut
    libx11.XConnectionNumber.restype = ctypes.c_int
    fd = libx11.XConnectionNumber(conn)
    self._x11_io_watch_id = GLib.io_add_watch(
        fd, GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP,
        self._on_x11_event
    )
```

**`_teardown_drag_hotkey()`** *(method on ClockWindow)*

Centralised teardown — called from `update_from_config` on shortcut change and from `_on_close`.

Teardown sequence (order is critical to prevent use-after-free):

```python
def _teardown_drag_hotkey(self) -> None:
    if self._x11_io_watch_id:
        GLib.source_remove(self._x11_io_watch_id)   # 1. detach watcher FIRST
        self._x11_io_watch_id = 0
    if self._x11_grab_conn is None:
        return
    conn = self._x11_grab_conn
    self._x11_grab_conn = None                       # 2. null before draining
    # 3. drain remaining events
    ev = _XEvent()
    while libx11.XPending(conn) > 0:
        libx11.XNextEvent(conn, ctypes.byref(ev))
    # 4. ungrab key for all lock-modifier permutations
    libx11.XDefaultRootWindow.restype = ctypes.c_ulong
    root = libx11.XDefaultRootWindow(conn)
    for extra in (0, LockMask, Mod2Mask, LockMask | Mod2Mask):
        libx11.XUngrabKey(conn, self._grab_keycode, self._grab_mods | extra, root)
    libx11.XFlush(conn)
    libx11.XCloseDisplay(conn)                       # 5. close
    self._grab_keycode = 0
    self._grab_mods    = 0
    self._registered_shortcut = ""
    # If drag mode was ON, restore click-through so the window does not get stuck
    if self._drag_mode:
        _x11_set_click_through(self)
        self._drag_mode = False
```

**`_on_map` change**

Replace the existing `_apply_x11_hints` timeout with a combined sequence:

```python
GLib.timeout_add(150, self._restore_position)
GLib.timeout_add(200, self._apply_x11_hints)    # sets click-through
GLib.timeout_add(300, self._on_map_register_hotkey)  # runs after click-through is set
```

`_on_map_register_hotkey` is a one-shot wrapper:

```python
def _on_map_register_hotkey(self) -> bool:
    self._register_drag_hotkey()
    return False
```

**`_on_x11_event(fd, condition) -> bool`**

```python
def _on_x11_event(self, fd, condition) -> bool:
    if condition & (GLib.IO_ERR | GLib.IO_HUP):
        logger.warning("X11 grab connection lost — drag hotkey disabled.")
        # Partial teardown: GLib removes this source automatically on SOURCE_REMOVE,
        # so we only need to drain, ungrab, and close.
        self._x11_io_watch_id = 0   # already being removed by SOURCE_REMOVE
        conn = self._x11_grab_conn
        self._x11_grab_conn = None
        if conn:
            ev_buf = _XEvent()
            while libx11.XPending(conn) > 0:
                libx11.XNextEvent(conn, ctypes.byref(ev_buf))
            libx11.XDefaultRootWindow.restype = ctypes.c_ulong
            root = libx11.XDefaultRootWindow(conn)
            for extra in (0, LockMask, Mod2Mask, LockMask | Mod2Mask):
                libx11.XUngrabKey(conn, self._grab_keycode, self._grab_mods | extra, root)
            libx11.XCloseDisplay(conn)
        self._grab_keycode = 0
        self._grab_mods    = 0
        self._registered_shortcut = ""
        return GLib.SOURCE_REMOVE   # stop spinning on dead fd
    conn = self._x11_grab_conn
    if conn is None:
        return GLib.SOURCE_REMOVE
    ev_buf = _XEvent()
    while libx11.XPending(conn) > 0:
        libx11.XNextEvent(conn, ctypes.byref(ev_buf))
        ev = ctypes.cast(ctypes.byref(ev_buf), ctypes.POINTER(_XKeyEvent)).contents
        if ev.type != KeyPress:
            continue
        pressed_mods = ev.state & ~(LockMask | Mod2Mask)
        if ev.keycode == self._grab_keycode and pressed_mods == self._grab_mods:
            self._toggle_drag_mode()
    return GLib.SOURCE_CONTINUE
```

**`_toggle_drag_mode()`**

```python
def _toggle_drag_mode(self) -> None:
    if self._drag_mode:
        _x11_set_click_through(self)
        self._drag_mode = False
        logger.debug("Drag mode OFF.")
    else:
        _x11_unset_click_through(self)
        self._drag_mode = True
        logger.debug("Drag mode ON.")
```

**`_on_drag_begin` guard** *(new lines prepended to the existing method body)*

```python
def _on_drag_begin(self, gesture, start_x, start_y):
    # NEW: deny drag when not in drag mode
    if not self._drag_mode:
        gesture.set_state(Gtk.EventSequenceState.DENIED)
        return
    # EXISTING logic below — unchanged:
    pos = _x11_get_window_position(self)
    if pos is not None:
        self._drag_win_x, self._drag_win_y = pos
    else:
        self._drag_win_x = self.config.pos_x
        self._drag_win_y = self.config.pos_y
```

#### `update_from_config` change

Re-register hotkey only when shortcut string changes. The `commit` parameter controls whether hotkey re-registration runs — live-preview calls pass `commit=False`:

```python
def update_from_config(self, config: ClockConfig, commit: bool = True) -> None:
    self.config = config
    self._keep_above = config.always_on_top
    self._apply_config()
    self._controller.update_config(config)
    self._update_display()
    config_manager.save(config)
    GLib.idle_add(self._restore_position)
    # config_manager.save is called unconditionally (matching existing behavior);
    # live-preview calls will persist intermediate shortcut strings, but Cancel
    # restores the original via a subsequent commit=True call.

    if commit and config.drag_shortcut != self._registered_shortcut:
        self._teardown_drag_hotkey()
        self._register_drag_hotkey()
```

#### `_on_close` change

```python
self._teardown_drag_hotkey()   # before self._controller.stop()
```

Note: `_teardown_drag_hotkey` already handles resetting drag mode and restoring click-through if needed, so `_on_close` requires no special case for drag state.

---

### 3. `SettingsDialog` (`settings_dialog.py`)

#### Shortcut capture row

- Label: `"Drag shortcut"`
- Button showing current value (`"Not set"` if empty)

**Capture mode lifecycle:**

1. Click button → `_enter_capture_mode()`: button label = `"Press keys…"`, attach `Gtk.EventControllerKey` to dialog
2. Key event handler priority (checked in order):
   - If keyval is `Gdk.KEY_Escape` → `_cancel_capture()`: restore previous label, detach controller
   - If keyval is `Gdk.KEY_BackSpace` **and** no modifiers → `_clear_shortcut()`: set `config.drag_shortcut = ""`, button label = `"Not set"`, detach controller
   - If modifier mask has ≥ 1 modifier (Ctrl/Alt/Shift/Super) → `_accept_shortcut(keyval, state)`: format and store
   - Bare modifier key press alone → ignore, stay in capture mode

**`_accept_shortcut(keyval, state)` key name formatting:**

```python
key_name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval))
# e.g. GDK_KEY_M with Shift → Gdk.keyval_to_lower → GDK_KEY_m → "m"
# Build mod prefix in canonical order: Ctrl, Alt, Shift, Super
parts = []
if state & Gdk.ModifierType.CONTROL_MASK:  parts.append("Ctrl")
if state & Gdk.ModifierType.ALT_MASK:      parts.append("Alt")
if state & Gdk.ModifierType.SHIFT_MASK:    parts.append("Shift")
if state & Gdk.ModifierType.SUPER_MASK:    parts.append("Super")
parts.append(key_name)
shortcut = "+".join(parts)   # e.g. "Ctrl+Shift+m"
config.drag_shortcut = shortcut
button.set_label(shortcut)
```

`Gdk.keyval_to_lower` ensures `"m"` is stored regardless of whether Shift was held.

#### Live preview vs. commit

`SettingsDialog` has three call sites for `update_from_config`. Required changes:

| Call site | Current call | New call |
|---|---|---|
| `_on_any_change` (live preview, every widget change) | `update_from_config(cfg)` | `update_from_config(cfg, commit=False)` |
| `_on_ok` (OK / Apply button) | `update_from_config(cfg)` | `update_from_config(cfg, commit=True)` *(default, no change)* |
| `_on_cancel` (Cancel / restore) | `update_from_config(original_cfg)` | `update_from_config(original_cfg, commit=True)` *(default, no change)* |

Only `_on_any_change` requires an explicit `commit=False`. The shortcut capture widget's `_accept_shortcut` and `_clear_shortcut` update `config.drag_shortcut` and then rely on `_on_any_change` to propagate — they do not call `update_from_config` directly.

---

## Data Flow

```
User presses hotkey
  → XGrabKey fires KeyPress on dedicated X11 connection (root window)
  → GLib.io_add_watch wakes up _on_x11_event
  → drain XPending loop → KeyPress matches → _toggle_drag_mode()
  → if enabling drag:
      _x11_unset_click_through() → XShapeCombineRectangles(full rect) → window receives input
      _drag_mode = True → GestureDrag events processed normally
  → if disabling drag:
      _x11_set_click_through() → XShapeCombineRectangles(0 rects) → click-through restored
      _drag_mode = False → _on_drag_begin denies all sequences
```

---

## Error Handling

- `_parse_shortcut` failure → log warning, skip registration. Config value preserved so user can fix in Settings.
- `XGrabKey` failure (key grabbed by another app) → log warning, hotkey silently unavailable.
- X11 connection error in `_on_x11_event` → return `SOURCE_REMOVE`, null `_x11_grab_conn`, log warning.
- All X11 ctypes calls wrapped in try/except (consistent with existing helpers).

---

## Testing

**Unit tests:**

- `_parse_shortcut`: valid strings (`"Ctrl+m"`, `"Ctrl+Shift+m"`, `"Super+F1"`), unknown key name → `None`, no modifier → `None`, empty string → `None`.
- `_toggle_drag_mode`: mock `_x11_set_click_through` / `_x11_unset_click_through`; verify `_drag_mode` flips on repeated calls.
- `_on_x11_event`:
  - Mock `XPending`/`XNextEvent` with matching `KeyPress` → verify `_toggle_drag_mode` called.
  - Non-matching keycode → verify `_toggle_drag_mode` not called.
  - `IO_ERR` condition → verify `SOURCE_REMOVE` returned and `_x11_grab_conn` set to `None`.
- `_on_drag_begin` guard: verify gesture denied when `_drag_mode = False`.
- `SettingsDialog` shortcut capture:
  - `Ctrl+Shift+M` press → stored as `"Ctrl+Shift+m"` (lowercase key).
  - `Escape` → shortcut unchanged.
  - `Backspace` with no modifier → shortcut cleared to `""`.

**Manual:**

- Set shortcut in Settings (e.g. `Ctrl+Shift+m`), press it → window becomes draggable.
- Drag window to new position → position saved on release.
- Press hotkey again → click-through restored, window not draggable.
- Clear shortcut in Settings → hotkey stops working.

---

## Out of Scope

- Wayland support (existing app is X11-only for advanced features).
- Non-modifier single-key shortcuts (require modifier to avoid conflicts with normal typing).
- Visual indicator in the window while drag mode is active (can be added later).
