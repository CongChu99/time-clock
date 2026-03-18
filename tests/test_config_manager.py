"""Tests for ConfigManager and ClockConfig — TDD first pass."""
import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_config(config_dir: Path):
    """Return a context manager that redirects config_manager to *config_dir*."""
    config_file = config_dir / "config.json"
    return patch.multiple(
        "linux_clock_app.config_manager",
        CONFIG_DIR=config_dir,
        CONFIG_FILE=config_file,
    )


# ---------------------------------------------------------------------------
# ClockConfig model tests
# ---------------------------------------------------------------------------

class TestClockConfig:
    def test_defaults(self):
        from linux_clock_app.models import ClockConfig
        cfg = ClockConfig()
        assert cfg.pos_x == -1
        assert cfg.pos_y == -1
        assert cfg.always_on_top is False
        assert cfg.use_24h is True
        assert cfg.show_seconds is False
        assert cfg.show_date is True
        assert cfg.font_family == "Sans"
        assert cfg.font_size == 36
        assert cfg.text_color == "#FFFFFF"
        assert cfg.bg_color == "#000000"
        assert cfg.bg_opacity == 0.7

    def test_to_dict_has_all_keys(self):
        from linux_clock_app.models import ClockConfig
        d = ClockConfig().to_dict()
        expected_keys = {
            "pos_x", "pos_y", "always_on_top",
            "use_24h", "show_seconds", "show_date",
            "font_family", "font_size", "text_color", "bg_color", "bg_opacity",
            "show_lunar", "border_width", "border_color", "border_radius", "drag_shortcut",
        }
        assert set(d.keys()) == expected_keys

    def test_from_dict_roundtrip(self):
        from linux_clock_app.models import ClockConfig
        original = ClockConfig(pos_x=500, pos_y=200, font_family="Monospace", bg_opacity=0.5)
        restored = ClockConfig.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_uses_defaults_for_missing_keys(self):
        from linux_clock_app.models import ClockConfig
        cfg = ClockConfig.from_dict({"pos_x": 999})
        assert cfg.pos_x == 999
        assert cfg.pos_y == -1  # default


# ---------------------------------------------------------------------------
# ConfigManager tests
# ---------------------------------------------------------------------------

class TestConfigManagerLoad:
    def test_load_returns_defaults_when_no_file(self, tmp_path):
        """load() returns ClockConfig defaults when config file is absent."""
        config_dir = tmp_path / "linux-clock-app"
        # config_dir intentionally NOT created

        import linux_clock_app.config_manager as cm
        from linux_clock_app.models import ClockConfig

        with _patch_config(config_dir):
            cfg = cm.load()

        assert cfg == ClockConfig()

    def test_load_creates_config_dir_if_missing(self, tmp_path):
        """load() auto-creates CONFIG_DIR when it does not exist."""
        config_dir = tmp_path / "linux-clock-app"
        assert not config_dir.exists()

        import linux_clock_app.config_manager as cm

        with _patch_config(config_dir):
            cm.load()

        assert config_dir.exists()

    def test_load_corrupt_returns_defaults_and_logs_warning(self, tmp_path, caplog):
        """load() returns defaults and logs a WARNING when JSON is corrupt."""
        config_dir = tmp_path / "linux-clock-app"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text("this is { not valid json!!!")

        import linux_clock_app.config_manager as cm
        from linux_clock_app.models import ClockConfig

        with _patch_config(config_dir):
            with caplog.at_level(logging.WARNING, logger="linux_clock_app.config_manager"):
                cfg = cm.load()

        assert cfg == ClockConfig()
        assert any(
            "corrupt" in r.message.lower() or "invalid" in r.message.lower()
            for r in caplog.records
        )

    def test_load_valid_file_returns_saved_values(self, tmp_path):
        """load() returns the values stored in a valid config.json."""
        config_dir = tmp_path / "linux-clock-app"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        data = {
            "pos_x": 1200, "pos_y": 50, "always_on_top": True,
            "use_24h": False, "show_seconds": True, "show_date": False,
            "font_family": "Monospace", "font_size": 24,
            "text_color": "#FF0000", "bg_color": "#0000FF", "bg_opacity": 0.9,
        }
        config_file.write_text(json.dumps(data))

        import linux_clock_app.config_manager as cm

        with _patch_config(config_dir):
            cfg = cm.load()

        assert cfg.pos_x == 1200
        assert cfg.always_on_top is True
        assert cfg.font_family == "Monospace"
        assert cfg.bg_opacity == 0.9


class TestConfigManagerSave:
    def test_save_then_load_roundtrip(self, tmp_path):
        """save() followed by load() preserves all fields."""
        config_dir = tmp_path / "linux-clock-app"

        from linux_clock_app.models import ClockConfig
        import linux_clock_app.config_manager as cm

        original = ClockConfig(
            pos_x=800, pos_y=600, always_on_top=True,
            use_24h=False, show_seconds=True, show_date=False,
            font_family="Monospace", font_size=48,
            text_color="#00FF00", bg_color="#111111", bg_opacity=0.3,
        )

        with _patch_config(config_dir):
            cm.save(original)
            restored = cm.load()

        assert restored == original

    def test_save_atomic_no_tmp_file_after_save(self, tmp_path):
        """After save(), the .tmp file must not exist (atomic replace was used)."""
        config_dir = tmp_path / "linux-clock-app"
        config_file = config_dir / "config.json"

        from linux_clock_app.models import ClockConfig
        import linux_clock_app.config_manager as cm

        with _patch_config(config_dir):
            cm.save(ClockConfig())

        tmp_file = config_file.with_suffix(".tmp")
        assert not tmp_file.exists(), ".tmp file should be cleaned up after atomic save"

    def test_save_creates_config_dir_if_missing(self, tmp_path):
        """save() auto-creates CONFIG_DIR when it does not exist."""
        config_dir = tmp_path / "linux-clock-app"
        assert not config_dir.exists()

        from linux_clock_app.models import ClockConfig
        import linux_clock_app.config_manager as cm

        with _patch_config(config_dir):
            cm.save(ClockConfig())

        assert config_dir.exists()
        config_file = config_dir / "config.json"
        assert config_file.exists()

    def test_save_writes_valid_json(self, tmp_path):
        """The file written by save() is valid JSON matching to_dict()."""
        config_dir = tmp_path / "linux-clock-app"
        config_file = config_dir / "config.json"

        from linux_clock_app.models import ClockConfig
        import linux_clock_app.config_manager as cm

        cfg = ClockConfig(pos_x=777, font_family="DejaVu Sans")

        with _patch_config(config_dir):
            cm.save(cfg)

        raw = json.loads(config_file.read_text())
        assert raw["pos_x"] == 777
        assert raw["font_family"] == "DejaVu Sans"
