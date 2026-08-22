from itertools import combinations, permutations
import unittest

from scripts.modifier_state import (
    CANONICAL_MODIFIER_ORDER,
    canonicalize_modifier_state,
    normalize_modifier_combination,
)


class ModifierStateTests(unittest.TestCase):
    def test_all_modifier_permutations_use_canonical_order(self) -> None:
        modifiers = tuple(modifier.casefold() for modifier in CANONICAL_MODIFIER_ORDER)

        for count in range(1, len(modifiers) + 1):
            for subset in combinations(modifiers, count):
                expected = "+".join(
                    modifier
                    for modifier in CANONICAL_MODIFIER_ORDER
                    if modifier.casefold() in subset
                )
                for arrangement in permutations(subset):
                    with self.subTest(arrangement=arrangement):
                        self.assertEqual(
                            canonicalize_modifier_state(arrangement),
                            expected,
                        )

    def test_empty_modifier_state_has_no_combination(self) -> None:
        self.assertIsNone(canonicalize_modifier_state(set()))

    def test_required_modifier_examples(self) -> None:
        examples = {
            frozenset({"ctrl"}): "Ctrl",
            frozenset({"ctrl", "shift"}): "Ctrl+Shift",
            frozenset({"shift", "alt"}): "Alt+Shift",
            frozenset({"win", "ctrl"}): "Ctrl+Win",
        }

        for modifiers, expected in examples.items():
            with self.subTest(modifiers=modifiers):
                self.assertEqual(canonicalize_modifier_state(modifiers), expected)

    def test_configuration_names_are_normalized(self) -> None:
        examples = {
            "Shift+Alt": "Alt+Shift",
            "Win+Shift": "Shift+Win",
            "Win+Ctrl": "Ctrl+Win",
        }

        for configured_name, expected in examples.items():
            with self.subTest(configured_name=configured_name):
                self.assertEqual(
                    normalize_modifier_combination(configured_name),
                    expected,
                )

    def test_altgr_has_an_explicit_future_exclusion_interface(self) -> None:
        self.assertIsNone(canonicalize_modifier_state({"ctrl", "altgr"}))
        self.assertEqual(
            canonicalize_modifier_state(
                {"ctrl", "altgr"},
                exclude_altgr=True,
            ),
            "Ctrl",
        )

    def test_unknown_modifier_has_no_canonical_combination(self) -> None:
        self.assertIsNone(normalize_modifier_combination("Ctrl+Hyper"))

    def test_unknown_logical_token_fails_closed(self) -> None:
        self.assertIsNone(canonicalize_modifier_state({"ctrl", "hyper"}))

    def test_malformed_modifier_combinations_return_none(self) -> None:
        for combination in ("", None, "Ctrl+", "Ctrl++Shift"):
            with self.subTest(combination=combination):
                self.assertIsNone(normalize_modifier_combination(combination))


if __name__ == "__main__":
    unittest.main()
