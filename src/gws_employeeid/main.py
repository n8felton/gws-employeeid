"""Main orchestration for Employee ID assignment pipeline."""

import csv
import logging
from pathlib import Path

from gws_employeeid.assigner import AssignmentItem, plan_assignments
from gws_employeeid.google_admin import GoogleAdminClient
from gws_employeeid.models.config import AssignmentConfig
from gws_employeeid.models.user import WorkspaceUser

logger = logging.getLogger(__name__)


def export_plan_to_csv(
    plan: list[AssignmentItem],
    outcomes: dict[str, str],
    csv_path: Path,
) -> None:
    """Export the assignment plan and results to a CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "primary_email",
                "full_name",
                "creation_time",
                "old_employee_id",
                "new_employee_id",
                "action",
                "status",
                "reason",
            ]
        )
        for item in plan:
            email = item.user.primary_email
            creation_str = (
                item.user.creation_time.isoformat() if item.user.creation_time else ""
            )
            writer.writerow(
                [
                    email,
                    item.user.full_name,
                    creation_str,
                    item.old_employee_id or "",
                    item.new_employee_id or "",
                    item.action,
                    outcomes.get(email, "unknown"),
                    item.reason,
                ]
            )
    logger.info("Exported assignment details to CSV: %s", csv_path)


def process_users(
    client: GoogleAdminClient,
    users: list[WorkspaceUser],
    config: AssignmentConfig,
    csv_export: Path | None = None,
) -> dict[str, str]:
    """Calculate and execute Employee ID assignments for given users.

    Args:
        client: Authenticated Google Admin SDK client.
        users: List of Workspace users to process.
        config: Assignment configuration rules.
        csv_export: Optional path to export CSV report.

    Returns:
        Dict mapping user primary email to outcome status string.
    """
    plan = plan_assignments(users, config)
    outcomes: dict[str, str] = {}
    max_email_len = max((len(item.user.primary_email) for item in plan), default=0)

    for item in plan:
        email = item.user.primary_email
        email_display = email.ljust(max_email_len)

        if item.action == "skip_existing":
            logger.info(
                "Skipping %s — already has Employee ID '%s' (use --force to overwrite)",
                email_display,
                item.old_employee_id,
            )
            outcomes[email] = "skipped_existing"
            continue

        if item.action == "skip_suspended":
            logger.info(
                "Skipping %s — user account is suspended",
                email_display,
            )
            outcomes[email] = "skipped_suspended"
            continue

        # item.action == "assign"
        creation_display = (
            item.user.creation_time.strftime("%Y-%m-%d %H:%M:%S UTC")
            if item.user.creation_time
            else "unknown creation date"
        )

        if config.dry_run:
            logger.info(
                "[DRY RUN] Would assign Employee ID '%s' to %s (%s) [created: %s]",
                item.new_employee_id,
                item.user.full_name,
                email,
                creation_display,
            )
            outcomes[email] = "dry_run"
            continue

        logger.info(
            "Assigning Employee ID '%s' to %s (%s) [created: %s]",
            item.new_employee_id,
            item.user.full_name,
            email,
            creation_display,
        )

        try:
            client.update_user_employee_id(
                email=email,
                employee_id=str(item.new_employee_id),
                existing_external_ids=item.user.external_ids,
            )
            outcomes[email] = "assigned"
        except Exception:
            logger.exception("Failed to update Employee ID for %s", email)
            outcomes[email] = "failed"

    if csv_export:
        export_plan_to_csv(plan, outcomes, csv_export)

    return outcomes


def run(
    service_account_key: Path,
    admin_email: str,
    domain: str,
    config: AssignmentConfig,
    *,
    org_unit_path: str | None = None,
    user_emails: list[str] | None = None,
    csv_export: Path | None = None,
) -> dict[str, str]:
    """Top-level entry point for assigning Employee IDs.

    Args:
        service_account_key: Path to Google service account JSON key file.
        admin_email: Google Workspace admin email for domain-wide delegation.
        domain: Google Workspace domain (e.g. example.com).
        config: Assignment configuration.
        org_unit_path: Optional OU path filter.
        user_emails: Optional list of specific users to target.
        csv_export: Optional path to save CSV results.

    Returns:
        Dict mapping user primary email to outcome status string.
    """
    client = GoogleAdminClient(service_account_key, admin_email)

    logger.info("Fetching users from domain %s...", domain)
    users = client.list_users(
        domain=domain,
        org_unit_path=org_unit_path,
        user_emails=user_emails,
    )
    logger.info("Found %d user(s) to evaluate", len(users))

    if not users:
        logger.warning("No users found. Nothing to do.")
        return {}

    return process_users(
        client=client,
        users=users,
        config=config,
        csv_export=csv_export,
    )
