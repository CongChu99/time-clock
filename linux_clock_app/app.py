"""Linux Clock App - GTK4 Application"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gio, Gtk

from linux_clock_app import config_manager
from linux_clock_app.clock_window import ClockWindow


class ClockApp(Gtk.Application):
    """Main GTK4 Application for Linux Clock App.

    Single-instance application enforced via application_id.
    """

    def __init__(self, **kwargs):
        super().__init__(
            application_id="io.github.user.LinuxClockApp",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
            **kwargs,
        )

    def do_activate(self):
        """Called when the application is activated (including D-Bus re-activation)."""
        existing = self.get_windows()
        if existing:
            existing[0].present()
            return
        config = config_manager.load()
        win = ClockWindow(app=self, config=config)
        win.present()
