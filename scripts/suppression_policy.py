"""Shared presentation suppression semantics for ShortcutHUD surfaces."""

from __future__ import annotations

from enum import Enum, auto


class SuppressionDecision(Enum):
    """The strongest presentation restriction currently in effect."""

    ALLOW = auto()
    SOFT_BLOCK = auto()
    HARD_BLOCK = auto()


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
    """Session-owned suppression state shared by presentation controllers."""

    def __init__(self) -> None:
        self._manual_game_mode_enabled = False

    @property
    def manual_game_mode_enabled(self) -> bool:
        return self._manual_game_mode_enabled

    @property
    def decision(self) -> SuppressionDecision:
        if self._manual_game_mode_enabled:
            return SuppressionDecision.HARD_BLOCK
        return SuppressionDecision.ALLOW

    def set_manual_game_mode(self, enabled: bool) -> SuppressionDecision:
        """Set session-only Manual Game Mode and return the new decision."""

        self._manual_game_mode_enabled = bool(enabled)
        return self.decision

    def allows(self, intent: PresentationIntent) -> bool:
        return presentation_is_allowed(self.decision, intent)
