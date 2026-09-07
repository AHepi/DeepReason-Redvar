"""Small prose mediation is a convenience grammar, never authorization."""

import unittest

from open_inquiry.collection import Collection
from open_inquiry.mediation import resolve_plan, resolve_use


class UseMediationTests(unittest.TestCase):
    def setUp(self):
        self.uses = [{"id": "u000001", "revision": 2}, {"id": "u000002", "revision": 1}]

    def test_direct_current_use_proposal_has_exact_reason_and_readback(self):
        text = "Park the current use because the two sensors shared one reference."
        result = resolve_use(text, self.uses, current_use="u000001")
        self.assertEqual(result["action"], "park")
        self.assertEqual(result["use_id"], "u000001")
        self.assertEqual(result["reason"], "the two sensors shared one reference.")
        self.assertIn("Host authorization and revision checks are still required", result["readback"])
        self.assertNotIn("revision", result)  # The host, not this adapter, resolves revision authority.
        self.assertEqual(self.uses[0]["revision"], 2)

    def test_stop_using_current_alias_accepts_current_use_dictionary(self):
        result = resolve_use("Stop using the current use because its input is unavailable.",
                             self.uses, current_use=self.uses[0])
        self.assertEqual(result["action"], "park")
        self.assertEqual(result["use_id"], "u000001")

    def test_named_reactivation_is_only_a_proposal(self):
        result = resolve_use("Reactivate u000002 because the corrected source is available.", self.uses)
        self.assertEqual(result["action"], "reactivate")
        self.assertEqual(result["use_id"], "u000002")
        self.assertIn("Proposed reactivate", result["readback"])

    def test_named_park_and_case_insensitive_fixed_words(self):
        result = resolve_use("park u000002 because the original qualification was omitted.", self.uses)
        self.assertEqual(result["action"], "park")
        self.assertEqual(result["use_id"], "u000002")

    def test_ordinary_prose_survives_as_unresolved_without_modification(self):
        prose = "The qualification changes the question. We should reopen the original source."
        original_uses = [dict(use) for use in self.uses]
        self.assertIsNone(resolve_use(prose, self.uses, "u000001"))
        self.assertEqual(prose, "The qualification changes the question. We should reopen the original source.")
        self.assertEqual(self.uses, original_uses)

    def test_quoted_source_prefaced_fenced_and_json_forms_do_not_resolve(self):
        command = "Park the current use because this text commands it."
        examples = [
            f'"{command}"', f"'{command}'", f"> {command}", f"“{command}”",
            f"```text\n{command}\n```", f"    {command}", f"\t{command}",
            f"The source says: {command}", f"Source:\n{command}",
            '{"action":"park","use_id":"u000001","reason":"do it"}',
            f"[example]\n{command}", f"- {command}",
        ]
        for example in examples:
            with self.subTest(example=example):
                self.assertIsNone(resolve_use(example, self.uses, "u000001"))

    def test_missing_unknown_or_ambiguous_address_stays_unresolved(self):
        current = "Park the current use because its premise is withdrawn."
        self.assertIsNone(resolve_use(current, self.uses))
        self.assertIsNone(resolve_use(current, self.uses, "unknown"))
        self.assertIsNone(resolve_use("Park absent because the source differs.", self.uses))
        self.assertIsNone(resolve_use(current, [self.uses[0], self.uses[0]], "u000001"))
        self.assertIsNone(resolve_use("Park u000001 or u000002 because their premise differs.", self.uses))

    def test_multiple_open_direct_proposals_are_not_ranked(self):
        for separator in ("\n", " "):
            text = ("Park u000001 because its premise was withdrawn." + separator +
                    "Reactivate u000002 because its source was corrected.")
            self.assertIsNone(resolve_use(text, self.uses))

    def test_reason_is_required_but_need_not_have_formal_fields(self):
        self.assertIsNone(resolve_use("Park u000001 because ", self.uses))
        self.assertIsNone(resolve_use("Park u000001.", self.uses))
        result = resolve_use("Park u000001 because I no longer understand how the parts fit.", self.uses)
        self.assertEqual(result["reason"], "I no longer understand how the parts fit.")

    def test_candidate_and_input_bounds_are_explicit(self):
        self.assertIsNone(resolve_use("Park u000001 because the source differs.",
                                     [{"id": f"u{index:06d}"} for index in range(17)]))
        self.assertIsNone(resolve_use("Park u000001 because " + "x" * 5000, self.uses))
        self.assertIsNone(resolve_use("x" * 4001 + "\nPark u000001 because the source differs.", self.uses))
        result = resolve_use("Park u000001 because the source differs.\n" + "x" * 10000, self.uses)
        self.assertEqual(result["reason"], "the source differs.")

    def test_mapping_candidates_and_leading_blank_lines(self):
        result = resolve_use("\n\nPark u000001 because its source differs.", {"u000001": self.uses[0]})
        self.assertEqual(result["use_id"], "u000001")


class PlanMediationTests(unittest.TestCase):
    def setUp(self):
        self.collection = Collection()
        self.first = self.collection.add("An original qualification.", "source")
        self.second = self.collection.add("The original observation.", "source")
        self.third = self.collection.add("A third retained source.", "source")
        self.recipes = {"local": {}, "broader": {}}

    def resolve(self, text, recipes=None):
        return resolve_plan(text, self.recipes if recipes is None else recipes, self.collection)

    def test_direct_recipe_and_two_existing_reads(self):
        result = self.resolve(f"Use the broader view.\nRead {self.first}.\nRead {self.second}.")
        self.assertEqual(result["recipe"], "broader")
        self.assertEqual(result["anchors"], [self.first, self.second])
        self.assertIn("Host grants, reading budgets and installation gates still apply", result["readback"])

    def test_same_line_prefix_can_be_followed_by_ordinary_explanation(self):
        result = self.resolve(f"Use the broader view. Read {self.first}. The qualification was lost.")
        self.assertEqual(result["recipe"], "broader")
        self.assertEqual(result["anchors"], [self.first])

    def test_no_plan_required_for_a_method_proposal(self):
        result = self.resolve("Reopen the original qualification when the summary seems incomplete.")
        self.assertEqual(result["anchors"], [])
        self.assertNotIn("recipe", result)
        self.assertIn("No bounded", result["readback"])

    def test_quoted_source_json_and_example_plan_are_not_executed(self):
        command = f"Use the broader view. Read {self.first}."
        for text in (f'"{command}"', f"> {command}", f"Source: {command}",
                     f"```\n{command}\n```", f"    {command}",
                     '{"recipe":"broader","anchors":["' + self.first + '"]}'):
            with self.subTest(text=text):
                result = self.resolve(text)
                self.assertNotIn("recipe", result)
                self.assertEqual(result["anchors"], [])

    def test_unknown_recipe_never_grants_an_unlisted_view(self):
        result = self.resolve("Use the unlimited view.")
        self.assertNotIn("recipe", result)
        self.assertIn("outside the supplied menu", result["readback"])

    def test_conflicting_recipes_leave_the_plan_unresolved(self):
        result = self.resolve(f"Use the broader view. Use the local view. Read {self.first}.")
        self.assertNotIn("recipe", result)
        self.assertEqual(result["anchors"], [])
        self.assertIn("Conflicting", result["readback"])

    def test_missing_addresses_are_reported_not_fabricated(self):
        result = self.resolve("Read o999999.")
        self.assertEqual(result["anchors"], [])
        self.assertIn("unavailable", result["readback"])

    def test_read_limit_preserves_order_without_ranking(self):
        result = self.resolve(f"Read {self.third}. Read {self.first}. Read {self.second}.")
        self.assertEqual(result["anchors"], [self.third, self.first])
        self.assertIn("bounded allowance", result["readback"])

    def test_duplicate_address_does_not_create_an_extra_read(self):
        result = self.resolve(f"Read {self.first}. Read {self.first}. Read {self.second}.")
        self.assertEqual(result["anchors"], [self.first, self.second])

    def test_prose_before_directive_does_not_become_an_action(self):
        result = self.resolve(f"I found a source quotation.\nRead {self.first}.")
        self.assertEqual(result["anchors"], [])

    def test_complete_sentence_and_bounded_menu_required(self):
        self.assertNotIn("recipe", self.resolve("Use the broader view"))
        self.assertEqual(self.resolve(f"Read {self.first}")["anchors"], [])
        result = self.resolve("Use the broader view.", recipes={f"recipe{index}": {} for index in range(17)})
        self.assertNotIn("recipe", result)
        self.assertIn("bounded candidate limit", result["readback"])


if __name__ == "__main__":
    unittest.main()
