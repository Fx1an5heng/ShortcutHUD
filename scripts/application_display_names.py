"""User-facing application labels for ShortcutHUD presentation."""

from __future__ import annotations

from collections.abc import Mapping

from .shell_identity import WINDOWS_SHELL
from .wps_identity import (
    WPS_PDF,
    WPS_PRESENTATION,
    WPS_UNKNOWN,
    WPS_WRITER,
)


_APPLICATION_DISPLAY_NAMES = {
    WPS_WRITER: "WPS Writer",
    WPS_PDF: "WPS PDF",
    WPS_PRESENTATION: "WPS Presentation",
    WPS_UNKNOWN: None,
    WINDOWS_SHELL: None,
}


def get_application_display_name(
    application_name: str | None,
    user_display_names: Mapping[str, str] | None = None,
) -> str | None:
    """Return a user override, built-in label, or raw resolver identity."""

    if not isinstance(application_name, str) or not application_name.strip():
        return "DEFAULT"

    internal_name = application_name.strip()
    normalized_name = internal_name.upper()
    built_in_name = _APPLICATION_DISPLAY_NAMES.get(normalized_name, internal_name)
    if built_in_name is None:
        return None
    if isinstance(user_display_names, Mapping):
        user_name = user_display_names.get(normalized_name)
        if isinstance(user_name, str) and user_name.strip():
            return user_name.strip()
    return built_in_name
