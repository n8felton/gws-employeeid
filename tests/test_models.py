"""Tests for data and configuration models."""

from datetime import UTC, datetime

from gws_employeeid.models.config import AssignmentConfig
from gws_employeeid.models.user import (
    WorkspaceUser,
    extract_employee_id,
    parse_creation_time,
)


class TestParseCreationTime:
    """Tests for parsing Google Workspace creation times."""

    def test_parse_iso_with_z(self) -> None:
        raw = "2023-05-10T14:30:00.000Z"
        parsed = parse_creation_time(raw)
        assert parsed == datetime(2023, 5, 10, 14, 30, 0, tzinfo=UTC)

    def test_parse_iso_with_offset(self) -> None:
        raw = "2023-05-10T10:30:00-04:00"
        parsed = parse_creation_time(raw)
        assert parsed == datetime(2023, 5, 10, 14, 30, 0, tzinfo=UTC)

    def test_parse_none_or_empty(self) -> None:
        assert parse_creation_time(None) is None
        assert parse_creation_time("") is None
        assert parse_creation_time("   ") is None

    def test_parse_invalid_string(self) -> None:
        assert parse_creation_time("not-a-date") is None


class TestExtractEmployeeId:
    """Tests for extracting Employee ID from Google API externalIds list."""

    def test_extract_organization_type(self) -> None:
        ext_ids = [
            {"type": "account", "value": "acct123"},
            {"type": "organization", "value": "EMP-042"},
        ]
        assert extract_employee_id(ext_ids) == "EMP-042"

    def test_extract_none_when_empty_or_missing(self) -> None:
        assert extract_employee_id(None) is None
        assert extract_employee_id([]) is None
        assert extract_employee_id([{"type": "account", "value": "123"}]) is None

    def test_extract_skips_empty_values(self) -> None:
        ext_ids = [
            {"type": "organization", "value": ""},
            {"type": "organization", "value": "   "},
        ]
        assert extract_employee_id(ext_ids) is None


class TestWorkspaceUser:
    """Tests for WorkspaceUser properties."""

    def test_has_employee_id(self) -> None:
        user_with_id = WorkspaceUser(
            primary_email="alice@example.com",
            full_name="Alice Adams",
            employee_id="1001",
        )
        assert user_with_id.has_employee_id is True

        user_without_id = WorkspaceUser(
            primary_email="bob@example.com",
            full_name="Bob Brown",
            employee_id=None,
        )
        assert user_without_id.has_employee_id is False

        user_with_empty_id = WorkspaceUser(
            primary_email="carol@example.com",
            full_name="Carol Clark",
            employee_id="  ",
        )
        assert user_with_empty_id.has_employee_id is False


class TestAssignmentConfig:
    """Tests for ID formatting and config options."""

    def test_format_id_plain(self) -> None:
        cfg = AssignmentConfig()
        assert cfg.format_id(42) == "42"

    def test_format_id_with_prefix(self) -> None:
        cfg = AssignmentConfig(prefix="EMP-")
        assert cfg.format_id(42) == "EMP-42"

    def test_format_id_with_padding(self) -> None:
        cfg = AssignmentConfig(pad_width=4)
        assert cfg.format_id(42) == "0042"
        assert cfg.format_id(12345) == "12345"

    def test_format_id_prefix_and_padding(self) -> None:
        cfg = AssignmentConfig(prefix="ID-", pad_width=5)
        assert cfg.format_id(7) == "ID-00007"
