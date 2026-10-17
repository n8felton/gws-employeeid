# gws-employeeid

Assign incremental Employee IDs to Google Workspace users ordered chronologically by account creation date/time.

## Features

- **Chronological ordering:** Evaluates users ordered by their account creation date and time (`creationTime`), assigning earlier IDs to earlier accounts.
- **Preserves existing IDs:** Users who already have an Employee ID populated are left alone by default.
- **Smart start ID auto-detection:** Automatically discovers the highest existing numeric Employee ID in your domain and continues incrementing from there (`max + 1`), avoiding duplicates and collisions.
- **Auto-detects GAM7 credentials:** Reads service account key (`oauth2service.json`), admin email, and domain directly from `~/.gam` or `$GAMCFGDIR`.
- **Customizable ID formatting:** Support for custom prefixes (e.g., `EMP-`), minimum digit width with zero-padding (e.g., `--pad-width 4` -> `0042`), and custom `--start-id`.
- **Targeting options:** Filter by Organizational Unit (`--org-unit /Staff`), specific user emails (`--users`), or exclude suspended users (`--exclude-suspended`).
- **Safe preview (`--dry-run`):** Preview all planned assignments with user names, creation timestamps, and proposed IDs before making any changes.
- **Audit reporting (`--csv-export`):** Save an audit report of all evaluated users, prior IDs, newly assigned IDs, and statuses to CSV.

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) for project and dependency management
- A Google Cloud project with the [Admin SDK API](https://developers.google.com/admin-sdk/directory/v1/guides) enabled
- A service account with [domain-wide delegation](https://developers.google.com/identity/protocols/oauth2/service-account#delegatingauthority) configured with:
  - `https://www.googleapis.com/auth/admin.directory.user`
  - `https://www.googleapis.com/auth/admin.directory.user.readonly`
- **Or** an existing [GAM7](https://github.com/GAM-team/GAM) installation

## Installation

```bash
uv sync
```

## Usage

### With GAM7 installed (simplest)

If you have GAM7 configured at `~/.gam` (or `$GAMCFGDIR`), credentials and domain are auto-detected:

```bash
# Preview proposed assignments
gws-employeeid --dry-run -v

# Run assignments
gws-employeeid -v
```

### Without GAM7 (explicit credentials)

```bash
gws-employeeid \
  --service-account-key /path/to/service-account.json \
  --admin-email admin@example.com \
  --domain example.com \
  --dry-run -v
```

### Formatting IDs

```bash
# Add a prefix and 4-digit zero padding (e.g. EMP-0001, EMP-0002)
gws-employeeid --prefix "EMP-" --pad-width 4 --dry-run

# Start at an explicit ID (e.g. 5000)
gws-employeeid --start-id 5000 --dry-run
```

### Targeting specific users or OUs

```bash
# Target a specific organizational unit
gws-employeeid --org-unit /Engineering

# Target specific user emails
gws-employeeid --users alice@example.com bob@example.com

# Exclude suspended user accounts
gws-employeeid --exclude-suspended
```

### Overwriting existing IDs

By default, users who already have an Employee ID are left untouched. To overwrite existing IDs:

```bash
gws-employeeid --force
```

### Exporting audit report to CSV

```bash
gws-employeeid --dry-run --csv-export ./employee_id_plan.csv
```

## CLI Options

| Option | Description |
|---|---|
| `--service-account-key` | Path to Google service account JSON key file (auto-detected from GAM7) |
| `--admin-email` | Email of a Workspace admin for domain-wide delegation (auto-detected from GAM7) |
| `--domain` | Google Workspace domain (auto-detected from GAM7) |
| `--start-id` | Starting integer for sequence (default: auto `max(existing) + 1` or `1`) |
| `--prefix` | String prefix prepended to Employee IDs (e.g. `EMP-`) |
| `--pad-width` | Zero-pad numeric ID to minimum width (e.g. `4` for `0001`) |
| `--org-unit` | Only process users in this organizational unit (e.g. `/Staff`) |
| `--users` | Specific user email(s) to process |
| `--exclude-suspended` | Skip suspended user accounts |
| `--dry-run` | Preview proposed changes without modifying Google Workspace |
| `--force` | Overwrite existing Employee IDs instead of leaving them alone |
| `--csv-export` | Save detailed report of evaluated users and assignments to CSV |
| `-v` / `-vv` | Increase logging verbosity (`-v` for INFO, `-vv` for DEBUG) |

## Development

```bash
# Install dependencies and pre-commit hooks
uv sync
uv run pre-commit install

# Run pre-commit hooks manually on all files
uv run pre-commit run --all-files

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=gws_employeeid

# Lint check
uv run ruff check src/ tests/

# Format check
uv run ruff format --check src/ tests/
```

## GAM7 Auto-Detection

When [GAM7](https://github.com/GAM-team/GAM) is present, `gws-employeeid` checks:
1. `$GAMCFGDIR` environment variable, falling back to `~/.gam/`
2. `oauth2service.json` for the service account key
3. `gam.cfg` `[DEFAULT]` section for `admin_email` and `domain`

Any explicit CLI flags take precedence over auto-detected values.
