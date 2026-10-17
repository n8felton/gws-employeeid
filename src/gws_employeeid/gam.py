"""Auto-detect GAM7 credentials and configuration.

GAM7 stores its configuration in ~/.gam (or $GAMCFGDIR):
  - oauth2service.json: service account key file
  - gam.cfg: INI-style config with admin_email, domain, etc.

See: https://github.com/GAM-team/GAM/wiki/gam.cfg
"""

import configparser
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_ACCOUNT_FILENAME = "oauth2service.json"
GAM_CONFIG_FILENAME = "gam.cfg"


@dataclass(frozen=True)
class GamConfig:
    """Discovered GAM7 configuration values."""

    config_dir: Path
    service_account_key: Path
    admin_email: str
    domain: str


def get_gam_config_dir() -> Path | None:
    """Locate the GAM7 configuration directory.

    Checks $GAMCFGDIR first, then falls back to ~/.gam.
    Returns None if no valid GAM directory is found.
    """
    env_dir = os.environ.get("GAMCFGDIR")
    if env_dir:
        candidate = Path(env_dir)
        if candidate.is_dir():
            logger.debug("Using GAMCFGDIR: %s", candidate)
            return candidate
        logger.debug("GAMCFGDIR set but not a directory: %s", env_dir)

    default_dir = Path.home() / ".gam"
    if default_dir.is_dir():
        logger.debug("Using default GAM dir: %s", default_dir)
        return default_dir

    return None


def find_service_account_key(gam_dir: Path) -> Path | None:
    """Find the oauth2service.json file in a GAM config directory."""
    key_path = gam_dir / SERVICE_ACCOUNT_FILENAME
    if key_path.is_file():
        return key_path
    return None


def _strip_gam_value(value: str) -> str:
    """Strip surrounding quotes that GAM7 uses for empty placeholders.

    GAM7 writes ``''`` or ``""`` in gam.cfg for unconfigured fields.
    ConfigParser preserves those quotes, so we must remove them.
    """
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ("'", '"'):
        stripped = stripped[1:-1]
    return stripped


def _parse_gam_cfg(gam_dir: Path) -> dict[str, str]:
    """Parse gam.cfg and return relevant key-value pairs.

    Reads from the DEFAULT section of the INI file.
    """
    cfg_path = gam_dir / GAM_CONFIG_FILENAME
    if not cfg_path.is_file():
        return {}

    config = configparser.ConfigParser()
    config.read(cfg_path)

    result: dict[str, str] = {}

    admin_email = _strip_gam_value(config.get("DEFAULT", "admin_email", fallback=""))
    if admin_email:
        result["admin_email"] = admin_email

    domain = _strip_gam_value(config.get("DEFAULT", "domain", fallback=""))
    if domain:
        result["domain"] = domain

    return result


def discover_gam_config() -> GamConfig | None:
    """Attempt to discover a complete GAM7 configuration.

    Returns a GamConfig if at minimum a service account key
    is found. The admin_email and domain fields may be empty
    if not configured in gam.cfg.
    """
    gam_dir = get_gam_config_dir()
    if gam_dir is None:
        logger.debug("No GAM configuration directory found")
        return None

    key_path = find_service_account_key(gam_dir)
    if key_path is None:
        logger.debug("No %s found in %s", SERVICE_ACCOUNT_FILENAME, gam_dir)
        return None

    cfg_values = _parse_gam_cfg(gam_dir)

    config = GamConfig(
        config_dir=gam_dir,
        service_account_key=key_path,
        admin_email=cfg_values.get("admin_email", ""),
        domain=cfg_values.get("domain", ""),
    )

    logger.info("Discovered GAM7 config at %s", gam_dir)
    return config
