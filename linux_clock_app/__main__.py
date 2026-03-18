"""Entry point for Linux Clock App."""

import sys

from linux_clock_app.app import ClockApp


def main():
    """Run the application."""
    app = ClockApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
