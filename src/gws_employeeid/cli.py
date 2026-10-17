"""Command-line interface for gws-employeeid."""

import argparse
import logging
import sys
from pathlib import Path

from gws_employeeid.gam import discover_gam_config
from gws_employeeid.models.config import AssignmentConfig


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="gws-employeeid",
        description=(
            "Assign incremental Employee IDs to Google Workspace users "
            "ordered chronologically by account creation date/time. "
            "Users who already have an Employee ID are left alone by default. "
            "When GAM7 is installed (~/.gam or $GAMCFGDIR), credentials and domain "
            "are auto-detected."
        ),
    )

    # Google Workspace credentials
    parser.add_argument(
        "--service-account-key",
        type=Path,
        default=None,
        help=(
            "Path to Google service account JSON key file. "
            "Auto-detected from GAM7 if not specified."
        ),
    )
    parser.add_argument(
        "--admin-email",
        default=None,
        help=(
            "Email of a Workspace admin for domain-wide delegation. "
            "Auto-detected from GAM7 gam.cfg if not specified."
        ),
    )
    parser.add_argument(
        "--domain",
        default=None,
        help=(
            "Google Workspace domain (e.g. example.com). "
            "Auto-detected from GAM7 gam.cfg if not specified."
        ),
    )

    # User targeting
    targeting = parser.add_mutually_exclusive_group()
    targeting.add_argument(
        "--org-unit",
        dest="org_unit_path",
        help="Only evaluate users in this organizational unit (e.g. '/Staff').",
    )
    targeting.add_argument(
        "--users",
        dest="user_emails",
        nargs="+",
        help="Specific user email(s) to evaluate.",
    )

    # ID numbering and formatting
    parser.add_argument(
        "--start-id",
        type=int,
        default=None,
        help=(
            "Starting integer for Employee ID sequence. "
            "If omitted, automatically continues from highest existing "
            "numeric ID + 1 (or 1 if none found)."
        ),
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="",
        help="String prefix prepended to Employee IDs (e.g. 'EMP-'). Default: none.",
    )
    parser.add_argument(
        "--pad-width",
        type=int,
        default=0,
        help=(
            "Zero-pad numeric ID to this minimum width (e.g. 4 for 0001). "
            "Default: 0 (no padding)."
        ),
    )
    parser.add_argument(
        "--exclude-suspended",
        action="store_true",
        default=False,
        help="Exclude suspended accounts from being assigned Employee IDs.",
    )

    # Operational flags
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Preview what would happen without making any changes in Google Workspace."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing Employee IDs instead of leaving them alone.",
    )
    parser.add_argument(
        "--csv-export",
        type=Path,
        default=None,
        help=(
            "Path to export a CSV report containing all evaluated users, "
            "IDs, and statuses."
        ),
    )

    # Logging
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity (-v for INFO, -vv for DEBUG).",
    )

    return parser


def _configure_logging(verbosity: int) -> None:
    """Configure logging based on verbosity level."""
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _resolve_gam_defaults(args: argparse.Namespace) -> None:
    """Fill in missing arguments from GAM7 configuration or error if missing."""
    gam_config = discover_gam_config()

    if gam_config:
        if args.service_account_key is None:
            args.service_account_key = gam_config.service_account_key
            logging.getLogger(__name__).info(
                "Using GAM7 service account key: %s",
                gam_config.service_account_key,
            )
        if args.admin_email is None and gam_config.admin_email:
            args.admin_email = gam_config.admin_email
            logging.getLogger(__name__).info(
                "Using GAM7 admin email: %s",
                gam_config.admin_email,
            )
        if args.domain is None and gam_config.domain:
            args.domain = gam_config.domain
            logging.getLogger(__name__).info("Using GAM7 domain: %s", gam_config.domain)

    missing: list[str] = []
    if args.service_account_key is None:
        missing.append("--service-account-key")
    if args.admin_email is None:
        missing.append("--admin-email")
    if args.domain is None:
        missing.append("--domain")

    if missing:
        hint = (
            " (install GAM7 or set GAMCFGDIR to enable auto-detection)"
            if gam_config is None
            else " (configure these in gam.cfg or pass explicitly)"
        )
        names = ", ".join(missing)
        print(
            f"Error: missing required argument(s): {names}{hint}",
            file=sys.stderr,
        )
        sys.exit(2)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)
    _resolve_gam_defaults(args)

    config = AssignmentConfig(
        start_id=args.start_id,
        prefix=args.prefix,
        pad_width=args.pad_width,
        exclude_suspended=args.exclude_suspended,
        force=args.force,
        dry_run=args.dry_run,
    )

    # Defer import to keep CLI parsing quick and testable
    from gws_employeeid.main import run

    results = run(
        service_account_key=args.service_account_key,
        admin_email=args.admin_email,
        domain=args.domain,
        config=config,
        org_unit_path=args.org_unit_path,
        user_emails=args.user_emails,
        csv_export=args.csv_export,
    )

    if results:
        assigned = sum(1 for v in results.values() if v == "assigned")
        dry = sum(1 for v in results.values() if v == "dry_run")
        skipped_existing = sum(1 for v in results.values() if v == "skipped_existing")
        skipped_suspended = sum(1 for v in results.values() if v == "skipped_suspended")
        failed = sum(1 for v in results.values() if v == "failed")

        header = "Dry Run Summary" if args.dry_run else "Summary"
        print(f"\n{header} for {len(results)} evaluated user(s):")
        if dry:
            print(f"  Would assign:        {dry}")
        if assigned:
            print(f"  Assigned:            {assigned}")
        if skipped_existing:
            print(f"  Skipped (existing):  {skipped_existing}")
        if skipped_suspended:
            print(f"  Skipped (suspended): {skipped_suspended}")
        if failed:
            print(f"  Failed:              {failed}")

        if args.csv_export:
            print(f"  CSV report saved to: {args.csv_export}")

        if failed:
            sys.exit(1)
    else:
        print("No users found to process.")
