# Proposal: Linux Clock App

## Why

Linux desktop users — đặc biệt developers dùng multi-monitor hay tiling WMs — không có giải pháp clock widget nào vừa cross-desktop, vừa GUI-configurable, vừa Wayland-compatible. Conky mạnh nhưng yêu cầu edit config file; Cairo-clock đẹp nhưng bị bỏ rơi từ 2013 và không hỗ trợ Wayland; GNOME Clocks/KClock không phải floating widget. Một GTK 4 clock widget đóng gói Flatpak, cài được không cần terminal, sẽ lấp đầy gap này.

## What Changes

Greenfield project — không modify hệ thống nào hiện có. Các capability mới được tạo:

1. **Floating clock window** hiển thị thời gian real-time trên desktop, có thể drag để reposition
2. **Right-click settings panel** để customize appearance mà không cần edit file config
3. **Persistence layer** lưu vị trí, theme, format về `~/.config/linux-clock-app/config.json`
4. **Flatpak packaging** để cài đặt one-click không cần terminal

## Capabilities

### New Capabilities
- `clock-display`: Hiển thị digital clock real-time, cập nhật mỗi giây (khi show seconds) hoặc mỗi phút
- `clock-positioning`: Drag-to-reposition, position được lưu và restore khi mở lại
- `clock-formatting`: Toggle 12h/24h, show/hide seconds, show/hide date
- `appearance-settings`: Font family/size, text color, background color, opacity (0-100%)
- `always-on-top`: Window stays above other windows (X11 đầy đủ; Wayland best-effort)
- `settings-ui`: Right-click context menu → Settings dialog với live preview
- `flatpak-packaging`: Flatpak manifest, publish-ready cho Flathub

### Modified Capabilities
N/A (greenfield)

## Scope

### In Scope
- Digital clock display (HH:MM với optional seconds)
- 12h / 24h format toggle
- Show/hide date bên dưới clock
- Drag-to-reposition; position saved on exit
- Right-click context menu với Settings option
- Font family và size selector
- Text color và background color picker
- Background opacity slider (0–100%)
- Always-on-top toggle (X11 full support; Wayland best-effort, documented)
- Flatpak packaging và Flathub-ready manifest

### Out of Scope (Non-Goals)
- Analog clock mode (V2)
- Multiple timezone / world clock (V2)
- Alarm / timer functionality (V2)
- GtkLayerShell / true Wayland desktop overlay (V2)
- Snap packaging (V2)
- Theme import/export (V2)
- Weather widget (out of scope entirely)
- Network access của bất kỳ loại nào

## Success Criteria
- User có thể cài app qua Flatpak và thấy clock hiển thị trong vòng 30 giây mà không cần mở terminal
- User có thể drag clock đến vị trí mới và position được restore chính xác sau khi restart app
- User có thể thay đổi font, color, opacity qua Settings dialog trong 3 clicks từ right-click menu
- Clock update đúng giờ với độ trễ < 1 giây so với system clock
- App sử dụng < 50MB RAM và < 1% CPU khi idle (seconds hidden) trên hardware phổ thông
- Always-on-top hoạt động đúng trên X11 và được document rõ limitation trên Wayland GNOME

## Impact
- **New standalone app** — không ảnh hưởng hệ thống nào hiện có
- **Dependencies**: Python 3.10+, GTK 4, PyGObject (libgirepository) — bundled trong Flatpak
- **Config file**: `~/.config/linux-clock-app/config.json` — không conflict với app nào khác
- **Positioning vs competitors**:
  - Thay thế Cairo-clock (abandoned, GTK2, X11-only) cho users muốn floating clock
  - Complement Conky (vẫn mạnh hơn cho power users với custom scripts)
  - Alternative cho GNOME Desktop Widgets extension (cross-desktop, không bị break theo GNOME version)
