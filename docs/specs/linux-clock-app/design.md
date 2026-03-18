# Design: Linux Clock App

## Context

Linux desktop users — đặc biệt developers dùng multi-monitor hoặc tiling WMs — không có giải pháp clock widget nào vừa cross-desktop, GUI-configurable, và Wayland-compatible. App này là một standalone floating GTK 4 clock widget được đóng gói Flatpak, chạy được trên mọi Linux desktop không cần cấu hình.

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│                Application                  │
│  ┌─────────────┐    ┌────────────────────┐  │
│  │  ClockWindow│    │   SettingsDialog   │  │
│  │  (GTK4 Win) │◄───│   (GTK4 Dialog)   │  │
│  └──────┬──────┘    └────────┬───────────┘  │
│         │                    │              │
│  ┌──────▼──────────────────▼─────────────┐  │
│  │           ClockController             │  │
│  │  (business logic, GLib timer)         │  │
│  └──────────────────┬────────────────────┘  │
│                     │                       │
│  ┌──────────────────▼────────────────────┐  │
│  │           ConfigManager               │  │
│  │  (~/.config/linux-clock-app/          │  │
│  │   config.json)                        │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

Single-process Python app. Không có network, không có background service.

## Components

### Component 1: ClockWindow
- **Purpose**: Main floating window hiển thị thời gian. Là entry point của app. Handle drag-to-reposition, right-click context menu, always-on-top.
- **Interface**:
  - Input: `ClockConfig` từ ConfigManager khi khởi động
  - Output: position updates → ConfigManager; right-click events → SettingsDialog
- **Dependencies**: ClockController (để lấy formatted time string), ConfigManager (load/save position & always-on-top state)

### Component 2: ClockController
- **Purpose**: Business logic layer. Quản lý GLib timer, format time string theo config, notify ClockWindow khi cần update.
- **Interface**:
  - `start()` — bắt đầu timer
  - `stop()` — dừng timer
  - `get_formatted_time(config) -> str` — trả về time string theo format settings
  - `get_formatted_date(config) -> str` — trả về date string hoặc empty
- **Dependencies**: Python `datetime` stdlib, `GLib.timeout_add_seconds()`

### Component 3: SettingsDialog
- **Purpose**: GTK 4 dialog cho phép user thay đổi appearance và format settings với live preview.
- **Interface**:
  - Input: current `ClockConfig`
  - Output: updated `ClockConfig` on close → ConfigManager
  - Live preview: gửi config changes tạm thời về ClockWindow trong khi dialog mở
- **Dependencies**: ClockWindow (live preview), ConfigManager (save on close)

### Component 4: ConfigManager
- **Purpose**: Đọc/ghi config JSON. Handle first-launch defaults, corrupt file recovery, directory creation.
- **Interface**:
  - `load() -> ClockConfig` — đọc file, fallback về defaults nếu lỗi
  - `save(config: ClockConfig)` — ghi file atomically (write temp → rename)
- **Dependencies**: Python `json`, `pathlib` stdlib

### Component 5: SingleInstanceGuard
- **Purpose**: Đảm bảo chỉ một instance chạy. Dùng Gio.Application với unique application ID.
- **Interface**: Wraps `Gtk.Application` với `application_id="io.github.<user>.LinuxClockApp"`
- **Dependencies**: `Gio.Application` (GTK/GIO)

## Data Model

### ClockConfig (persisted to JSON)
```python
@dataclass
class ClockConfig:
    # Window state
    pos_x: int = 100
    pos_y: int = 100
    always_on_top: bool = False

    # Format
    use_24h: bool = True
    show_seconds: bool = False
    show_date: bool = True

    # Appearance
    font_family: str = "Sans"
    font_size: int = 36
    text_color: str = "#FFFFFF"      # hex RRGGBB
    bg_color: str = "#000000"        # hex RRGGBB
    bg_opacity: float = 0.7          # 0.0 – 1.0
```

### config.json example
```json
{
  "pos_x": 1200,
  "pos_y": 50,
  "always_on_top": true,
  "use_24h": true,
  "show_seconds": false,
  "show_date": true,
  "font_family": "Monospace",
  "font_size": 36,
  "text_color": "#FFFFFF",
  "bg_color": "#000000",
  "bg_opacity": 0.7
}
```

## API Design

Desktop app — không có HTTP API. Internal interfaces:

| Caller | Callee | Method | Purpose |
|--------|--------|--------|---------|
| main() | SingleInstanceGuard | `run()` | App entry, enforce single instance |
| ClockWindow | ClockController | `get_formatted_time()` | Get time string mỗi tick |
| ClockWindow | SettingsDialog | `show(config)` | Mở settings từ right-click |
| SettingsDialog | ClockWindow | `preview(config)` | Live preview khi thay đổi settings |
| SettingsDialog | ConfigManager | `save(config)` | Lưu khi đóng dialog |
| ClockWindow | ConfigManager | `save(config)` | Lưu position khi move/close |
| main() | ConfigManager | `load()` | Load config khi khởi động |

## Error Handling

| Error | Handling |
|-------|----------|
| `config.json` không tồn tại | Tạo mới với defaults, không báo lỗi |
| `config.json` corrupt (invalid JSON) | Log warning to stderr, dùng defaults, ghi đè file |
| `~/.config/linux-clock-app/` không tồn tại | `Path.mkdir(parents=True, exist_ok=True)` |
| Font không tồn tại trên hệ thống | Fallback về "Sans", log warning |
| GTK không thể set keep_above (Wayland) | Silently ignore, hiển thị tooltip một lần |
| Second instance launched | `Gio.Application` tự raise existing window, exit new process |
| Config write fail (disk full) | Log error to stderr, app vẫn chạy với in-memory config |

## Goals / Non-Goals

**Goals:**
- Floating digital clock widget chạy được trên X11 và Wayland
- Zero-config first launch với sensible defaults
- Customisable appearance qua GUI không cần edit file
- Cross-desktop (GNOME, KDE, Xfce, tiling WMs) via Flatpak
- < 50MB RAM, < 1% CPU khi idle

**Non-Goals:**
- Analog clock mode (V2)
- Multiple timezones (V2)
- GtkLayerShell true desktop overlay (V2)
- Alarm / timer features
- Network connectivity
- Windows / macOS support

## Decisions

### Decision 1: Python + GTK 4 thay vì C + GTK 4
- **Chosen**: Python 3.10+ với PyGObject
- **Alternatives**: C + GTK 4 (compiled), Qt6/PyQt6, Electron
- **Rationale**: Prototype trong ~200 LOC; development speed >> runtime overhead cho một clock widget; Python pre-installed trên hầu hết distros; Flatpak bundle loại bỏ dependency concerns
- **Trade-off**: Slightly higher startup time (~0.3s) so với C — acceptable

### Decision 2: Gtk.Label thay vì Cairo DrawingArea cho digital clock
- **Chosen**: `Gtk.Label` với CSS font/color styling
- **Alternatives**: `Gtk.DrawingArea` + Cairo (custom rendering)
- **Rationale**: Digital-only MVP không cần custom drawing; Label đơn giản hơn 10x; font/color dễ control qua CSS provider
- **Trade-off**: V2 analog mode sẽ cần refactor sang DrawingArea — accepted

### Decision 3: JSON file thay vì SQLite/dconf
- **Chosen**: Plain JSON tại `~/.config/linux-clock-app/config.json`
- **Alternatives**: dconf (GNOME-specific), SQLite (overkill), INI file
- **Rationale**: Human-readable, dễ backup, no external deps, config schema đơn giản không cần DB
- **Trade-off**: Không có versioning/migration — acceptable cho MVP schema đơn giản

### Decision 4: Gio.Application cho single instance
- **Chosen**: `Gtk.Application` với unique application ID
- **Alternatives**: Lock file (`/tmp/linux-clock-app.lock`), Unix socket
- **Rationale**: GTK best practice; tích hợp với desktop session; tự động handle raise window
- **Trade-off**: Buộc phải có application ID từ đầu — acceptable, cần cho Flatpak anyway

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Wayland "always-on-top" bị ignore trên GNOME Wayland | High | Medium | Document rõ trong README và tooltip UI; recommend GNOME Desktop Widgets extension cho GNOME users |
| GTK 4 API breaking changes | Medium | Medium | Pin minimum GTK version trong Flatpak manifest; dùng stable APIs only |
| PyGObject bindings không có sẵn ngoài Flatpak | Medium | Medium | Flatpak bundle all deps; document manual install cho non-Flatpak |
| Font rendering khác nhau giữa distros | Low | Low | Dùng system default font làm fallback; test trên Ubuntu + Fedora + Arch |
| Single developer abandonment | Medium | High | Giữ scope nhỏ; document rõ; accept community PRs |
| **Contrarian**: Wayland fragmentation tạo chronic support burden | High | Medium | Scope MVP tới X11 + basic Wayland; defer GtkLayerShell tới V2; document compatibility matrix |

## Testing Strategy

| Requirement Priority | Test Type | Approach |
|---------------------|-----------|----------|
| MUST (REQ-01,02,03,04,06,07,10) | Unit tests | pytest — test ClockController formatting, ConfigManager load/save/corrupt-recovery, SingleInstanceGuard logic |
| MUST | Integration tests | Spawn app process, verify config file written correctly, verify single-instance behaviour |
| SHOULD (REQ-05,08,09,11) | Manual testing | Test matrix: X11/Wayland × GNOME/KDE/Xfce; test font fallback; test Flatpak install |
| All | Smoke test | `python -m linux_clock_app --test-mode` — launch, verify window opens, quit after 2s |

**Coverage target**: 80% line coverage cho `config_manager.py` và `clock_controller.py`
