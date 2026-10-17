"""Tests for gws-employeeid command-line interface."""

from pathlib import Path
from unittest.mock import patch

import pytest

from gws_employeeid.cli import (
    _build_parser,
    _resolve_gam_defaults,
    main,
)
from gws_employeeid.gam import GamConfig


class TestCliParser:
    """Tests for CLI argument parsing."""

    def test_default_options(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.service_account_key is None
        assert args.admin_email is None
        assert args.domain is None
        assert args.start_id is None
        assert args.prefix == ""
        assert args.pad_width == 0
        assert args.exclude_suspended is False
        assert args.dry_run is False
        assert args.force is False
        assert args.csv_export is None
        assert args.verbose == 0

    def test_custom_options(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--service-account-key",
                "/path/to/key.json",
                "--admin-email",
                "admin@example.com",
                "--domain",
                "example.com",
                "--start-id",
                "1000",
                "--prefix",
                "EMP-",
                "--pad-width",
                "5",
                "--exclude-suspended",
                "--dry-run",
                "--force",
                "--csv-export",
                "/tmp/out.csv",
                "-vv",
            ]
        )
        assert args.service_account_key == Path("/path/to/key.json")
        assert args.admin_email == "admin@example.com"
        assert args.domain == "example.com"
        assert args.start_id == 1000
        assert args.prefix == "EMP-"
        assert args.pad_width == 5
        assert args.exclude_suspended is True
        assert args.dry_run is True
        assert args.force is True
        assert args.csv_export == Path("/tmp/out.csv")
        assert args.verbose == 2


class TestResolveGamDefaults:
    """Tests for resolving arguments from GAM configuration."""

    @patch("gws_employeeid.cli.discover_gam_config")
    def test_fills_in_gam_defaults(self, mock_discover) -> None:
        mock_discover.return_value = GamConfig(
            config_dir=Path("/home/user/.gam"),
            service_account_key=Path("/home/user/.gam/oauth2service.json"),
            admin_email="gam_admin@example.com",
            domain="gam_domain.com",
        )
        parser = _build_parser()
        args = parser.parse_args([])

        _resolve_gam_defaults(args)

        assert args.service_account_key == Path("/home/user/.gam/oauth2service.json")
        assert args.admin_email == "gam_admin@example.com"
        assert args.domain == "gam_domain.com"

    @patch("gws_employeeid.cli.discover_gam_config")
    def test_cli_args_override_gam(self, mock_discover) -> None:
        mock_discover.return_value = GamConfig(
            config_dir=Path("/home/user/.gam"),
            service_account_key=Path("/home/user/.gam/oauth2service.json"),
            admin_email="gam_admin@example.com",
            domain="gam_domain.com",
        )
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--admin-email",
                "override@example.com",
            ]
        )

        _resolve_gam_defaults(args)

        assert args.admin_email == "override@example.com"
        assert args.domain == "gam_domain.com"

    @patch("gws_employeeid.cli.discover_gam_config")
    def test_exits_when_missing_and_no_gam(self, mock_discover) -> None:
        mock_discover.return_value = None
        parser = _build_parser()
        args = parser.parse_args([])

        with pytest.raises(SystemExit) as exc_info:
            _resolve_gam_defaults(args)
        assert exc_info.value.code == 2


class TestMain:
    """Tests for CLI main entry point."""

    @patch("gws_employeeid.main.run")
    @patch("gws_employeeid.cli.discover_gam_config")
    def test_main_successful_dry_run(self, mock_discover, mock_run, capsys) -> None:
        mock_discover.return_value = GamConfig(
            config_dir=Path("/fake"),
            service_account_key=Path("/fake/oauth2service.json"),
            admin_email="admin@example.com",
            domain="example.com",
        )
        mock_run.return_value = {
            "alice@example.com": "dry_run",
            "bob@example.com": "skipped_existing",
        }

        main(["--dry-run"])

        captured = capsys.readouterr()
        assert "Dry Run Summary for 2 evaluated user(s):" in captured.out
        assert "Would assign:        1" in captured.out
        assert "Skipped (existing):  1" in captured.out

    @patch("gws_employeeid.main.run")
    @patch("gws_employeeid.cli.discover_gam_config")
    def test_main_exits_1_on_failure(self, mock_discover, mock_run) -> None:
        mock_discover.return_value = GamConfig(
            config_dir=Path("/fake"),
            service_account_key=Path("/fake/oauth2service.json"),
            admin_email="admin@example.com",
            domain="example.com",
        )
        mock_run.return_value = {"alice@example.com": "failed"}

        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 1

    @patch("gws_employeeid.main.run")
    @patch("gws_employeeid.cli.discover_gam_config")
    def test_main_no_users(self, mock_discover, mock_run, capsys) -> None:
        mock_discover.return_value = GamConfig(
            config_dir=Path("/fake"),
            service_account_key=Path("/fake/oauth2service.json"),
            admin_email="admin@example.com",
            domain="example.com",
        )
        mock_run.return_value = {}

        main([])

        captured = capsys.readouterr()
        assert "No users found to process." in captured.out
