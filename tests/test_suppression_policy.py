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
