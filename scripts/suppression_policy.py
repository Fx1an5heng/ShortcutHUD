"""Shared presentation suppression semantics for ShortcutHUD surfaces."""

from __future__ import annotations

from enum import Enum, auto


class SuppressionDecision(Enum):
    """The strongest presentation restriction currently in effect."""

    ALLOW = auto()
    SOFT_BLOCK = auto()
    HARD_BLOCK = auto()


class SuppressionSource(Enum):
    """Independent reasons that can restrict ShortcutHUD presentation."""

    MANUAL_GAME_MODE = auto()
    FULLSCREEN = auto()
    EXCLUDED_APP = auto()


class PresentationIntent(Enum):
    """Whether a presentation was passive or explicitly requested by the user."""

    PASSIVE = auto()
    USER_INITIATED = auto()


def presentation_is_allowed(
    decision: SuppressionDecision,
    intent: PresentationIntent,
) -> bool:
    """Apply one suppression decision to one presentation intent.

    SOFT_BLOCK is reserved for future contextual signals such as automatic
    fullscreen detection. It blocks passive surfaces while preserving an
    explicit user path to a future Guide. HARD_BLOCK represents an explicit
    user request to suppress every ShortcutHUD presentation surface.
    """

    if decision is SuppressionDecision.ALLOW:
        return True
    if decision is SuppressionDecision.SOFT_BLOCK:
        return intent is PresentationIntent.USER_INITIATED
    return False


class SuppressionPolicy:
    """Aggregate independent suppression sources into one effective decision."""

    def __init__(self) -> None:
        self._source_decisions = {
            source: SuppressionDecision.ALLOW for source in SuppressionSource
        }

    @property
    def manual_game_mode_enabled(self) -> bool:
        return (
            self._source_decisions[SuppressionSource.MANUAL_GAME_MODE]
            is SuppressionDecision.HARD_BLOCK
        )

    @property
    def fullscreen_active(self) -> bool:
        return (
            self._source_decisions[SuppressionSource.FULLSCREEN]
            is SuppressionDecision.SOFT_BLOCK
        )

    @property
    def excluded_app_active(self) -> bool:
        return (
            self._source_decisions[SuppressionSource.EXCLUDED_APP]
            is SuppressionDecision.SOFT_BLOCK
        )

    @property
    def decision(self) -> SuppressionDecision:
        if SuppressionDecision.HARD_BLOCK in self._source_decisions.values():
            return SuppressionDecision.HARD_BLOCK
        if SuppressionDecision.SOFT_BLOCK in self._source_decisions.values():
            return SuppressionDecision.SOFT_BLOCK
        return SuppressionDecision.ALLOW

    def set_manual_game_mode(self, enabled: bool) -> SuppressionDecision:
        """Set session-only Manual Game Mode and return the new decision."""

        self._source_decisions[SuppressionSource.MANUAL_GAME_MODE] = (
            SuppressionDecision.HARD_BLOCK
            if enabled
            else SuppressionDecision.ALLOW
        )
        return self.decision

    def set_runtime_sources(
        self,
        *,
        fullscreen_active: bool,
        excluded_app_active: bool,
    ) -> SuppressionDecision:
        """Replace contextual sources together and return the effective decision."""

        self._source_decisions[SuppressionSource.FULLSCREEN] = (
            SuppressionDecision.SOFT_BLOCK
            if fullscreen_active
            else SuppressionDecision.ALLOW
        )
        self._source_decisions[SuppressionSource.EXCLUDED_APP] = (
            SuppressionDecision.SOFT_BLOCK
            if excluded_app_active
            else SuppressionDecision.ALLOW
        )
        return self.decision

    def allows(self, intent: PresentationIntent) -> bool:
        return presentation_is_allowed(self.decision, intent)
