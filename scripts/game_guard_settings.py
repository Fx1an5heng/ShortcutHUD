"""Pure normalization helpers for persistent Game Guard settings."""

from __future__ import annotations

from .shortcut_resolver import (
    RESERVED_USER_IDENTITIES,
    normalize_application_identity,
)


FULLSCREEN_SUPPRESSION_SETTING = "fullscreen_suppression_enabled"
EXCLUDED_APPLICATIONS_SETTING = "excluded_applications"
DEFAULT_FULLSCREEN_SUPPRESSION_ENABLED = False


def normalize_excluded_applications(value: object) -> list[str]:
    """Return unique, editable application identities in stable input order."""

    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in value:
        application_id = normalize_excluded_application(candidate)
        if application_id is None or application_id in seen:
            continue
        seen.add(application_id)
        normalized.append(application_id)
    return normalized


def normalize_excluded_application(value: object) -> str | None:
    """Normalize one safe resolver-facing application identity."""

    application_id = normalize_application_identity(value)
    if application_id is None or application_id in RESERVED_USER_IDENTITIES:
        return None
    return application_id
