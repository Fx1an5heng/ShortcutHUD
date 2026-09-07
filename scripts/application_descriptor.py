"""User-facing descriptions of applications observed in the foreground."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import PureWindowsPath

from .application_display_names import get_application_display_name
from .shell_identity import WINDOWS_DESKTOP
from .shortcut_resolver import normalize_application_identity


@dataclass(frozen=True, slots=True)
class ApplicationMetadata:
    product_name: str | None = None
    file_description: str | None = None


@dataclass(frozen=True, slots=True)
class ApplicationDescriptor:
    """One external foreground application, independent of Catalog coverage."""

    runtime_identity: str
    executable_name: str
    executable_path: str | None
    display_name: str
    product_name: str | None = None
    file_description: str | None = None
    catalog_product_id: str | None = None
    supported: bool = False
    aliases: tuple[str, ...] = ()
    last_detected_order: int = 0
    context_kind: str = "application"

    def with_catalog(
        self,
        *,
        product_id: str | None,
        display_name: str | None = None,
        aliases: tuple[str, ...] = (),
    ) -> "ApplicationDescriptor":
        return replace(
            self,
            catalog_product_id=product_id,
            supported=product_id is not None,
            display_name=display_name or self.display_name,
            aliases=aliases,
        )


MetadataProvider = Callable[[str], ApplicationMetadata | Mapping[str, object] | None]


class ApplicationDescriptorFactory:
    """Build descriptors from one known foreground executable; never scans apps."""

    def __init__(self, metadata_provider: MetadataProvider | None = None) -> None:
        self._metadata_provider = metadata_provider or read_windows_version_metadata

    def describe(
        self,
        runtime_identity: object,
        executable_path: object = None,
        *,
        order: int = 0,
    ) -> ApplicationDescriptor | None:
        identity = normalize_application_identity(runtime_identity)
        if identity is None:
            return None
        if identity == WINDOWS_DESKTOP:
            return ApplicationDescriptor(
                runtime_identity=identity,
                executable_name="EXPLORER.EXE",
                executable_path=None,
                display_name="Windows Desktop",
                last_detected_order=order,
                context_kind="desktop",
            )
        path = _clean_path(executable_path)
        metadata = self._metadata(path) if path else ApplicationMetadata()
        executable_name = PureWindowsPath(path).name.upper() if path else identity
        display_name = (
            metadata.product_name
            or metadata.file_description
            or _known_display_name(identity)
            or _friendly_executable_name(executable_name)
        )
        return ApplicationDescriptor(
            runtime_identity=identity,
            executable_name=executable_name,
            executable_path=path,
            display_name=display_name,
            product_name=metadata.product_name,
            file_description=metadata.file_description,
            last_detected_order=order,
        )

    def _metadata(self, path: str) -> ApplicationMetadata:
        try:
            raw = self._metadata_provider(path)
        except (OSError, ValueError, TypeError):
            raw = None
        if isinstance(raw, ApplicationMetadata):
            return raw
        if isinstance(raw, Mapping):
            return ApplicationMetadata(
                product_name=_clean_text(raw.get("ProductName")),
                file_description=_clean_text(raw.get("FileDescription")),
            )
        return ApplicationMetadata()


def read_windows_version_metadata(path: str) -> ApplicationMetadata:
    """Read optional version-resource labels for a single executable safely."""

    try:
        import win32api

        translations = win32api.GetFileVersionInfo(path, r"\\VarFileInfo\\Translation")
        pairs = translations if isinstance(translations, list) else []
        for language, code_page in pairs:
            root = fr"\\StringFileInfo\\{language:04X}{code_page:04X}\\"
            product = _clean_text(win32api.GetFileVersionInfo(path, root + "ProductName"))
            description = _clean_text(win32api.GetFileVersionInfo(path, root + "FileDescription"))
            if product or description:
                return ApplicationMetadata(product, description)
    except (ImportError, OSError, ValueError, TypeError):
        pass
    return ApplicationMetadata()


def _known_display_name(identity: str) -> str | None:
    label = get_application_display_name(identity)
    return label if label and label != identity else None


def _clean_path(value: object) -> str | None:
    return value.strip().strip('"') if isinstance(value, str) and value.strip() else None


def _clean_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _friendly_executable_name(executable_name: str) -> str:
    return executable_name.removesuffix(".EXE").replace("_", " ").replace("-", " ").title()
