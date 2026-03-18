"""ClockController — time formatting and GLib-driven timer."""
from __future__ import annotations

import datetime
from typing import Callable, Optional

from gi.repository import GLib

from linux_clock_app.models import ClockConfig


class ClockController:
    """Drives a repeating clock tick and formats time/date strings.

    Parameters
    ----------
    on_tick:
        Callable invoked on every timer tick (no arguments).  The caller is
        responsible for refreshing any UI elements inside this callback.
    """

    def __init__(self, on_tick: Callable[[], None]) -> None:
        self._on_tick = on_tick
        self._timer_id: Optional[int] = None

    # ------------------------------------------------------------------
    # Timer control
    # ------------------------------------------------------------------

    def start(self, config: ClockConfig) -> None:
        """Start the repeating timer according to *config*.

        If a timer is already running it is cancelled first so there is never
        more than one active timer.
        """
        self.stop()
        self._timer_id = self._schedule(config)

    def stop(self) -> None:
        """Cancel the running timer, if any."""
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def update_config(self, config: ClockConfig) -> None:
        """Change the timer interval without losing the on_tick callback.

        Cancels the old timer and starts a new one with the updated *config*.
        """
        self.start(config)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def get_formatted_time(self, config: ClockConfig) -> str:
        """Return the current local time as a human-readable string.

        Formats:
        - 24h without seconds: ``"14:30"``
        - 24h with seconds:    ``"14:30:25"``
        - 12h without seconds: ``"2:30 PM"``
        - 12h with seconds:    ``"2:30:25 PM"``
        """
        now = datetime.datetime.now()
        if config.use_24h:
            fmt = "%H:%M:%S" if config.show_seconds else "%H:%M"
        else:
            # %-I strips the leading zero on POSIX/Linux.
            fmt = "%-I:%M:%S %p" if config.show_seconds else "%-I:%M %p"
        try:
            return now.strftime(fmt)
        except ValueError:
            # Fallback for non-POSIX platforms (macOS, Windows) that don't support %-I/%-d
            fmt_fallback = "%I:%M:%S %p" if config.show_seconds else "%I:%M %p"
            return now.strftime(fmt_fallback).lstrip("0") or "0"

    def get_formatted_date(self, config: ClockConfig) -> str:
        """Return the current local date as a human-readable string, or ``""``
        when *config.show_date* is ``False``.

        Example return value: ``"Mon, 17 Mar 2026"``
        """
        if not config.show_date:
            return ""
        now = datetime.datetime.now()
        try:
            return now.strftime("%a, %-d %b %Y")
        except ValueError:
            # Fallback for non-POSIX platforms
            return now.strftime("%a, %d %b %Y").replace(" 0", " ")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _tick(self) -> bool:
        """Internal GLib timer callback.  Calls on_tick and returns True so
        GLib keeps the timer alive."""
        self._on_tick()
        return True  # Must return True to continue repeating.

    def _schedule(self, config: ClockConfig) -> int:
        """Register the appropriate GLib timer and return its source id."""
        if config.show_seconds:
            return GLib.timeout_add_seconds(1, self._tick)
        else:
            return GLib.timeout_add(60_000, self._tick)
