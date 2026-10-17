"""Data models for Google Workspace users."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def parse_creation_time(timestamp_str: str | None) -> datetime | None:
    """Parse ISO 8601 creation time string from Google Admin SDK into UTC datetime."""
    if not timestamp_str or not isinstance(timestamp_str, str):
        return None
    try:
        # Standard ISO-8601 string, e.g. "2021-04-12T14:32:00.000Z"
        normalized = timestamp_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, TypeError) as exc:
        logger.warning("Failed to parse creationTime '%s': %s", timestamp_str, exc)
        return None


def extract_employee_id(external_ids: list[dict] | None) -> str | None:
    """Extract employee ID from Google Admin SDK externalIds list.

    In Google Workspace Directory API, Employee ID is stored in the
    externalIds array with type='organization'.
    """
    if not external_ids:
        return None
    for entry in external_ids:
        if isinstance(entry, dict) and entry.get("type") == "organization":
            val = entry.get("value")
            if val is not None:
                stripped = str(val).strip()
                if stripped:
                    return stripped
    return None


@dataclass(frozen=True)
class WorkspaceUser:
    """Represents a Google Workspace user for Employee ID assignment."""

    primary_email: str
    full_name: str
    given_name: str = ""
    family_name: str = ""
    creation_time: datetime | None = None
    employee_id: str | None = None
    external_ids: tuple[dict, ...] = field(default_factory=tuple)
    org_unit_path: str = "/"
    suspended: bool = False

    @property
    def has_employee_id(self) -> bool:
        """Return True if user already has an employee ID assigned."""
        return self.employee_id is not None and bool(self.employee_id.strip())
