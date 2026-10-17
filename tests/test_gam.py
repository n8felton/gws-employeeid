"""Tests for GAM7 credential auto-detection."""

from pathlib import Path

import pytest

from gws_employeeid.gam import (
    _parse_gam_cfg,
    _strip_gam_value,
    discover_gam_config,
    find_service_account_key,
    get_gam_config_dir,
)


class TestGetGamConfigDir:
    """Tests for locating the GAM config directory."""

    def test_uses_gamcfgdir_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GAMCFGDIR", str(tmp_path))
        assert get_gam_config_dir() == tmp_path

    def test_ignores_nonexistent_gamcfgdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = tmp_path / "nonexistent"
        monkeypatch.setenv("GAMCFGDIR", str(fake))
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert get_gam_config_dir() is None

    def test_falls_back_to_home_dot_gam(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GAMCFGDIR", raising=False)
        gam_dir = tmp_path / ".gam"
        gam_dir.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert get_gam_config_dir() == gam_dir

    def test_returns_none_when_no_gam(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GAMCFGDIR", raising=False)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert get_gam_config_dir() is None


class TestFindServiceAccountKey:
    """Tests for finding oauth2service.json."""

    def test_finds_key_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "oauth2service.json"
        key_file.write_text("{}")
        assert find_service_account_key(tmp_path) == key_file

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert find_service_account_key(tmp_path) is None


class TestStripGamValue:
    """Tests for stripping GAM7 quoted placeholders."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("''", ""),
            ('""', ""),
            ("'admin@example.com'", "admin@example.com"),
            ('"example.com"', "example.com"),
            ("plain_value", "plain_value"),
            ("", ""),
            ("  'spaced'  ", "spaced"),
        ],
    )
    def test_strip_quotes(self, raw: str, expected: str) -> None:
        assert _strip_gam_value(raw) == expected


class TestParseGamCfg:
    """Tests for parsing gam.cfg."""

    def test_parses_valid_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "gam.cfg"
        cfg.write_text(
            "[DEFAULT]\nadmin_email = admin@example.com\ndomain = example.com\n"
        )
        result = _parse_gam_cfg(tmp_path)
        assert result == {
            "admin_email": "admin@example.com",
            "domain": "example.com",
        }

    def test_handles_empty_quoted_values(self, tmp_path: Path) -> None:
        cfg = tmp_path / "gam.cfg"
        cfg.write_text("[DEFAULT]\nadmin_email = ''\ndomain = ''\n")
        result = _parse_gam_cfg(tmp_path)
        assert result == {}

    def test_returns_empty_when_no_gam_cfg(self, tmp_path: Path) -> None:
        assert _parse_gam_cfg(tmp_path) == {}


class TestDiscoverGamConfig:
    """Tests for overall GAM7 auto-discovery."""

    def test_complete_discovery(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GAMCFGDIR", str(tmp_path))
        key = tmp_path / "oauth2service.json"
        key.write_text("{}")
        cfg = tmp_path / "gam.cfg"
        cfg.write_text(
            "[DEFAULT]\nadmin_email = admin@example.com\ndomain = example.com\n"
        )

        config = discover_gam_config()
        assert config is not None
        assert config.config_dir == tmp_path
        assert config.service_account_key == key
        assert config.admin_email == "admin@example.com"
        assert config.domain == "example.com"

    def test_returns_none_when_no_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GAMCFGDIR", str(tmp_path))
        assert discover_gam_config() is None

    def test_returns_none_when_no_gam_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GAMCFGDIR", raising=False)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert discover_gam_config() is None
