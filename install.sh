#!/usr/bin/env bash
# Linux Clock App — Installer
# Usage:
#   ./install.sh           Install and autostart
#   ./install.sh --uninstall  Remove everything

set -e

APP_ID="io.github.user.LinuxClockApp"
APP_NAME="linux-clock-app"
INSTALL_DIR="$HOME/.local/lib/linux-clock-app"
BIN_DIR="$HOME/.local/bin"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/$APP_ID.desktop"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/$APP_NAME.service"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DATA_DIR="$HOME/.local/share/applications"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }
section() { echo -e "\n${BOLD}$*${NC}"; }

# ─────────────────────────────────────────
# UNINSTALL
# ─────────────────────────────────────────
uninstall() {
    section "Uninstalling Linux Clock App..."

    # Stop and disable systemd service if present
    if systemctl --user is-active --quiet "$APP_NAME" 2>/dev/null; then
        systemctl --user stop "$APP_NAME"
        info "Stopped background service"
    fi
    if systemctl --user is-enabled --quiet "$APP_NAME" 2>/dev/null; then
        systemctl --user disable "$APP_NAME"
        info "Disabled autostart service"
    fi

    # Kill any running process
    pkill -f "linux_clock_app" 2>/dev/null && info "Killed running process" || true

    # Remove files
    rm -f  "$SERVICE_FILE"
    rm -f  "$DESKTOP_FILE"
    rm -f  "$BIN_DIR/$APP_NAME"
    rm -f  "$ICON_DIR/$APP_ID.svg"
    rm -f  "$DATA_DIR/$APP_ID.desktop"
    rm -rf "$INSTALL_DIR"

    # Reload systemd
    systemctl --user daemon-reload 2>/dev/null || true
    # Refresh desktop database
    update-desktop-database "$DATA_DIR" 2>/dev/null || true

    echo ""
    info "Linux Clock App has been completely removed."
    echo "  Config/settings kept at: ~/.config/linux-clock-app/"
    echo "  To also remove settings: rm -rf ~/.config/linux-clock-app/"
}

# ─────────────────────────────────────────
# INSTALL
# ─────────────────────────────────────────
install() {
    section "Installing Linux Clock App..."

    # 1. Check Python + GTK4
    python3 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk" 2>/dev/null \
        || error "GTK4 + PyGObject not found. Install with:\n  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0"
    info "GTK4 + PyGObject found"

    # 2. Copy app files to install dir
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    mkdir -p "$INSTALL_DIR"
    cp -r "$SCRIPT_DIR/linux_clock_app" "$INSTALL_DIR/"
    info "App files copied to $INSTALL_DIR"

    # 3. Create launcher script in ~/.local/bin
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/$APP_NAME" << EOF
#!/usr/bin/env bash
# Linux Clock App launcher
export PYTHONPATH="$INSTALL_DIR:\$PYTHONPATH"
exec python3 -m linux_clock_app "\$@"
EOF
    chmod +x "$BIN_DIR/$APP_NAME"
    info "Launcher created: $BIN_DIR/$APP_NAME"

    # Ensure ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        warn "$BIN_DIR is not in PATH. Add this to ~/.bashrc or ~/.profile:"
        warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi

    # 4. Install icon
    mkdir -p "$ICON_DIR"
    if [ -f "$SCRIPT_DIR/data/icons/$APP_ID.svg" ]; then
        cp "$SCRIPT_DIR/data/icons/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"
        info "Icon installed"
    fi

    # 5. Install .desktop file for app launcher
    mkdir -p "$DATA_DIR"
    cat > "$DATA_DIR/$APP_ID.desktop" << EOF
[Desktop Entry]
Name=Linux Clock App
Comment=A lightweight floating desktop clock widget for Linux
Exec=$BIN_DIR/$APP_NAME
Icon=$APP_ID
Terminal=false
Type=Application
Categories=Utility;Clock;
StartupNotify=false
EOF
    update-desktop-database "$DATA_DIR" 2>/dev/null || true
    info "App launcher registered"

    # 6. Create systemd user service (autostart + background)
    mkdir -p "$SERVICE_DIR"
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Linux Clock App — floating desktop clock
Documentation=https://github.com/user/linux-clock-app
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$BIN_DIR/$APP_NAME
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0
Environment=PYTHONPATH=$INSTALL_DIR

[Install]
WantedBy=graphical-session.target
EOF
    info "Systemd user service created"

    # 7. Create a display-aware wrapper script
    WRAPPER="$BIN_DIR/${APP_NAME}-session"
    cat > "$WRAPPER" << 'WRAPPER_EOF'
#!/usr/bin/env bash
# Detect active X11/Wayland display before launching GTK app

# Try to inherit from current environment first
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    # Look for an active X11 display via /tmp/.X11-unix
    for sock in /tmp/.X11-unix/X*; do
        num="${sock##*X}"
        DISPLAY=":${num}"
        export DISPLAY
        break
    done
fi

# Export for GTK
export DISPLAY
export WAYLAND_DISPLAY
export DBUS_SESSION_BUS_ADDRESS

exec /home/REPLACED_HOME/.local/bin/linux-clock-app "$@"
WRAPPER_EOF
    # Replace placeholder with real home
    sed -i "s|REPLACED_HOME|$(basename "$HOME")|g" "$WRAPPER"
    sed -i "s|/home/$(basename "$HOME")|$HOME|g" "$WRAPPER"
    chmod +x "$WRAPPER"
    info "Display-aware wrapper created"

    # 8. Update systemd service to use wrapper + propagate environment
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Linux Clock App — floating desktop clock
Documentation=https://github.com/user/linux-clock-app
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$WRAPPER
Restart=on-failure
RestartSec=5
PassEnvironment=DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR

[Install]
WantedBy=graphical-session.target
EOF
    info "Systemd user service updated with display support"

    # Propagate current display environment to systemd user manager
    if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
        systemctl --user import-environment DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS 2>/dev/null || true
    fi

    systemctl --user daemon-reload
    systemctl --user enable "$APP_NAME" 2>/dev/null && info "Autostart enabled (runs on login)" || \
        warn "Could not enable systemd service — falling back to XDG autostart"

    # XDG autostart (runs in graphical session — most reliable for desktop apps)
    mkdir -p "$AUTOSTART_DIR"
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=Linux Clock App
Comment=Autostart — Linux Clock App
Exec=$BIN_DIR/$APP_NAME
Icon=$APP_ID
Terminal=false
Type=Application
Hidden=false
X-GNOME-Autostart-enabled=true
EOF
    info "XDG autostart entry created (runs on every login)"

    # 9. Start now
    if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
        nohup "$BIN_DIR/$APP_NAME" > /tmp/linux-clock-app.log 2>&1 & disown
        info "App started in background (log: /tmp/linux-clock-app.log)"
    else
        warn "No display detected — app will start on next login"
    fi

    # ─── Summary ───
    echo ""
    echo -e "${BOLD}╔═══════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║   Linux Clock App installed successfully!     ║${NC}"
    echo -e "${BOLD}╠═══════════════════════════════════════════════╣${NC}"
    echo -e "${BOLD}║${NC} Run now:     ${GREEN}linux-clock-app${NC}"
    echo -e "${BOLD}║${NC} Stop:        ${YELLOW}systemctl --user stop linux-clock-app${NC}"
    echo -e "${BOLD}║${NC} Start:       ${YELLOW}systemctl --user start linux-clock-app${NC}"
    echo -e "${BOLD}║${NC} Status:      ${YELLOW}systemctl --user status linux-clock-app${NC}"
    echo -e "${BOLD}║${NC} Uninstall:   ${RED}./install.sh --uninstall${NC}"
    echo -e "${BOLD}╚═══════════════════════════════════════════════╝${NC}"
    echo ""
    info "App will auto-start on every login."
}

# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────
case "${1:-}" in
    --uninstall|-u|uninstall)
        uninstall
        ;;
    --help|-h)
        echo "Usage: $0 [--uninstall]"
        echo "  (no args)     Install and autostart Linux Clock App"
        echo "  --uninstall   Remove app, service, and autostart entries"
        ;;
    *)
        install
        ;;
esac
