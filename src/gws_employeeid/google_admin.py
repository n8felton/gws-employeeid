"""Google Workspace Admin SDK Directory API integration.

Provides user listing and Employee ID assignment.
"""

import logging
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gws_employeeid.models.user import (
    WorkspaceUser,
    extract_employee_id,
    parse_creation_time,
)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user",
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
]


class GoogleAdminClient:
    """Client for interacting with Google Workspace Admin SDK Directory API."""

    def __init__(
        self,
        service_account_key_path: Path,
        admin_email: str,
    ) -> None:
        """Initialize the Admin SDK client.

        Args:
            service_account_key_path: Path to the service account JSON key file.
            admin_email: Email of a Workspace admin to impersonate via
                domain-wide delegation.
        """
        credentials = service_account.Credentials.from_service_account_file(
            str(service_account_key_path),
            scopes=SCOPES,
        )
        self._delegated = credentials.with_subject(admin_email)
        self._service = build(
            "admin",
            "directory_v1",
            credentials=self._delegated,
        )

    def list_users(
        self,
        domain: str,
        org_unit_path: str | None = None,
        user_emails: list[str] | None = None,
    ) -> list[WorkspaceUser]:
        """List Google Workspace users.

        Args:
            domain: The Workspace domain to query.
            org_unit_path: Optional OU path to filter users.
            user_emails: Optional list of specific user emails to fetch
                instead of listing all.

        Returns:
            List of WorkspaceUser objects.
        """
        if user_emails:
            return self._get_specific_users(user_emails)

        return self._list_all_users(domain, org_unit_path)

    def _list_all_users(
        self,
        domain: str,
        org_unit_path: str | None = None,
    ) -> list[WorkspaceUser]:
        """Fetch all users in the domain, optionally filtered by OU."""
        users: list[WorkspaceUser] = []
        page_token: str | None = None

        while True:
            kwargs: dict = {
                "domain": domain,
                "maxResults": 500,
                "projection": "full",
                "orderBy": "email",
            }
            if org_unit_path:
                kwargs["query"] = f"orgUnitPath='{org_unit_path}'"
            if page_token:
                kwargs["pageToken"] = page_token

            result = self._service.users().list(**kwargs).execute()

            for entry in result.get("users", []):
                users.append(self._parse_user(entry))

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.info("Fetched %d users from domain %s", len(users), domain)
        return users

    def _get_specific_users(
        self,
        emails: list[str],
    ) -> list[WorkspaceUser]:
        """Fetch specific users by email address."""
        users: list[WorkspaceUser] = []
        for email in emails:
            try:
                result = (
                    self._service.users()
                    .get(userKey=email, projection="full")
                    .execute()
                )
                users.append(self._parse_user(result))
            except HttpError as exc:
                logger.warning("Could not fetch user %s: %s", email, exc)
        return users

    def _parse_user(self, entry: dict) -> WorkspaceUser:
        """Parse a Google Directory API user entry into a WorkspaceUser."""
        name = entry.get("name", {})
        raw_ext_ids = entry.get("externalIds", [])
        ext_ids_list = [eid for eid in raw_ext_ids if isinstance(eid, dict)]

        return WorkspaceUser(
            primary_email=entry.get("primaryEmail", ""),
            full_name=name.get("fullName", ""),
            given_name=name.get("givenName", ""),
            family_name=name.get("familyName", ""),
            creation_time=parse_creation_time(entry.get("creationTime")),
            employee_id=extract_employee_id(ext_ids_list),
            external_ids=tuple(ext_ids_list),
            org_unit_path=entry.get("orgUnitPath", "/"),
            suspended=bool(entry.get("suspended", False)),
        )

    def update_user_employee_id(
        self,
        email: str,
        employee_id: str,
        existing_external_ids: tuple[dict, ...] | list[dict] | None = None,
    ) -> None:
        """Update a user's Employee ID in Google Workspace.

        Preserves any existing non-organization external IDs and updates/inserts
        the externalId with type='organization'.

        Args:
            email: Primary email of the user.
            employee_id: The new employee ID string to assign.
            existing_external_ids: The user's current externalIds list/tuple, if known.
        """
        updated_external_ids: list[dict] = [
            dict(eid)
            for eid in (existing_external_ids or [])
            if isinstance(eid, dict) and eid.get("type") != "organization"
        ]
        updated_external_ids.append(
            {
                "type": "organization",
                "value": str(employee_id),
            }
        )

        body = {
            "externalIds": updated_external_ids,
        }

        self._service.users().patch(
            userKey=email,
            body=body,
        ).execute()
        logger.info("Updated employee ID for %s to '%s'", email, employee_id)
