"""Pure KeyPath hint allocation, dataset projection, and navigation state."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Iterable, Sequence

from .catalog_presentation import ResolvedCatalogEntry, localized_description
from .full_guide_model import CategorySection


class GuideMode(str, Enum):
    NORMAL = "normal"
    KEYPATH = "keypath"


class KeyPathLevel(str, Enum):
    ROOT = "root"
    CATEGORY = "category"
    RESULT = "result"


@dataclass(frozen=True, slots=True)
class HintRequest:
    stable_id: str
    preferred: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KeyPathAction:
    entry_id: str
    hint: str
    label: str
    trigger: str
    row: ResolvedCatalogEntry


@dataclass(frozen=True, slots=True)
class KeyPathCategory:
    key: str
    hint: str
    title: str
    actions: tuple[KeyPathAction, ...]


@dataclass(frozen=True, slots=True)
class KeyPathDataset:
    categories: tuple[KeyPathCategory, ...]

    @property
    def entry_count(self) -> int:
        return sum(len(category.actions) for category in self.categories)


_SINGLE_HINTS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_IGNORED_WORDS = frozenset({"a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with"})
_CATEGORY_PREFERRED_HINTS = {
    "general": "G",
    "basic_editing": "E",
    "navigation": "N",
    "search": "S",
    "display": "V",
    "editor": "R",
    "file_management": "F",
    "integrated_terminal": "T",
    "rich-languages-editing": "C",
    "editor-and-window-management": "W",
    "chat-and-ai": "A",
    "debug": "D",
    "tasks": "K",
    "global": "G",
    "user": "U",
    "legacy": "O",
}


class KeyPathHintAllocator:
    """Allocate unique, repeatable hints without locale or insertion-order drift."""

    def allocate(self, requests: Iterable[HintRequest]) -> dict[str, str]:
        items = tuple(requests)
        if len({item.stable_id for item in items}) != len(items):
            raise ValueError("hint stable IDs must be unique within a level")
        if len(items) > len(_SINGLE_HINTS):
            return self._fixed_width_fallback(items)

        result: dict[str, str] = {}
        used: set[str] = set()
        ordered = sorted(items, key=lambda item: (not bool(item.preferred), item.stable_id.casefold(), item.stable_id))
        for item in ordered:
            semantic = _hint_candidates((*item.preferred, *item.sources))
            fallback = tuple("1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ") if not semantic else _SINGLE_HINTS
            hint = next((candidate for candidate in (*semantic, *fallback) if candidate not in used), None)
            if hint is None:
                raise RuntimeError("single-character hint capacity was miscalculated")
            result[item.stable_id] = hint
            used.add(hint)
        return result

    @staticmethod
    def _fixed_width_fallback(items: Sequence[HintRequest]) -> dict[str, str]:
        width = 2
        while len(_SINGLE_HINTS) ** width < len(items):
            width += 1
        ordered = sorted(items, key=lambda item: (item.stable_id.casefold(), item.stable_id))
        return {item.stable_id: _base_hint(index, width) for index, item in enumerate(ordered)}


def build_keypath_dataset(
    sections: Sequence[CategorySection],
    allocator: KeyPathHintAllocator | None = None,
) -> KeyPathDataset:
    """Project the already resolved/filtered Full Guide sections into KeyPath."""

    hint_allocator = allocator or KeyPathHintAllocator()
    category_hints = hint_allocator.allocate(
        HintRequest(section.category, (_CATEGORY_PREFERRED_HINTS[section.category],) if section.category in _CATEGORY_PREFERRED_HINTS else (), (section.category,))
        for section in sections
    )
    categories: list[KeyPathCategory] = []
    for section in sections:
        action_requests = []
        for row in section.rows:
            explicit = row.entry.provenance.get("keypath_hint") if hasattr(row.entry.provenance, "get") else None
            preferred = (explicit,) if isinstance(explicit, str) else ()
            english_title = row.entry.title.get("en", "")
            english_description = localized_description(row.entry.description, "en")
            action_requests.append(HintRequest(row.entry.id, preferred, (english_title, english_description, *row.entry.aliases, row.entry.id)))
        action_hints = hint_allocator.allocate(action_requests)
        actions = tuple(
            KeyPathAction(row.entry.id, action_hints[row.entry.id], row.description or row.title, row.trigger, row)
            for row in section.rows
        )
        categories.append(KeyPathCategory(section.category, category_hints[section.category], section.title, actions))
    return KeyPathDataset(tuple(categories))


class KeyPathSession:
    """Guide-local ROOT/CATEGORY/RESULT navigation; never executes shortcuts."""

    def __init__(self, dataset: KeyPathDataset) -> None:
        self.dataset = dataset
        self.level = KeyPathLevel.ROOT
        self.category_key: str | None = None
        self.result_id: str | None = None
        self.input_buffer = ""

    @property
    def category(self) -> KeyPathCategory | None:
        return next((item for item in self.dataset.categories if item.key == self.category_key), None)

    @property
    def result(self) -> KeyPathAction | None:
        category = self.category
        return next((item for item in category.actions if item.entry_id == self.result_id), None) if category else None

    @property
    def path_hints(self) -> tuple[str, ...]:
        category = self.category
        if category is None:
            return ()
        result = self.result
        return (category.hint,) if result is None else (category.hint, result.hint)

    def select_hint(self, key: str) -> bool:
        if self.level == KeyPathLevel.RESULT or len(key) != 1 or not key.isascii() or not key.isalnum():
            return False
        token = (self.input_buffer + key).upper()
        options = self.dataset.categories if self.level == KeyPathLevel.ROOT else self.category.actions if self.category else ()
        matches = tuple(option for option in options if option.hint.startswith(token))
        if not matches:
            self.input_buffer = ""
            return False
        exact = next((option for option in matches if option.hint == token), None)
        if exact is None:
            self.input_buffer = token
            return True
        self.input_buffer = ""
        return self.select_category(exact.key) if self.level == KeyPathLevel.ROOT else self.select_action(exact.entry_id)

    def select_category(self, category_key: str) -> bool:
        if not any(category.key == category_key for category in self.dataset.categories):
            return False
        self.category_key = category_key
        self.result_id = None
        self.input_buffer = ""
        self.level = KeyPathLevel.CATEGORY
        return True

    def select_action(self, entry_id: str) -> bool:
        category = self.category
        if category is None or not any(action.entry_id == entry_id for action in category.actions):
            return False
        self.result_id = entry_id
        self.input_buffer = ""
        self.level = KeyPathLevel.RESULT
        return True

    def back(self) -> bool:
        self.input_buffer = ""
        if self.level == KeyPathLevel.RESULT:
            self.result_id = None
            self.level = KeyPathLevel.CATEGORY
            return True
        if self.level == KeyPathLevel.CATEGORY:
            self.category_key = None
            self.level = KeyPathLevel.ROOT
            return True
        return False


def _hint_candidates(sources: Iterable[str]) -> tuple[str, ...]:
    candidates: list[str] = []
    for source in sources:
        words = [word.upper() for word in _WORD_RE.findall(source) if word.casefold() not in _IGNORED_WORDS]
        for candidate in (word[0] for word in words if word):
            if candidate in _SINGLE_HINTS and candidate not in candidates:
                candidates.append(candidate)
        for candidate in (character for word in words for character in word):
            if candidate in _SINGLE_HINTS and candidate not in candidates:
                candidates.append(candidate)
    return tuple(candidates)


def _base_hint(index: int, width: int) -> str:
    base = len(_SINGLE_HINTS)
    digits = []
    value = index
    for _ in range(width):
        digits.append(_SINGLE_HINTS[value % base])
        value //= base
    return "".join(reversed(digits))
