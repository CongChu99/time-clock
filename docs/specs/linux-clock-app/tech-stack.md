# Tech Stack: Linux Clock App

## UI Framework
- **Chosen**: Python 3.10+ + GTK 4 (PyGObject)
- **Alternatives considered**:
  - C + GTK 4: faster binary, no runtime dep — rejected: slower dev, overkill for clock widget
  - Qt6 / PyQt6: cross-platform — rejected: heavier runtime, less native on GNOME/Xfce, licensing complexity
  - Electron: rejected — ~150MB runtime for a clock widget is unjustifiable
- **Lock-in risk**: Low — GTK 4 is open source, widely available on all major distros

## Rendering
- **Chosen**: `Gtk.Label` for digital clock display; `GLib.timeout_add_seconds()` for tick
- **Rationale**: Digital-only MVP does not require custom drawing. Simpler than Cairo `DrawingArea`. Font/color controlled via CSS provider.
- **Note**: V2 analog mode will require `Gtk.DrawingArea` + Cairo

## Persistence
- **Chosen**: JSON file at `~/.config/linux-clock-app/config.json` via Python `json` stdlib
- **Schema**: `{ position: {x, y}, theme: {font, fontSize, textColor, bgColor, opacity}, format: {use24h, showSeconds, showDate}, alwaysOnTop: bool }`
- **Lock-in risk**: None — plain JSON, no external dependency

## Packaging
- **Chosen**: Flatpak with manifest `io.github.<user>.LinuxClockApp.yml`
- **Runtime**: `org.gnome.Platform` (includes GTK 4 + PyGObject)
- **Rationale**: Bundles all Python/GTK dependencies, cross-distro, one-click install, Flathub-ready
- **Lock-in risk**: Low — Flatpak is open standard; deb/rpm packaging can be added later

## CI/CD
- **Pipeline**: GitHub Actions
  - On push: lint (flake8/ruff), run unit tests
  - On tag: build Flatpak bundle, create GitHub Release
- **Flatpak builder**: `flatpak-builder` action (official)

## Monitoring & Logging
- N/A — local desktop app, no telemetry or remote logging
- Debug logging to stderr only (controlled by `--verbose` flag)

## Deployment Strategy
- **Strategy**: Flatpak release via GitHub Releases + Flathub submission
- **Environments**: local dev (run from source) → GitHub Release (tagged Flatpak bundle) → Flathub (manual submission post-MVP)
