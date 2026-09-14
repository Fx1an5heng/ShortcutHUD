"""Pure in-memory search, category grouping and column balancing."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .catalog_presentation import ResolvedCatalogEntry

MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")
_MODIFIERS = frozenset(MODIFIER_ORDER)


@dataclass(frozen=True, slots=True)
class ModifierFilterState:
    """Guide-local cumulative filters; unrelated to physical key state."""

    selected: tuple[str, ...] = ()

    def add(self, modifier: str) -> "ModifierFilterState":
        if modifier not in _MODIFIERS or modifier in self.selected:
            return self
        selected = frozenset((*self.selected, modifier))
        return ModifierFilterState(tuple(item for item in MODIFIER_ORDER if item in selected))

    def clear(self) -> "ModifierFilterState":
        return ModifierFilterState()


@dataclass(frozen=True, slots=True)
class LayoutDensity:
    columns: int
    compact: bool
    expected_to_fit: bool


@dataclass(frozen=True, slots=True)
class CategorySection:
    category: str
    title: str
    rows: tuple[ResolvedCatalogEntry, ...]

    @property
    def estimated_height(self) -> int:
        return 52 + sum(38 + 18 * max(0, (len(row.description) - 24) // 24) for row in self.rows)

    def estimated_height_for(self, compact: bool) -> int:
        if not compact:
            return self.estimated_height
        return 44 + sum(32 + 15 * max(0, (len(row.description) - 27) // 27) for row in self.rows)


def first_stroke_modifiers(row: ResolvedCatalogEntry) -> frozenset[str]:
    trigger = row.entry.trigger
    if trigger.kind == "combo":
        tokens = trigger.keys[:-1]
    elif trigger.kind == "sequence" and trigger.keys:
        tokens = trigger.keys[0].split("+")[:-1]
    else:
        tokens = ()
    aliases = {"Control": "Ctrl", "Meta": "Win"}
    return frozenset(aliases.get(token, token) for token in tokens if aliases.get(token, token) in _MODIFIERS)


def group_entries(rows: Sequence[ResolvedCatalogEntry], query: str = "", modifiers: Sequence[str] = ()) -> tuple[CategorySection, ...]:
    terms = query.strip().casefold().split()
    required = frozenset(modifiers)
    grouped: dict[str, list[ResolvedCatalogEntry]] = {}
    for row in rows:
        if required <= first_stroke_modifiers(row) and all(term in row.search_text for term in terms):
            grouped.setdefault(row.category, []).append(row)
    return tuple(CategorySection(key, items[0].category_title, tuple(sorted(items, key=lambda row: (not row.entry.recommended, row.entry.rank, row.entry.order, row.entry.id)))) for key, items in grouped.items())


def column_count_for_width(width: int) -> int:
    return max(1, min(5, (width + 18) // 350))


def choose_layout_density(sections: Sequence[CategorySection], width: int, height: int) -> LayoutDensity:
    """Prefer normal spacing, then another readable column, then compact rows."""

    base = column_count_for_width(width)
    maximum = max(base, min(6, max(1, (width + 14) // 300)))
    usable_height = max(240, height - 138)
    for columns in range(base, maximum + 1):
        balanced = balance_categories(sections, columns)
        tallest = max((sum(section.estimated_height for section in column) for column in balanced), default=0)
        if tallest <= usable_height:
            return LayoutDensity(columns, False, True)
    balanced = balance_categories(sections, maximum)
    tallest = max((sum(section.estimated_height_for(True) for section in column) for column in balanced), default=0)
    return LayoutDensity(maximum, True, tallest <= usable_height)


def balance_categories(sections: Sequence[CategorySection], columns: int) -> tuple[tuple[CategorySection, ...], ...]:
    if columns < 1:
        raise ValueError("columns must be positive")
    result: list[list[CategorySection]] = [[] for _ in range(columns)]
    heights = [0] * columns
    for section in sections:
        index = min(range(columns), key=lambda value: (heights[value], value))
        result[index].append(section)
        heights[index] += section.estimated_height
    return tuple(tuple(column) for column in result)
