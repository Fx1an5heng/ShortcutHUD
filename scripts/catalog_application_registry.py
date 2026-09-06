"""User-facing application registry derived from the initialized Catalog."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .application_descriptor import ApplicationDescriptor
from .application_display_names import get_application_display_name
from .shortcut_catalog import ShortcutCatalog, select_catalog_text
from .shortcut_resolver import RESERVED_USER_IDENTITIES, normalize_application_identity

_PRODUCT_LABELS = {
    "WINWORD.EXE": "Microsoft Word", "EXCEL.EXE": "Microsoft Excel",
    "POWERPNT.EXE": "Microsoft PowerPoint", "WPSOFFICE.EXE": "WPS Office",
    "PHOTOSHOP.EXE": "Adobe Photoshop", "OUTLOOK.EXE": "Microsoft Outlook",
    "NOTEPAD.EXE": "Notepad", "ACRORD32.EXE": "Adobe Acrobat Reader",
    "CHROME.EXE": "Google Chrome", "CODE.EXE": "Visual Studio Code",
    "CODE-INSIDERS.EXE": "Visual Studio Code Insiders", "MSEDGE.EXE": "Microsoft Edge",
    "EXPLORER.EXE": "File Explorer", "WINDOWSTERMINAL.EXE": "Windows Terminal",
    "ADOBE PREMIERE PRO.EXE": "Adobe Premiere Pro", "AFTERFX.EXE": "Adobe After Effects",
    "AUDITION.EXE": "Adobe Audition", "3DSMAX.EXE": "Autodesk 3ds Max",
    "MAYA.EXE": "Autodesk Maya", "UNITY.EXE": "Unity", "UNREALEDITOR.EXE": "Unreal Editor",
}


@dataclass(frozen=True, slots=True)
class CatalogApplication:
    product_id: str
    display_name: str
    primary_identity: str
    identities: tuple[str, ...]
    source: str
    detected: bool


class CatalogApplicationRegistry:
    """One Catalog-facing app view; process identities stay below this boundary."""

    def __init__(
        self,
        catalog: ShortcutCatalog,
        user_profiles: Mapping[str, object] | None = None,
        language: str | None = None,
        detected_identities: Iterable[str | None] = (),
    ) -> None:
        self.catalog = catalog
        self.user_profiles = user_profiles if isinstance(user_profiles, Mapping) else {}
        self.language = language
        self.detected = {
            identity for value in detected_identities
            if (identity := normalize_application_identity(value)) is not None
        }

    def applications(self) -> list[CatalogApplication]:
        grouped: dict[str, tuple[list[str], set[str]]] = {}
        for entry in self.catalog.entries:
            if entry.scope != "APP":
                continue
            for identity in entry.application_ids:
                product_id = self.catalog.application_product_ids.get(
                    identity, f"legacy.{identity.casefold()}"
                )
                identities, sources = grouped.setdefault(product_id, ([], set()))
                if identity not in identities:
                    identities.append(identity)
                sources.add("PACK" if identity in self.catalog.application_titles else "LEGACY")
        for raw_identity in self.user_profiles:
            identity = normalize_application_identity(raw_identity)
            if identity is not None and identity not in RESERVED_USER_IDENTITIES:
                product_id = self.catalog.application_product_ids.get(
                    identity, f"legacy.{identity.casefold()}"
                )
                identities, sources = grouped.setdefault(product_id, ([], set()))
                if identity not in identities:
                    identities.append(identity)
                sources.add("USER")
        records = [self._record(product_id, identities, sources) for product_id, (identities, sources) in grouped.items()]
        return sorted(records, key=lambda item: (item.display_name.casefold(), item.product_id))

    def find_by_identity(self, identity: str | None) -> CatalogApplication | None:
        normalized = normalize_application_identity(identity)
        if normalized is None:
            return None
        return next(
            (item for item in self.applications() if normalized in item.identities),
            None,
        )

    def supported_applications(self) -> list[CatalogApplication]:
        """Catalog-backed applications only; USER-only profiles remain detected apps."""

        return [
            item for item in self.applications()
            if self.has_builtin_support(item.primary_identity)
        ]

    def has_builtin_support(self, identity: str | None) -> bool:
        normalized = normalize_application_identity(identity)
        return normalized is not None and any(
            entry.scope == "APP" and normalized in entry.application_ids
            for entry in self.catalog.entries
        )

    def describe(self, descriptor: ApplicationDescriptor | None) -> ApplicationDescriptor | None:
        """Decorate a detected app with optional Catalog support, never filter it."""

        if descriptor is None:
            return None
        if not self.has_builtin_support(descriptor.runtime_identity):
            return descriptor
        record = self.find_by_identity(descriptor.runtime_identity)
        if record is None:
            return descriptor
        return descriptor.with_catalog(
            product_id=record.product_id,
            display_name=record.display_name,
            aliases=record.identities,
        )

    def _record(
        self,
        product_id: str,
        identities: list[str],
        sources: set[str],
    ) -> CatalogApplication:
        identity = identities[0]
        title = self.catalog.application_titles.get(identity)
        display = select_catalog_text(title, self.language) if title else (
            _PRODUCT_LABELS.get(identity)
            or get_application_display_name(identity)
            or _friendly_legacy_name(identity)
        )
        source = "PACK" if "PACK" in sources else "USER" if sources == {"USER"} else "LEGACY"
        return CatalogApplication(
            product_id=product_id,
            display_name=display,
            primary_identity=identity,
            identities=tuple(identities),
            source=source,
            detected=bool(set(identities) & self.detected),
        )


def _friendly_legacy_name(identity: str) -> str:
    stem = identity.removesuffix(".EXE").replace("_", " ").replace("-", " ")
    return stem.title()
