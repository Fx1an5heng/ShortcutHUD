"""User-facing application labels for ShortcutHUD presentation."""

from __future__ import annotations

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
}


def get_application_display_name(application_name: str | None) -> str | None:
    """Return a UI label without changing the resolver-owned identity."""

    if not isinstance(application_name, str) or not application_name.strip():
        return "DEFAULT"

    internal_name = application_name.strip()
    return _APPLICATION_DISPLAY_NAMES.get(
        internal_name.upper(),
        internal_name,
    )
