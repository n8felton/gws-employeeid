"""Tests for Google Workspace Admin SDK Directory API client."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from gws_employeeid.google_admin import GoogleAdminClient


@pytest.fixture
def mock_credentials():
    with patch(
        "gws_employeeid.google_admin.service_account.Credentials.from_service_account_file"
    ) as mock_creds:
        mock_delegated = MagicMock()
        mock_creds.return_value.with_subject.return_value = mock_delegated
        yield mock_creds


@pytest.fixture
def mock_build():
    with patch("gws_employeeid.google_admin.build") as mock_b:
        yield mock_b


@pytest.fixture
def client(mock_credentials, mock_build) -> GoogleAdminClient:
    return GoogleAdminClient(
        service_account_key_path=Path("/fake/key.json"),
        admin_email="admin@example.com",
    )


class TestClientInit:
    """Tests for client initialization."""

    def test_delegates_admin_subject(self, mock_credentials, mock_build) -> None:
        GoogleAdminClient(
            service_account_key_path=Path("/fake/key.json"),
            admin_email="superadmin@example.com",
        )
        mock_credentials.assert_called_once_with(
            "/fake/key.json",
            scopes=[
                "https://www.googleapis.com/auth/admin.directory.user",
                "https://www.googleapis.com/auth/admin.directory.user.readonly",
            ],
        )
        mock_credentials.return_value.with_subject.assert_called_once_with(
            "superadmin@example.com"
        )
        mock_build.assert_called_once_with(
            "admin",
            "directory_v1",
            credentials=mock_credentials.return_value.with_subject.return_value,
        )


class TestParseUser:
    """Tests for parsing Google API user entries into WorkspaceUser objects."""

    def test_parse_complete_user(self, client: GoogleAdminClient) -> None:
        entry = {
            "primaryEmail": "ada@example.com",
            "name": {
                "fullName": "Ada Lovelace",
                "givenName": "Ada",
                "familyName": "Lovelace",
            },
            "creationTime": "2021-04-12T14:32:00.000Z",
            "externalIds": [
                {"type": "account", "value": "ada-sys"},
                {"type": "organization", "value": "1001"},
            ],
            "orgUnitPath": "/Engineering",
            "suspended": False,
        }
        user = client._parse_user(entry)
        assert user.primary_email == "ada@example.com"
        assert user.full_name == "Ada Lovelace"
        assert user.employee_id == "1001"
        assert user.org_unit_path == "/Engineering"
        assert user.suspended is False
        assert user.creation_time is not None
        assert user.creation_time.year == 2021

    def test_parse_minimal_user(self, client: GoogleAdminClient) -> None:
        entry = {
            "primaryEmail": "minimal@example.com",
        }
        user = client._parse_user(entry)
        assert user.primary_email == "minimal@example.com"
        assert user.full_name == ""
        assert user.employee_id is None
        assert user.creation_time is None
        assert user.org_unit_path == "/"
        assert user.suspended is False


class TestListUsers:
    """Tests for querying users."""

    def test_list_all_users_paginates(
        self, client: GoogleAdminClient, mock_build: MagicMock
    ) -> None:
        mock_service = mock_build.return_value
        mock_users = mock_service.users.return_value

        page1 = {
            "users": [
                {
                    "primaryEmail": "ada@example.com",
                    "creationTime": "2021-01-01T00:00:00Z",
                }
            ],
            "nextPageToken": "token123",
        }
        page2 = {
            "users": [
                {
                    "primaryEmail": "grace@example.com",
                    "creationTime": "2022-01-01T00:00:00Z",
                }
            ],
        }
        mock_users.list.return_value.execute.side_effect = [page1, page2]

        users = client.list_users(domain="example.com")
        assert len(users) == 2
        assert users[0].primary_email == "ada@example.com"
        assert users[1].primary_email == "grace@example.com"

    def test_list_all_users_with_org_unit(
        self, client: GoogleAdminClient, mock_build: MagicMock
    ) -> None:
        mock_service = mock_build.return_value
        mock_users = mock_service.users.return_value
        mock_users.list.return_value.execute.return_value = {"users": []}

        client.list_users(domain="example.com", org_unit_path="/Staff")
        mock_users.list.assert_called_once_with(
            domain="example.com",
            maxResults=500,
            projection="full",
            orderBy="email",
            query="orgUnitPath='/Staff'",
        )

    def test_get_specific_users(
        self, client: GoogleAdminClient, mock_build: MagicMock
    ) -> None:
        mock_service = mock_build.return_value
        mock_users = mock_service.users.return_value
        mock_users.get.return_value.execute.return_value = {
            "primaryEmail": "specific@example.com",
            "name": {"fullName": "Specific User"},
        }

        users = client.list_users(
            domain="example.com",
            user_emails=["specific@example.com"],
        )
        assert len(users) == 1
        assert users[0].primary_email == "specific@example.com"

    def test_get_specific_users_handles_error(
        self, client: GoogleAdminClient, mock_build: MagicMock
    ) -> None:
        mock_service = mock_build.return_value
        mock_users = mock_service.users.return_value
        mock_resp = MagicMock(status=404)
        mock_users.get.return_value.execute.side_effect = HttpError(
            resp=mock_resp, content=b"Not found"
        )

        users = client.list_users(
            domain="example.com",
            user_emails=["missing@example.com"],
        )
        assert len(users) == 0


class TestUpdateUserEmployeeId:
    """Tests for patching user Employee ID."""

    def test_updates_external_ids_preserving_others(
        self, client: GoogleAdminClient, mock_build: MagicMock
    ) -> None:
        mock_service = mock_build.return_value
        mock_users = mock_service.users.return_value

        existing_ext_ids = (
            {"type": "account", "value": "old_account"},
            {"type": "organization", "value": "old_emp_id"},
            {"type": "custom", "value": "custom_val"},
        )

        client.update_user_employee_id(
            email="ada@example.com",
            employee_id="2001",
            existing_external_ids=existing_ext_ids,
        )

        mock_users.patch.assert_called_once_with(
            userKey="ada@example.com",
            body={
                "externalIds": [
                    {"type": "account", "value": "old_account"},
                    {"type": "custom", "value": "custom_val"},
                    {"type": "organization", "value": "2001"},
                ]
            },
        )
        mock_users.patch.return_value.execute.assert_called_once()

    def test_updates_when_no_prior_external_ids(
        self, client: GoogleAdminClient, mock_build: MagicMock
    ) -> None:
        mock_service = mock_build.return_value
        mock_users = mock_service.users.return_value

        client.update_user_employee_id(
            email="newbie@example.com",
            employee_id="0001",
            existing_external_ids=None,
        )

        mock_users.patch.assert_called_once_with(
            userKey="newbie@example.com",
            body={
                "externalIds": [
                    {"type": "organization", "value": "0001"},
                ]
            },
        )
