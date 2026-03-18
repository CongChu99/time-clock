# Research: Linux Clock App
> Mode: research
> Date: 2026-03-17

---

## Executive Summary

The Linux desktop clock widget space is active but fragmented: existing solutions either tie deeply into a specific desktop environment (GNOME, KDE, Xfce panel applets) or require significant manual configuration (Conky). A standalone, lightweight, cross-desktop clock app with clean defaults and a simple customisation UI represents a genuine gap. The primary technical challenge is supporting both X11 and Wayland display servers, since Wayland intentionally restricts application-level "always-on-top" and transparent-overlay behaviour.

---

## Assumptions

The following assumptions were made because the feature description was brief. They should be validated with the product owner before development begins.

- **Target display**: standalone floating window that stays visible on the desktop, not a panel applet.
- **Primary platform**: modern Ubuntu/Debian/Fedora desktops running GNOME or KDE under Wayland, with X11/Xorg as a secondary target.
- **Tech stack preference**: Python + GTK 4, chosen for native Linux integration, low overhead, and available tutorials.
- **Scope**: personal/hobby use; no enterprise or accessibility compliance requirements in the MVP.
- **No network features in MVP**: world clock and weather are post-MVP.

---

## Problem Statement

Linux users who want a persistent, at-a-glance clock on their desktop have no single satisfying solution:

1. **Panel clocks** (GNOME top bar, Xfce panel) are small and locked to the panel position — they cannot be repositioned to an idle screen area.
2. **Conky** is powerful but requires hand-editing a configuration file with a custom DSL; the barrier to entry is high for non-technical users.
3. **Cairo-clock** is visually appealing but has not been maintained for over a decade and has known high CPU usage issues.
4. **GNOME Shell extensions** (Desktop Widgets) only work on GNOME and break across major GNOME version upgrades.
5. **KClock** is primarily designed for Plasma Mobile and does not behave as a lightweight always-visible desktop widget.

The result: users who want a simple, resizable, repositionable clock widget with minimal setup friction have to choose between dated software, complex configuration, or desktop-environment lock-in.

---

## Target Users

### Persona 1 — The Productivity-Focused Developer
- **Background**: Software developer, uses a multi-monitor setup, runs Ubuntu or Arch Linux with GNOME or a tiling window manager.
- **Need**: A secondary clock visible at all times on a second monitor without occupying taskbar space.
- **Pain point**: Existing panel clocks are too small; Conky requires too much setup time.
- **Key feature**: Minimal, always-on-top floating window; stays out of the way.

### Persona 2 — The Customisation Enthusiast
- **Background**: Linux hobbyist, spends time ricing their desktop with custom themes and wallpapers.
- **Need**: A clock widget that matches their overall desktop aesthetic — font, colour, transparency.
- **Pain point**: Cairo-clock themes are old; Conky configuration is fragile.
- **Key feature**: Live theme editor, font picker, colour/opacity controls.

### Persona 3 — The Non-Technical Linux User
- **Background**: Migrated from Windows or macOS, uses Linux Mint or Ubuntu.
- **Need**: A desktop clock gadget similar to Windows Sidebar widgets or macOS Dashboard clock.
- **Pain point**: Cannot find an easy GUI-based clock widget that "just works" on their desktop.
- **Key feature**: Simple installation (Snap/Flatpak), GUI settings, no terminal required.

### Persona 4 — The Presenter / Streamer
- **Background**: Uses OBS or a presentation tool on Linux; needs a visible clock in the corner of their screen.
- **Need**: Large, readable clock that can be overlaid or kept on top.
- **Pain point**: Most clocks disappear behind full-screen applications.
- **Key feature**: Always-on-top mode, configurable size, transparent background.

---

## Core Workflows

### Workflow 1 — First Launch
1. User installs the app (Flatpak/Snap/deb).
2. App launches with sensible defaults: digital clock, system font, white text, semi-transparent background, top-right corner.
3. User sees the clock immediately without any configuration.

### Workflow 2 — Reposition the Clock
1. User left-clicks and drags the clock window to a new screen position.
2. Position is saved automatically and restored on next launch.

### Workflow 3 — Customise Appearance
1. User right-clicks the clock to open a context menu.
2. Selects "Settings" to open a settings dialog.
3. Adjusts font family, font size, text colour, background colour, opacity, and clock format (12h/24h, show/hide seconds, show/hide date).
4. Closes dialog; changes are applied live.

### Workflow 4 — Toggle Always-On-Top
1. User right-clicks and selects "Always on top".
2. Clock window stays above all other windows (X11) or uses compositor hint on Wayland.

### Workflow 5 — Resize Clock
1. User right-clicks and chooses a size preset (Small / Medium / Large) or drags window edge.
2. Font scales proportionally with window size.

### Workflow 6 — Multiple Time Zones (Post-MVP)
1. User opens settings and adds a second timezone.
2. A second row/clock appears showing the chosen city's local time.

---

## Domain Entities

| Entity | Attributes | Notes |
|---|---|---|
| **ClockInstance** | id, format (digital/analog), timezone, position (x, y), size (w, h), alwaysOnTop | Main display object |
| **Theme** | name, fontFamily, fontSize, textColor, bgColor, opacity, borderRadius | Visual configuration |
| **ClockFormat** | use24h, showSeconds, showDate, showDayOfWeek | Display format options |
| **TimeZone** | zoneId (IANA), displayLabel | e.g. "Asia/Ho_Chi_Minh" |
| **AppSettings** | launchOnBoot, defaultTheme, savedClocks[] | Persisted to disk (JSON/INI) |

---

## Business Rules

1. **Time source**: Always use the system clock; no custom NTP configuration in MVP.
2. **Persistence**: All settings are saved to `~/.config/<appname>/config.json` on every change.
3. **Update rate**: Clock display must update at least once per second when seconds are shown; once per minute otherwise (to reduce CPU usage).
4. **Minimum size**: Clock window must not be resizable below 80×30 px to remain readable.
5. **Transparency**: Background opacity must be configurable from 0% (fully transparent) to 100% (fully opaque).
6. **Always-on-top (X11)**: Use `_NET_WM_STATE_ABOVE` EWMH hint.
7. **Always-on-top (Wayland)**: Use `gtk_window_set_keep_above()`; note this may be silently ignored by some compositors.
8. **No network access**: The application must not require internet connectivity for core clock display.
9. **Single instance**: Only one application instance should run at a time; a second launch should focus the existing window.

---

## Competitive Landscape

### 1. Conky
- **Type**: System monitor with clock capability via config scripting
- **Tech**: C++, Lua scripting
- **Strengths**: Extremely powerful, highly customisable, very low resource usage, large theme community
- **Weaknesses**: No GUI for configuration; requires editing text config files; steep learning curve for new users; Wayland support is limited/experimental
- **Status**: Actively maintained (2024)
- **URL**: https://github.com/brndnmtthws/conky

### 2. Cairo-Clock (MacSlow's)
- **Type**: Standalone analog clock with compositing support
- **Tech**: C, GTK 2, Cairo, librsvg
- **Strengths**: Beautiful vector rendering, multiple themes, transparency/compositing effects
- **Weaknesses**: Last commit ~2013; unmaintained; requires GTK 2; high CPU usage reported; no Wayland support
- **Status**: Abandoned
- **URL**: https://github.com/MacSlow/cairo-clock

### 3. GNOME Clocks
- **Type**: Full-featured clock application (alarms, timers, world clocks, stopwatch)
- **Tech**: C, GTK 4, GNOME platform libraries
- **Strengths**: Polished, official GNOME app, Flatpak available, alarm/timer features
- **Weaknesses**: Not a desktop widget — opens in its own window, not always-on-top; GNOME-only integration
- **Status**: Actively maintained
- **URL**: https://apps.gnome.org/Clocks/

### 4. KClock (KDE)
- **Type**: Convergent clock app for desktop and Plasma Mobile
- **Tech**: C++, Qt 5/6, KDE Frameworks, QML
- **Strengths**: 12 clock styles, alarms/timers, wakes device from suspend, mobile/desktop convergent
- **Weaknesses**: KDE/Plasma dependency; not useful as a standalone floating widget; heavyweight for casual use
- **Status**: Actively maintained
- **URL**: https://apps.kde.org/kclock/

### 5. xclock
- **Type**: Minimal X11 clock (part of x11-apps)
- **Tech**: C, Xlib, Xt
- **Strengths**: Extremely low CPU/memory usage; pre-installed on many distros; analog and digital modes
- **Weaknesses**: X11-only; no Wayland; ugly default appearance; no GUI settings; minimal customisation
- **Status**: Maintained (part of X.Org project)
- **URL**: https://www.x.org/wiki/

### 6. GNOME Shell Extension — Desktop Widgets (Desktop Clock)
- **Type**: GNOME Shell extension adding clock/widget overlays to the desktop
- **Tech**: JavaScript, GNOME Shell API
- **Strengths**: True desktop overlay; analog and digital clock; repositionable by dragging; Wayland-compatible (via Shell)
- **Weaknesses**: GNOME-only; breaks on major GNOME version upgrades; requires GNOME Shell; no standalone use
- **Status**: Actively maintained (extensions.gnome.org)
- **URL**: https://extensions.gnome.org/extension/5156/desktop-clock/

### 7. ClockWidget (Snap)
- **Type**: Simple desktop clock widget
- **Tech**: Unknown (Snap package)
- **Strengths**: Easy snap install; customisable clock face, position, and size; right-click to configure
- **Weaknesses**: Limited feature set; small community; unclear maintenance status
- **Status**: Available on Snap Store
- **URL**: https://snapcraft.io/clockwidget

### 8. iClock
- **Type**: Fully customisable clock widget
- **Tech**: Python (GitHub: odest/iClock)
- **Strengths**: Open source; fully customisable components; cross-platform intent
- **Weaknesses**: Small project; limited documentation; unclear Wayland status
- **Status**: Active (recent commits)
- **URL**: https://github.com/odest/iClock

---

## Feature Comparison

| Feature | Conky | Cairo-Clock | GNOME Clocks | KClock | xclock | Desktop Widgets (GNOME ext) | ClockWidget | iClock |
|---|---|---|---|---|---|---|---|---|
| **Always-visible desktop widget** | Yes | Yes | No | No | Partial | Yes (GNOME only) | Yes | Yes |
| **GUI settings (no config file needed)** | No | Partial | Yes | Yes | No | No | Yes | Partial |
| **Analog clock mode** | Yes (Lua) | Yes | No | Yes | Yes | Yes | No | Unknown |
| **Digital clock mode** | Yes | No | Yes | Yes | Yes | Yes | Yes | Yes |
| **Font customisation** | Yes (config) | No | No | No | No | Partial | Yes | Yes |
| **Colour/theme customisation** | Yes (config) | Yes (themes) | No | Yes | Minimal | Minimal | Yes | Yes |
| **Transparency / opacity control** | Yes | Yes | No | No | No | Yes | Yes | Yes |
| **Always-on-top mode** | Partial | Yes | No | No | No | Yes | Yes | Unknown |
| **X11 support** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| **Wayland support** | Limited | No | Yes | Yes | No | Yes | Unknown | Unknown |
| **Alarm / timer** | No | No | Yes | Yes | No | No | No | No |
| **World clock / timezones** | Yes (config) | No | Yes | Yes | No | No | No | No |
| **Flatpak / Snap packaging** | No | No | Yes (Flatpak) | Yes (Flatpak) | No | N/A | Yes (Snap) | No |
| **Active maintenance** | Yes | No | Yes | Yes | Yes | Yes | Unknown | Yes |

---

## Gap Analysis

### Gap 1 — Cross-Desktop, Dependency-Free Widget
No existing solution works well as a desktop widget across GNOME, KDE, Xfce, and tiling WMs without pulling in a full desktop environment's framework. GNOME extensions only work on GNOME; KClock requires KDE; xclock is Xlib-only. A GTK 4 app with minimal dependencies can fill this gap.

### Gap 2 — Beginner-Friendly GUI Configuration
Conky (the most powerful option) requires editing text files. Cairo-clock's settings dialog is dated and unmaintained. No competitor combines rich customisation with a clean, discoverable GUI that a Linux newcomer can use without documentation. A right-click settings panel with live preview would be a first-class differentiator.

### Gap 3 — Modern Wayland-First Design with X11 Fallback
Cairo-clock (the most visually distinctive option) has no Wayland support. Most widget-style clocks either don't support Wayland or treat it as an afterthought. A new app designed with GTK 4's Wayland backend as the primary target, gracefully degrading on X11, has a clear technical advantage for users on modern Ubuntu 22.04+/Fedora 38+ systems.

### Gap 4 — Lightweight, Single-Purpose, No System Monitor Overhead
Conky is a full system monitor; using it just for a clock is overkill. GNOME Clocks and KClock are feature-heavy applications with alarms, timers, and world clocks that make them unsuitable as background desktop widgets. A focused, single-purpose clock widget with a small binary footprint addresses this gap.

### Gap 5 — Stable Cross-Version Packaging
GNOME Shell extensions break on major GNOME version bumps (a well-known pain point in the community). A standalone Flatpak-packaged app with no Shell API dependency would be significantly more stable across OS upgrades.

---

## Differentiation Strategy

1. **Zero-configuration first launch**: Ship with a visually appealing default (semi-transparent dark background, clean sans-serif font, 24h digital clock) so the app looks good immediately without any setup. Competitors either look dated by default (xclock, cairo-clock) or require manual config (Conky).

2. **Right-click-to-configure UX pattern**: A single right-click opens a settings popover with live preview — no separate settings window to hunt for. This is more discoverable than Conky's config file and more integrated than GNOME Clocks' settings screen.

3. **GTK 4 + Wayland-first**: Build on GTK 4 with `GtkLayerShell` (for true desktop overlay on Wayland compositors that support the `wlr-layer-shell` protocol) and fallback to `keep_above` hint. This is technically superior to cairo-clock (GTK 2, X11 only) and iClock (Wayland status unknown).

4. **Single Flatpak with no desktop-environment dependency**: Unlike GNOME extensions (GNOME-only), KClock (KDE-only), or xclock (X11-only), a Flatpak distribution ensures the app runs on any Linux desktop that supports Flatpak — GNOME, KDE, Xfce, BSPWM, etc.

5. **Open, extensible theme format**: Store themes as simple JSON files in `~/.local/share/<appname>/themes/`. Users can share themes via copy-paste, and the project can host a community theme gallery — replicating the success of Conky's theme community but with a much lower barrier to contribution.

---

## Initial MVP Scope

The MVP should deliver the core value proposition: a working, attractive, repositionable desktop clock with basic customisation, installable without a terminal.

| # | Feature | Priority | Notes |
|---|---|---|---|
| 1 | Digital clock display (HH:MM with optional seconds) | Must | Core function |
| 2 | 12h / 24h format toggle | Must | Most common user preference |
| 3 | Show/hide date below time | Must | High user demand |
| 4 | Drag to reposition; position saved on exit | Must | Core widget behaviour |
| 5 | Right-click context menu with Settings option | Must | Discoverability |
| 6 | Font family and size selector | Should | Key customisation gap |
| 7 | Text colour and background colour picker | Should | Aesthetic differentiation |
| 8 | Background opacity slider (0–100%) | Should | Transparency is a top user request |
| 9 | Always-on-top toggle (X11 + Wayland best-effort) | Should | Key for Persona 4 (streamer/presenter) |
| 10 | Flatpak packaging and publishing to Flathub | Should | Enables no-terminal install for Persona 3 |

**Post-MVP (V2)**:
- Analog clock mode
- Multiple timezone display
- Alarm / timer functionality
- Theme import/export (JSON)
- Snap packaging
- GtkLayerShell integration for true Wayland desktop overlay

---

## Technical Approaches

### Option A — Python + GTK 4 (PyGObject) — RECOMMENDED
- **Description**: Python application using GTK 4 via the PyGObject bindings. Uses `GLib.timeout_add_seconds()` for ticking, `Gtk.DrawingArea` (with Cairo) for the clock face, `Gtk.Window` with `keep_above` for always-on-top.
- **Pros**: Rapid development; large community; native GTK 4 Wayland backend; good theming integration with the host desktop; 2025 Linux Magazine article confirms active tutorial ecosystem.
- **Cons**: Python startup time slightly higher than compiled languages; requires Python runtime on host (usually pre-installed).
- **Wayland**: GTK 4 natively targets Wayland; `keep_above()` works on compositors that honour the hint.
- **Effort**: Low. A working prototype can be built in ~200 lines of Python.

### Option B — C + GTK 4
- **Description**: Same GTK 4 stack as Option A but compiled C for lower memory and faster startup.
- **Pros**: Smallest binary; no runtime dependency; best performance.
- **Cons**: Significantly slower to develop and maintain; overkill for a clock widget.
- **Recommendation**: Only worthwhile if performance profiling shows a real problem.

### Option C — Qt 5/6 (C++ or Python/PyQt6)
- **Description**: Qt-based window using `QLabel` or `QPainter` for rendering.
- **Pros**: Cross-platform (Linux, Windows, macOS); rich widget set; good Wayland support via Qt's Wayland platform plugin.
- **Cons**: Qt licensing (GPL vs LGPL vs commercial) adds complexity for distribution; Qt runtime is larger than GTK; less "native" feel on GNOME desktops.
- **Recommendation**: Viable but adds friction. Better choice if Windows/macOS support is needed later.

### Option D — Electron / Web Technologies
- **Description**: HTML/CSS/JS clock in an Electron window (e.g., Electron + Vue or React).
- **Pros**: Easiest web-developer on-ramp; extremely rich styling options.
- **Cons**: ~150 MB runtime overhead for a clock widget is unjustifiable; high memory and CPU usage; antithetical to the "lightweight" positioning.
- **Recommendation**: Do not use for this use case.

### Option E — Xlib / Xorg Overlay (pure C, no toolkit)
- **Description**: Draw directly on the X root window using Xlib and Cairo.
- **Pros**: Extremely low overhead; true desktop overlay without a window manager window.
- **Cons**: X11-only (no Wayland); very low-level; significant development effort; same approach used by xclock/Conky.
- **Recommendation**: Only if targeting X11-only environments (e.g., embedded Linux displays).

### Option F — GtkLayerShell (GTK + Wayland Layer Surface Protocol)
- **Description**: Uses the `gtk4-layer-shell` library to place the clock as a Wayland layer surface (like a status bar), rendering it truly "on the desktop" below all other windows or above them.
- **Pros**: True desktop overlay on Wayland; used by Waybar and other Wayland-native widgets; not affected by window focus.
- **Cons**: Only works on compositors implementing `wlr-layer-shell` (Sway, Hyprland, wlroots-based); does NOT work on GNOME or KDE Wayland; adds a library dependency.
- **Recommendation**: Include as an optional backend for tiling WM users (post-MVP).

**Final recommendation**: Start with **Option A (Python + GTK 4)**. Add GtkLayerShell as an optional post-MVP feature for tiling WM Wayland users.

---

## Contrarian View

**Argument against building this application:**

The Linux clock widget space already has more than a dozen solutions. The strongest counterargument is not about technical feasibility but about **maintenance burden vs. marginal utility**.

1. **The problem is mostly solved for technical users**: Conky, properly configured, does everything this app would do and more. The target audience of technical Linux users is, by definition, capable of editing a Conky config. Building a GUI wrapper adds code that needs to be maintained across GTK API changes, Wayland protocol updates, and distribution packaging changes.

2. **Wayland fragmentation will cause frustration**: The "always-on-top" and "desktop overlay" features — which are the core differentiators — behave differently on GNOME Wayland, KDE Wayland, and wlroots-based compositors. There is no single API that works everywhere. Users will file bug reports about behaviour that is outside the developer's control. This is a chronic maintenance pain point, as evidenced by the number of forum posts asking "why does always-on-top not work on Wayland?" (multiple forum threads from 2021–2025 confirm this).

3. **GNOME Shell extension Desktop Widgets already solves this for the largest Linux desktop user base**: GNOME is the dominant Linux desktop. The Desktop Widgets extension (extensions.gnome.org/extension/5156) already provides a repositionable, transparent, analog+digital clock widget on GNOME. The marginal value of a new app for GNOME users specifically is low.

4. **Low discoverability**: Without significant marketing/community effort, a new clock app will not surface above established alternatives in search results or package manager listings, limiting adoption.

**Counter to the contrarian view**: These arguments apply to a general-purpose app. If the scope is narrowed to "a clean, Flatpak-packaged, cross-desktop clock widget that works without configuration", there is still a real user need (evidenced by recurring forum questions on Linux Mint, Ubuntu, and Arch forums). The project is also a valid learning/portfolio project even if adoption is modest.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Wayland "always-on-top" behaves differently per compositor | High | High | Document limitations clearly; use GtkLayerShell as optional backend for wlroots compositors; graceful degradation |
| GTK 4 API breaking changes between versions | Medium | Medium | Pin minimum GTK version in Flatpak manifest; use stable GTK 4 APIs only |
| Low adoption / abandonment | High | Low | Scope MVP tightly; publish to Flathub early to gain visibility |
| Cairo-clock nostalgia — users expect analog clock | Medium | Low | Add analog mode in V2; digital-first is a valid MVP choice |
| Font rendering differences across distros | Low | Low | Use system default font as fallback; test on Ubuntu, Fedora, Arch |
| Always-on-top broken on GNOME Wayland (by design) | High | Medium | Document clearly; recommend GNOME users use the Desktop Widgets extension instead |
| Python PyGObject bindings not installed by default on some distros | Medium | Medium | Flatpak bundles all dependencies; document distro-specific install for non-Flatpak |
| Single developer burnout / unmaintained project | Medium | High | Keep scope small; accept community contributions via GitHub; use standard tooling |

---

## Recommendations

1. **Use Python + GTK 4 (PyGObject) as the primary stack**. It offers the best balance of development speed, native Linux integration, and Wayland support for this use case. A working MVP prototype can be built in a weekend.

2. **Prioritise Flatpak packaging from day one**. Publish to Flathub early to establish discoverability and enable one-click installation for non-technical users — this is the single biggest differentiator vs. older unmaintained tools.

3. **Be explicit about Wayland limitations in documentation**. The "always-on-top" feature cannot be guaranteed on all Wayland compositors. A clear compatibility matrix (GNOME / KDE / Sway / Hyprland / X11) prevents user frustration and reduces support burden.

4. **Design the theme/config format as a public JSON schema from day one**. This lowers the barrier for community contributions and positions the project to grow a theme ecosystem similar to Conky's, but with far lower configuration complexity.

5. **Do not implement alarm/timer/world clock in MVP**. These features already exist in GNOME Clocks and KClock. The MVP should be laser-focused on the desktop widget use case. Feature parity with full clock apps is not the goal.

6. **Consider the GNOME Desktop Widgets extension as a reference, not a competitor**. For GNOME-only users, recommend that extension. Focus this app's value proposition on cross-desktop users and those who want Flatpak-first, GUI-configured simplicity.

---

## Sources

- [Desktop Widgets (Desktop Clock) — GNOME Shell Extensions](https://extensions.gnome.org/extension/5156/desktop-clock/)
- [Best Clock And Weather Widgets For Linux — LinuxAndUbuntu](https://www.linuxandubuntu.com/home/best-clock-and-weather-widgets-for-linux/)
- [Clock — KDE Applications (KClock)](https://apps.kde.org/kclock/)
- [17 Best Free and Open Source Linux Clocks — LinuxLinks](https://www.linuxlinks.com/clocks/)
- [Install ClockWidget on Linux — Snap Store](https://snapcraft.io/clockwidget)
- [GitHub — MacSlow/cairo-clock](https://github.com/MacSlow/cairo-clock)
- [GitHub — odest/iClock: Fully Customizable Clock Widget](https://github.com/odest/iClock)
- [GitHub — sonnyp/Retro: Customizable clock widget (GTK 4)](https://github.com/sonnyp/Retro)
- [GitHub — davinellulinvega/Digital-clock: Qt clock widget for Linux](https://github.com/davinellulinvega/Digital-clock)
- [GitHub — MikaelPecyna/SimpleClock: Python/GTK app to display time](https://github.com/MikaelPecyna/SimpleClock)
- [Window of Opportunity — Linux Magazine (Cairo + GTK Python, 2025)](https://www.linux-magazine.com/Issues/2025/297/Graphics-in-Python-with-Cairo-and-GTK)
- [Simple clock using PyGTK and GObject.timeout_add() — GitHub Gist](https://gist.github.com/jampola/473e963cff3d4ae96707)
- [How to Install and Configure Conky — Linux.com](https://www.linux.com/topic/desktop/how-install-and-configure-conky/)
- [GitHub — wim66/clock-weather-conky](https://github.com/wim66/clock-weather-conky)
- [Overlay with GTK3 on Wayland — GNOME Discourse](https://discourse.gnome.org/t/overlay-with-gtk3-on-wayland/2216)
- [Always on Top: Ignored But Handy Feature in Linux Desktop — It's FOSS](https://itsfoss.com/always-on-top/)
- [xfce4-panel clock — Xfce Docs](https://docs.xfce.org/xfce/xfce4-panel/clock)
- [Use KDE's Digital Clock Widget as a World Clock — Linux Magazine](https://www.linux-magazine.com/Online/Blogs/Productivity-Sauce/Use-KDE-s-Digital-Clock-Widget-as-a-World-Clock)
- [GitHub — KDE/kclock: Clock app for Plasma Mobile](https://github.com/KDE/kclock)
- [GNOME Clocks Alternatives — AlternativeTo](https://alternativeto.net/software/gnome-clocks/)
- [Cairo-clock — Ubuntu Manpage](https://manpages.ubuntu.com/manpages/trusty/man1/cairo-clock.1.html)
- [MacSlow's Cairo Clock — LinuxLinks](https://www.linuxlinks.com/macslowscairoclock/)
