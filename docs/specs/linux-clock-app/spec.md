# Spec: Linux Clock App

## ADDED Requirements

### Requirement: REQ-01 — Digital Clock Display
Hiển thị thời gian real-time dạng digital (HH:MM hoặc HH:MM:SS).

**Priority**: MUST

#### Scenario: Hiển thị giờ mặc định
- **GIVEN** app vừa được khởi động lần đầu
- **WHEN** window xuất hiện
- **THEN** hiển thị giờ hiện tại theo system clock, format 24h, không có seconds, có date

#### Scenario: Clock tự cập nhật
- **GIVEN** app đang chạy với show seconds = true
- **WHEN** đồng hồ hệ thống tick thêm 1 giây
- **THEN** clock display cập nhật trong vòng 1 giây

---

### Requirement: REQ-02 — 12h/24h Format Toggle
User có thể switch giữa 12-hour (với AM/PM) và 24-hour format.

**Priority**: MUST

#### Scenario: Switch sang 12h
- **GIVEN** clock đang hiển thị 24h format (VD: "14:30")
- **WHEN** user toggle sang 12h trong Settings
- **THEN** clock hiển thị "2:30 PM" ngay lập tức

#### Scenario: Switch lại 24h
- **GIVEN** clock đang hiển thị 12h format
- **WHEN** user toggle sang 24h trong Settings
- **THEN** clock hiển thị format 24h không có AM/PM

---

### Requirement: REQ-03 — Show/Hide Date
User có thể hiển thị hoặc ẩn dòng date bên dưới clock.

**Priority**: MUST

#### Scenario: Bật date display
- **GIVEN** date đang bị ẩn
- **WHEN** user bật "Show date" trong Settings
- **THEN** một dòng text xuất hiện bên dưới clock hiển thị ngày tháng (VD: "Tue, 17 Mar 2026")

#### Scenario: Tắt date display
- **GIVEN** date đang hiển thị
- **WHEN** user tắt "Show date" trong Settings
- **THEN** dòng date biến mất, window co lại

---

### Requirement: REQ-04 — Drag to Reposition
User có thể drag clock window đến bất kỳ vị trí nào trên màn hình.

**Priority**: MUST

#### Scenario: Drag window
- **GIVEN** clock đang hiển thị ở vị trí mặc định
- **WHEN** user click-and-drag window đến góc dưới-phải màn hình
- **THEN** clock di chuyển đến vị trí mới ngay lập tức

#### Scenario: Position được restore sau restart
- **GIVEN** user đã drag clock đến vị trí (x=1200, y=800)
- **WHEN** user đóng app và mở lại
- **THEN** clock xuất hiện tại (x=1200, y=800)

---

### Requirement: REQ-05 — Always-On-Top Toggle
User có thể giữ clock window luôn hiển thị trên tất cả cửa sổ khác.

**Priority**: SHOULD

#### Scenario: Bật always-on-top trên X11
- **GIVEN** app đang chạy trên X11
- **WHEN** user bật "Always on top" qua right-click menu
- **THEN** clock window hiển thị trên tất cả cửa sổ khác, kể cả fullscreen app

#### Scenario: Wayland limitation
- **GIVEN** app đang chạy trên Wayland compositor không hỗ trợ hint
- **WHEN** user bật "Always on top"
- **THEN** app thực hiện best-effort (`gtk_window_set_keep_above`) và hiển thị tooltip: "Always-on-top may not work on all Wayland compositors"

---

### Requirement: REQ-06 — Single Instance
Chỉ một instance của app chạy tại một thời điểm.

**Priority**: MUST

#### Scenario: Mở lần 2
- **GIVEN** app đang chạy
- **WHEN** user mở app lần thứ hai (double-click icon hoặc terminal)
- **THEN** instance đang chạy được focus lên, instance mới không được tạo

---

### Requirement: REQ-07 — Right-Click Settings UI
Right-click vào clock mở context menu với option Settings.

**Priority**: MUST

#### Scenario: Mở context menu
- **GIVEN** clock đang hiển thị
- **WHEN** user right-click lên clock window
- **THEN** context menu xuất hiện với các options: Settings, Always on top, About, Quit

#### Scenario: Settings dialog mở
- **GIVEN** context menu đang hiển thị
- **WHEN** user click "Settings"
- **THEN** Settings dialog mở với live preview của clock

#### Scenario: Quit từ context menu
- **GIVEN** context menu đang hiển thị
- **WHEN** user click "Quit"
- **THEN** app đóng và config được lưu trước khi exit

---

### Requirement: REQ-08 — Font Customisation
User có thể chọn font family và size.

**Priority**: SHOULD

#### Scenario: Thay đổi font
- **GIVEN** Settings dialog đang mở
- **WHEN** user chọn font "Monospace 18" từ font picker
- **THEN** clock preview trong dialog cập nhật ngay lập tức với font mới

#### Scenario: Font không tồn tại
- **GIVEN** user chọn một font không còn được cài trên hệ thống
- **WHEN** app khởi động
- **THEN** app fallback về system default font, không crash

---

### Requirement: REQ-09 — Color & Opacity Settings
User có thể chọn text color, background color, và opacity.

**Priority**: SHOULD

#### Scenario: Thay đổi opacity
- **GIVEN** Settings dialog đang mở, opacity = 100%
- **WHEN** user kéo opacity slider xuống 50%
- **THEN** clock window trở nên semi-transparent ngay lập tức (live preview)

#### Scenario: Background fully transparent
- **GIVEN** user kéo opacity slider xuống 0%
- **THEN** chỉ text clock hiển thị, background hoàn toàn trong suốt

#### Scenario: Thay đổi text color
- **GIVEN** Settings dialog đang mở
- **WHEN** user chọn màu đỏ từ color picker
- **THEN** clock text chuyển sang màu đỏ trong live preview

---

### Requirement: REQ-10 — Settings Persistence
Tất cả settings được lưu tự động và restore khi restart.

**Priority**: MUST

#### Scenario: Auto-save
- **GIVEN** user thay đổi font trong Settings dialog
- **WHEN** user đóng dialog
- **THEN** config được ghi vào `~/.config/linux-clock-app/config.json` tự động

#### Scenario: Corrupt config fallback
- **GIVEN** `config.json` bị corrupt (invalid JSON)
- **WHEN** app khởi động
- **THEN** app load default settings và ghi đè file corrupt, không crash

#### Scenario: Config directory không tồn tại
- **GIVEN** `~/.config/linux-clock-app/` chưa tồn tại (first launch)
- **WHEN** app khởi động lần đầu
- **THEN** directory và config.json được tạo tự động với default values

---

### Requirement: REQ-11 — Flatpak Installation
App có thể được cài và chạy qua Flatpak không cần terminal commands phức tạp.

**Priority**: SHOULD

#### Scenario: Cài từ Flatpak bundle
- **GIVEN** user có file `.flatpak` bundle
- **WHEN** user double-click file hoặc chạy `flatpak install <bundle>`
- **THEN** app được cài và xuất hiện trong application launcher

#### Scenario: Chạy sau khi cài
- **GIVEN** app đã được cài qua Flatpak
- **WHEN** user click icon trong application launcher
- **THEN** clock window xuất hiện trong vòng 3 giây

## MODIFIED Requirements
N/A — greenfield project

## REMOVED Requirements
N/A — greenfield project
