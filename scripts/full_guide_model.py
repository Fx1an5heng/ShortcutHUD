"""Pure in-memory search, category grouping and column balancing."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .catalog_presentation import ResolvedCatalogEntry


@dataclass(frozen=True, slots=True)
class CategorySection:
    category: str
    title: str
    rows: tuple[ResolvedCatalogEntry, ...]

    @property
    def estimated_height(self) -> int:
        return 52 + sum(38 + 18 * max(0, (len(row.description) - 24) // 24) for row in self.rows)


def group_entries(rows: Sequence[ResolvedCatalogEntry], query: str = "") -> tuple[CategorySection, ...]:
    terms = query.strip().casefold().split()
    grouped: dict[str, list[ResolvedCatalogEntry]] = {}
    for row in rows:
        if all(term in row.search_text for term in terms):
            grouped.setdefault(row.category, []).append(row)
    return tuple(CategorySection(key, items[0].category_title, tuple(sorted(items, key=lambda row: (not row.entry.recommended, row.entry.rank, row.entry.order, row.entry.id)))) for key, items in grouped.items())


def column_count_for_width(width: int) -> int:
    return max(1, min(5, (width + 18) // 350))


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
