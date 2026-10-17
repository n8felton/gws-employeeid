"""Logic for ordering users and computing incremental Employee IDs."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from gws_employeeid.models.config import AssignmentConfig
from gws_employeeid.models.user import WorkspaceUser

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssignmentItem:
    """Represents a planned or executed Employee ID assignment for a user."""

    user: WorkspaceUser
    old_employee_id: str | None
    new_employee_id: str | None
    action: str  # "assign", "skip_existing", "skip_suspended"
    reason: str = ""


def find_max_existing_numeric_id(
    users: list[WorkspaceUser], prefix: str = ""
) -> int | None:
    """Find the highest integer employee ID among users who already have one.

    If a prefix is provided, it attempts to match IDs starting with that prefix.
    Otherwise, it checks for pure numeric IDs or IDs ending in digits.
    """
    max_id: int | None = None

    for user in users:
        emp_id = user.employee_id
        if not emp_id:
            continue

        candidate_num: int | None = None

        if prefix and emp_id.startswith(prefix):
            suffix = emp_id[len(prefix) :]
            if suffix.isdigit():
                candidate_num = int(suffix)
        elif emp_id.isdigit():
            candidate_num = int(emp_id)

        if candidate_num is not None:
            if max_id is None or candidate_num > max_id:
                max_id = candidate_num

    return max_id


def sort_users_by_creation_time(
    users: list[WorkspaceUser],
) -> list[WorkspaceUser]:
    """Sort users chronologically by creationTime ascending.

    Users with missing creationTime are placed earliest.
    Ties are broken deterministically by primaryEmail.
    """
    earliest = datetime.min.replace(tzinfo=UTC)
    return sorted(
        users,
        key=lambda u: (
            u.creation_time if u.creation_time is not None else earliest,
            u.primary_email.lower(),
        ),
    )


def plan_assignments(
    users: list[WorkspaceUser],
    config: AssignmentConfig,
) -> list[AssignmentItem]:
    """Calculate the Employee ID assignment plan for all users.

    - Sorts candidate users by creation date/time ascending.
    - Leaves users alone if their employee ID is already populated
      (unless config.force=True).
    - Honors config.exclude_suspended.
    - Determines the start ID from config or highest existing numeric ID + 1.
    - Avoids colliding with any existing employee IDs in the organization.
    """
    # Collect all existing employee IDs to prevent collisions
    existing_id_strings: set[str] = {u.employee_id for u in users if u.employee_id}

    # Determine starting ID if not explicitly provided
    if config.start_id is not None:
        next_num = config.start_id
    else:
        max_existing = find_max_existing_numeric_id(users, prefix=config.prefix)
        if max_existing is not None:
            next_num = max_existing + 1
            logger.info(
                "Auto-detected highest existing ID %d; starting from %d",
                max_existing,
                next_num,
            )
        else:
            next_num = 1
            logger.info("No existing numeric IDs found; starting from 1")

    # Sort users by creation date/time
    sorted_users = sort_users_by_creation_time(users)

    plan: list[AssignmentItem] = []

    for user in sorted_users:
        # Check suspended
        if config.exclude_suspended and user.suspended:
            plan.append(
                AssignmentItem(
                    user=user,
                    old_employee_id=user.employee_id,
                    new_employee_id=None,
                    action="skip_suspended",
                    reason="User account is suspended",
                )
            )
            continue

        # Check existing employee ID
        if user.has_employee_id and not config.force:
            plan.append(
                AssignmentItem(
                    user=user,
                    old_employee_id=user.employee_id,
                    new_employee_id=None,
                    action="skip_existing",
                    reason=f"Already has Employee ID '{user.employee_id}'",
                )
            )
            continue

        # Find next available ID that doesn't collide with existing IDs
        while True:
            formatted_id = config.format_id(next_num)
            next_num += 1
            # If force=True, user's own old ID is allowed to be overwritten,
            # but other existing IDs should not be duplicated
            if formatted_id not in existing_id_strings or (
                config.force and formatted_id == user.employee_id
            ):
                existing_id_strings.add(formatted_id)
                break

        plan.append(
            AssignmentItem(
                user=user,
                old_employee_id=user.employee_id,
                new_employee_id=formatted_id,
                action="assign",
                reason="Assigned based on creation date",
            )
        )

    return plan
