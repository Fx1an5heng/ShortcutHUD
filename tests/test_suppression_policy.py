import unittest

from scripts.suppression_policy import (
    PresentationIntent,
    SuppressionDecision,
    SuppressionPolicy,
    presentation_is_allowed,
)


class SuppressionPolicyTests(unittest.TestCase):
    def test_default_is_allow(self) -> None:
        policy = SuppressionPolicy()

        self.assertFalse(policy.manual_game_mode_enabled)
        self.assertIs(policy.decision, SuppressionDecision.ALLOW)
        self.assertTrue(policy.allows(PresentationIntent.PASSIVE))

    def test_manual_game_mode_on_is_hard_block(self) -> None:
        policy = SuppressionPolicy()

        decision = policy.set_manual_game_mode(True)

        self.assertIs(decision, SuppressionDecision.HARD_BLOCK)
        self.assertFalse(policy.allows(PresentationIntent.PASSIVE))
        self.assertFalse(policy.allows(PresentationIntent.USER_INITIATED))

    def test_manual_game_mode_off_returns_to_allow(self) -> None:
        policy = SuppressionPolicy()
        policy.set_manual_game_mode(True)

        decision = policy.set_manual_game_mode(False)

        self.assertIs(decision, SuppressionDecision.ALLOW)
        self.assertTrue(policy.allows(PresentationIntent.PASSIVE))

    def test_fullscreen_is_soft_block(self) -> None:
        policy = SuppressionPolicy()

        decision = policy.set_runtime_sources(
            fullscreen_active=True,
            excluded_app_active=False,
        )

        self.assertIs(decision, SuppressionDecision.SOFT_BLOCK)
        self.assertTrue(policy.fullscreen_active)

    def test_excluded_app_is_soft_block(self) -> None:
        policy = SuppressionPolicy()

        decision = policy.set_runtime_sources(
            fullscreen_active=False,
            excluded_app_active=True,
        )

        self.assertIs(decision, SuppressionDecision.SOFT_BLOCK)
        self.assertTrue(policy.excluded_app_active)

    def test_manual_precedes_fullscreen(self) -> None:
        policy = SuppressionPolicy()
        policy.set_runtime_sources(
            fullscreen_active=True,
            excluded_app_active=False,
        )

        decision = policy.set_manual_game_mode(True)

        self.assertIs(decision, SuppressionDecision.HARD_BLOCK)

    def test_disabling_manual_preserves_fullscreen_soft_block(self) -> None:
        policy = SuppressionPolicy()
        policy.set_runtime_sources(
            fullscreen_active=True,
            excluded_app_active=False,
        )
        policy.set_manual_game_mode(True)

        decision = policy.set_manual_game_mode(False)

        self.assertIs(decision, SuppressionDecision.SOFT_BLOCK)

    def test_clearing_all_sources_returns_to_allow(self) -> None:
        policy = SuppressionPolicy()
        policy.set_manual_game_mode(True)
        policy.set_runtime_sources(
            fullscreen_active=True,
            excluded_app_active=True,
        )

        policy.set_manual_game_mode(False)
        decision = policy.set_runtime_sources(
            fullscreen_active=False,
            excluded_app_active=False,
        )

        self.assertIs(decision, SuppressionDecision.ALLOW)

    def test_soft_block_reserves_explicit_user_presentations(self) -> None:
        self.assertFalse(
            presentation_is_allowed(
                SuppressionDecision.SOFT_BLOCK,
                PresentationIntent.PASSIVE,
            )
        )
        self.assertTrue(
            presentation_is_allowed(
                SuppressionDecision.SOFT_BLOCK,
                PresentationIntent.USER_INITIATED,
            )
        )


if __name__ == "__main__":
    unittest.main()
