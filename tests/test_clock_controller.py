"""Tests for ClockController formatting logic.

GLib timer functions (start/stop) are NOT tested here because they require a
running GLib MainLoop which is unavailable in a headless CI environment.
Instead we test get_formatted_time() and get_formatted_date() by mocking
datetime.datetime.now().
"""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from linux_clock_app.clock_controller import ClockController
from linux_clock_app.models import ClockConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def controller() -> ClockController:
    """A ClockController with a no-op on_tick callback."""
    return ClockController(on_tick=MagicMock())


def _fake_now(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    """Build a fixed datetime for 2026-03-17 at the given time."""
    return datetime.datetime(2026, 3, 17, hour, minute, second)


def _patch_now(dt: datetime.datetime):
    """Return a context manager that fixes datetime.datetime.now() to *dt*
    without replacing the datetime class itself (so strftime still works)."""
    return patch(
        "linux_clock_app.clock_controller.datetime.datetime",
        wraps=datetime.datetime,
        **{"now.return_value": dt},
    )


# ---------------------------------------------------------------------------
# get_formatted_time — 24h mode
# ---------------------------------------------------------------------------

class TestFormattedTime24h:
    def test_24h_without_seconds(self, controller: ClockController):
        config = ClockConfig(use_24h=True, show_seconds=False)
        with _patch_now(_fake_now(14, 30, 0)):
            result = controller.get_formatted_time(config)
        assert result == "14:30"

    def test_24h_with_seconds(self, controller: ClockController):
        config = ClockConfig(use_24h=True, show_seconds=True)
        with _patch_now(_fake_now(14, 30, 25)):
            result = controller.get_formatted_time(config)
        assert result == "14:30:25"

    def test_24h_midnight(self, controller: ClockController):
        """Hour 0 must render as '00', not '12'."""
        config = ClockConfig(use_24h=True, show_seconds=False)
        with _patch_now(_fake_now(0, 5)):
            result = controller.get_formatted_time(config)
        assert result == "00:05"


# ---------------------------------------------------------------------------
# get_formatted_time — 12h mode
# ---------------------------------------------------------------------------

class TestFormattedTime12h:
    def test_12h_am_without_seconds(self, controller: ClockController):
        config = ClockConfig(use_24h=False, show_seconds=False)
        with _patch_now(_fake_now(9, 5)):
            result = controller.get_formatted_time(config)
        assert result == "9:05 AM"

    def test_12h_pm_without_seconds(self, controller: ClockController):
        config = ClockConfig(use_24h=False, show_seconds=False)
        with _patch_now(_fake_now(14, 30)):
            result = controller.get_formatted_time(config)
        assert result == "2:30 PM"

    def test_12h_pm_with_seconds(self, controller: ClockController):
        config = ClockConfig(use_24h=False, show_seconds=True)
        with _patch_now(_fake_now(14, 30, 25)):
            result = controller.get_formatted_time(config)
        assert result == "2:30:25 PM"

    def test_12h_noon(self, controller: ClockController):
        """Noon (12:00) must render as '12:00 PM', not '0:00 PM'."""
        config = ClockConfig(use_24h=False, show_seconds=False)
        with _patch_now(_fake_now(12, 0)):
            result = controller.get_formatted_time(config)
        assert result == "12:00 PM"

    def test_12h_midnight(self, controller: ClockController):
        """Midnight (0:00) must render as '12:00 AM'."""
        config = ClockConfig(use_24h=False, show_seconds=False)
        with _patch_now(_fake_now(0, 0)):
            result = controller.get_formatted_time(config)
        assert result == "12:00 AM"


# ---------------------------------------------------------------------------
# get_formatted_date
# ---------------------------------------------------------------------------

class TestFormattedDate:
    def test_show_date_true_returns_formatted_string(self, controller: ClockController):
        config = ClockConfig(show_date=True)
        with _patch_now(datetime.datetime(2026, 3, 17, 14, 30, 0)):
            result = controller.get_formatted_date(config)
        assert result == "Tue, 17 Mar 2026"

    def test_show_date_false_returns_empty_string(self, controller: ClockController):
        config = ClockConfig(show_date=False)
        result = controller.get_formatted_date(config)
        assert result == ""

    def test_show_date_single_digit_day_has_no_leading_zero(self, controller: ClockController):
        """Day '5' must appear as '5', not '05'."""
        config = ClockConfig(show_date=True)
        with _patch_now(datetime.datetime(2026, 3, 5, 10, 0, 0)):
            result = controller.get_formatted_date(config)
        assert result == "Thu, 5 Mar 2026"


# ---------------------------------------------------------------------------
# Timer management (mocked GLib)
# ---------------------------------------------------------------------------

class TestTimerManagement:
    def test_start_calls_schedule_and_stores_timer_id(self):
        """start() must schedule a GLib timer and store its source id."""
        on_tick = MagicMock()
        ctrl = ClockController(on_tick=on_tick)
        config = ClockConfig(show_seconds=False)

        with patch("linux_clock_app.clock_controller.GLib") as mock_glib:
            mock_glib.timeout_add.return_value = 42
            ctrl.start(config)

        assert ctrl._timer_id == 42
        mock_glib.timeout_add.assert_called_once_with(60_000, ctrl._tick)

    def test_start_with_seconds_uses_timeout_add_seconds(self):
        """start() with show_seconds=True must use timeout_add_seconds(1, …)."""
        ctrl = ClockController(on_tick=MagicMock())
        config = ClockConfig(show_seconds=True)

        with patch("linux_clock_app.clock_controller.GLib") as mock_glib:
            mock_glib.timeout_add_seconds.return_value = 99
            ctrl.start(config)

        assert ctrl._timer_id == 99
        mock_glib.timeout_add_seconds.assert_called_once_with(1, ctrl._tick)

    def test_start_cancels_existing_timer_before_scheduling(self):
        """start() must cancel any running timer first (no duplicate timers)."""
        ctrl = ClockController(on_tick=MagicMock())
        ctrl._timer_id = 7  # simulate an already-running timer

        with patch("linux_clock_app.clock_controller.GLib") as mock_glib:
            mock_glib.timeout_add.return_value = 8
            ctrl.start(ClockConfig(show_seconds=False))

        mock_glib.source_remove.assert_called_once_with(7)

    def test_stop_removes_source_and_clears_timer_id(self):
        """stop() must call GLib.source_remove and set _timer_id to None."""
        ctrl = ClockController(on_tick=MagicMock())
        ctrl._timer_id = 55

        with patch("linux_clock_app.clock_controller.GLib") as mock_glib:
            ctrl.stop()

        mock_glib.source_remove.assert_called_once_with(55)
        assert ctrl._timer_id is None

    def test_stop_is_noop_when_no_timer_running(self):
        """stop() must not raise when _timer_id is None."""
        ctrl = ClockController(on_tick=MagicMock())
        with patch("linux_clock_app.clock_controller.GLib") as mock_glib:
            ctrl.stop()  # should not raise
        mock_glib.source_remove.assert_not_called()

    def test_tick_calls_on_tick_and_returns_true(self):
        """_tick() must call on_tick and return True (GLib keep-alive)."""
        on_tick = MagicMock()
        ctrl = ClockController(on_tick=on_tick)
        result = ctrl._tick()
        on_tick.assert_called_once()
        assert result is True

    def test_update_config_restarts_timer(self):
        """update_config() must cancel old timer and start a new one."""
        ctrl = ClockController(on_tick=MagicMock())
        ctrl._timer_id = 10

        with patch("linux_clock_app.clock_controller.GLib") as mock_glib:
            mock_glib.timeout_add.return_value = 20
            ctrl.update_config(ClockConfig(show_seconds=False))

        mock_glib.source_remove.assert_called_once_with(10)
        assert ctrl._timer_id == 20
