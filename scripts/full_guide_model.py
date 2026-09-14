"""Pure in-memory search, category grouping and column balancing."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .catalog_presentation import ResolvedCatalogEntry

MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")
_MODIFIERS = frozenset(MODIFIER_ORDER)
MIN_READABLE_COLUMN_WIDTH = 320
MAX_GUIDE_COLUMNS = 5
COLUMN_GAP = 18
SECTION_GAP = 18


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
class CategorySection:
    category: str
    title: str
    rows: tuple[ResolvedCatalogEntry, ...]

    @property
    def estimated_height(self) -> int:
        """Estimate a lightweight heading plus fixed-height, single-line rows."""

        return 34 + 30 * len(self.rows)


@dataclass(frozen=True, slots=True)
class GuideLayoutPlan:
    columns: int
    assignments: tuple[tuple[CategorySection, ...], ...]
    expected_to_fit: bool


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
    """Choose readable columns from usable content width, including gaps."""

    return max(1, min(MAX_GUIDE_COLUMNS, (max(1, width) + COLUMN_GAP) // (MIN_READABLE_COLUMN_WIDTH + COLUMN_GAP)))


def plan_guide_layout(sections: Sequence[CategorySection], width: int, height: int) -> GuideLayoutPlan:
    """Plan readable, sequential columns and accept scrolling when needed."""

    columns = min(column_count_for_width(width), max(1, len(sections)))
    assignments = balance_categories(sections, columns)
    usable_height = max(240, height - 126)
    tallest = max((_column_height(column) for column in assignments), default=0)
    return GuideLayoutPlan(columns, assignments, tallest <= usable_height)


def choose_layout_density(sections: Sequence[CategorySection], width: int, height: int) -> GuideLayoutPlan:
    """Compatibility name retained for existing callers and extensions."""

    return plan_guide_layout(sections, width, height)


def balance_categories(sections: Sequence[CategorySection], columns: int) -> tuple[tuple[CategorySection, ...], ...]:
    """Partition ordered categories into contiguous, approximately even columns."""

    if columns < 1:
        raise ValueError("columns must be positive")
    result: list[list[CategorySection]] = [[] for _ in range(columns)]
    heights = [0] * columns
    if not sections:
        return tuple(tuple(column) for column in result)

    active_columns = min(columns, len(sections))
    total_height = sum(section.estimated_height for section in sections)
    total_height += SECTION_GAP * max(0, len(sections) - active_columns)
    target_height = (total_height + active_columns - 1) // active_columns
    column_index = 0
    for position, section in enumerate(sections):
        section_height = section.estimated_height
        if result[column_index] and column_index < active_columns - 1:
            added_height = SECTION_GAP + section_height
            current_height = heights[column_index]
            remaining_sections = len(sections) - position
            remaining_columns = active_columns - column_index - 1
            must_advance = remaining_sections <= remaining_columns
            current_is_closer = abs(target_height - current_height) <= abs(target_height - (current_height + added_height))
            if must_advance or current_is_closer:
                column_index += 1
        if result[column_index]:
            heights[column_index] += SECTION_GAP
        result[column_index].append(section)
        heights[column_index] += section_height
    return tuple(tuple(column) for column in result)


def _column_height(sections: Sequence[CategorySection]) -> int:
    if not sections:
        return 0
    return sum(section.estimated_height for section in sections) + SECTION_GAP * (len(sections) - 1)
