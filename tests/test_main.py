"""Tests for main pipeline orchestration."""

import csv
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from gws_employeeid.assigner import AssignmentItem
from gws_employeeid.main import export_plan_to_csv, process_users, run
from gws_employeeid.models.config import AssignmentConfig
from gws_employeeid.models.user import WorkspaceUser


def _make_user(
    email: str,
    emp_id: str | None = None,
    created_iso: str | None = "2022-01-01T00:00:00Z",
    suspended: bool = False,
) -> WorkspaceUser:
    dt = (
        datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
        if created_iso
        else None
    )
    return WorkspaceUser(
        primary_email=email,
        full_name=email.split("@")[0].title(),
        creation_time=dt,
        employee_id=emp_id,
        suspended=suspended,
    )


class TestExportPlanToCsv:
    """Tests for CSV exporting."""

    def test_exports_valid_csv(self, tmp_path: Path) -> None:
        user = _make_user("ada@example.com", emp_id=None)
        item = AssignmentItem(
            user=user,
            old_employee_id=None,
            new_employee_id="101",
            action="assign",
            reason="Assigned based on creation date",
        )
        outcomes = {"ada@example.com": "assigned"}
        csv_file = tmp_path / "reports" / "output.csv"

        export_plan_to_csv([item], outcomes, csv_file)

        assert csv_file.is_file()
        with csv_file.open("r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            assert len(reader) == 2  # header + 1 row
            assert reader[0][0] == "primary_email"
            assert reader[1][0] == "ada@example.com"
            assert reader[1][4] == "101"
            assert reader[1][6] == "assigned"


class TestProcessUsers:
    """Tests for user processing pipeline."""

    def test_dry_run_does_not_call_update(self) -> None:
        client = MagicMock()
        users = [_make_user("ada@example.com")]
        config = AssignmentConfig(dry_run=True, start_id=1)

        outcomes = process_users(client, users, config)
        assert outcomes == {"ada@example.com": "dry_run"}
        client.update_user_employee_id.assert_not_called()

    def test_live_assignment_updates_user(self) -> None:
        client = MagicMock()
        users = [_make_user("ada@example.com")]
        config = AssignmentConfig(dry_run=False, start_id=10)

        outcomes = process_users(client, users, config)
        assert outcomes == {"ada@example.com": "assigned"}
        client.update_user_employee_id.assert_called_once_with(
            email="ada@example.com",
            employee_id="10",
            existing_external_ids=(),
        )

    def test_existing_ids_skipped_without_force(self) -> None:
        client = MagicMock()
        users = [_make_user("ada@example.com", emp_id="EMP-99")]
        config = AssignmentConfig(force=False)

        outcomes = process_users(client, users, config)
        assert outcomes == {"ada@example.com": "skipped_existing"}
        client.update_user_employee_id.assert_not_called()

    def test_handles_update_failure(self) -> None:
        client = MagicMock()
        client.update_user_employee_id.side_effect = RuntimeError("API error")
        users = [_make_user("ada@example.com")]
        config = AssignmentConfig(dry_run=False, start_id=1)

        outcomes = process_users(client, users, config)
        assert outcomes == {"ada@example.com": "failed"}

    def test_skipping_log_aligns_email_padding(self, caplog) -> None:
        client = MagicMock()
        users = [
            _make_user("short@test.com", emp_id="1"),
            _make_user("longer_email_address@test.com", emp_id="2"),
        ]
        config = AssignmentConfig(force=False)
        with caplog.at_level("INFO"):
            process_users(client, users, config)

        max_len = len("longer_email_address@test.com")
        expected_short_padded = "short@test.com".ljust(max_len)
        assert (
            f"Skipping {expected_short_padded} — already has Employee ID '1'"
            in caplog.text
        )
        assert (
            "Skipping longer_email_address@test.com — already has Employee ID '2'"
            in caplog.text
        )


class TestRun:
    """Tests for top-level run() function."""

    @patch("gws_employeeid.main.GoogleAdminClient")
    def test_run_orchestrates_flow(self, mock_client_cls) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.list_users.return_value = [_make_user("ada@example.com")]

        config = AssignmentConfig(dry_run=True, start_id=1)
        results = run(
            service_account_key=Path("/fake/key.json"),
            admin_email="admin@example.com",
            domain="example.com",
            config=config,
        )

        mock_client_cls.assert_called_once_with(
            Path("/fake/key.json"), "admin@example.com"
        )
        mock_client.list_users.assert_called_once_with(
            domain="example.com",
            org_unit_path=None,
            user_emails=None,
        )
        assert results == {"ada@example.com": "dry_run"}

    @patch("gws_employeeid.main.GoogleAdminClient")
    def test_run_empty_users(self, mock_client_cls) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.list_users.return_value = []

        results = run(
            service_account_key=Path("/fake/key.json"),
            admin_email="admin@example.com",
            domain="example.com",
            config=AssignmentConfig(),
        )
        assert results == {}
