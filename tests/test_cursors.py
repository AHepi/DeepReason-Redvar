"""Cursor preparation must scale with touched entries, not saved history."""

from copy import deepcopy
import json
import unittest

from open_inquiry.collection import Collection
from open_inquiry.config import validate
from open_inquiry.context import compile_cut
from open_inquiry.cursors import CursorTransaction


class NoIterationDict(dict):
    """Fail if point-operation/commit paths secretly enumerate the base map."""

    def __iter__(self):
        raise AssertionError("Saved cursor dictionary was enumerated")

    def keys(self):
        raise AssertionError("Saved cursor keys were enumerated")

    def items(self):
        raise AssertionError("Saved cursor items were enumerated")

    def values(self):
        raise AssertionError("Saved cursor values were enumerated")


class CursorTransactionTests(unittest.TestCase):
    def test_nested_changes_are_isolated_until_commit(self):
        base = {"roots": 2, "edges": {"o1": {"flat": 4, "streams": {"route": 7}}}}
        original = deepcopy(base)
        transaction = CursorTransaction(base)
        transaction["roots"] = 3
        transaction["edges"]["o1"]["streams"]["route"] = 8
        transaction["edges"]["o1"]["new"] = 11
        self.assertEqual(transaction["roots"], 3)
        self.assertEqual(transaction["edges"]["o1"]["streams"]["route"], 8)
        self.assertEqual(base, original)
        self.assertIs(transaction.commit(), base)
        self.assertEqual(base["roots"], 3)
        self.assertEqual(base["edges"]["o1"]["streams"]["route"], 8)
        self.assertEqual(base["edges"]["o1"]["new"], 11)

    def test_discard_leaves_base_exact_including_nested_identity(self):
        base = {"a": {"b": 1}, "remove": 3}
        nested = base["a"]
        original = json.dumps(base)
        transaction = CursorTransaction(base)
        transaction["a"]["b"] = 99
        transaction.pop("remove")
        transaction.setdefault("new", {})["position"] = 7
        transaction.discard()
        self.assertEqual(json.dumps(base), original)
        self.assertIs(base["a"], nested)
        self.assertNotIn("new", base)

    def test_abandoned_transaction_also_leaves_base_unchanged(self):
        base = {"a": {"position": 1}}
        transaction = CursorTransaction(base)
        transaction["a"]["position"] = 12
        del transaction
        self.assertEqual(base, {"a": {"position": 1}})

    def test_nested_transactions_are_cached(self):
        transaction = CursorTransaction({"a": {"b": 1}})
        self.assertIs(transaction["a"], transaction.get("a"))
        self.assertIs(transaction["a"], transaction.setdefault("a", {"other": 2}))
        self.assertNotIn("other", transaction["a"])

    def test_new_nested_dictionary_is_wrapped_and_committed_without_proxy(self):
        base = {}
        transaction = CursorTransaction(base)
        child = transaction.setdefault("edges", {})
        state = child.setdefault("o1", {"streams": {}, "flat": 0})
        state["streams"]["a"] = 3
        self.assertEqual(base, {})
        transaction.commit()
        self.assertEqual(base, {"edges": {"o1": {"streams": {"a": 3}, "flat": 0}}})
        self.assertEqual(json.loads(json.dumps(base)), base)
        self.assertIs(type(base["edges"]), dict)
        self.assertIs(type(base["edges"]["o1"]), dict)

    def test_point_operations_and_commit_never_enumerate_saved_maps(self):
        leaves = NoIterationDict({str(index): index for index in range(20000)})
        branch = NoIterationDict({"positions": leaves, "untouched": {"x": 1}})
        base = NoIterationDict({"large": branch, "delete": 1})
        transaction = CursorTransaction(base)
        transaction["large"]["positions"]["17000"] = 8
        transaction["large"]["positions"]["new"] = 9
        self.assertEqual(transaction.pop("delete"), 1)
        self.assertEqual(len(transaction), 1)
        transaction.commit()
        self.assertEqual(leaves["17000"], 8)
        self.assertEqual(leaves["new"], 9)
        self.assertNotIn("delete", base)

    def test_readonly_child_is_not_traversed_at_commit(self):
        readonly = NoIterationDict({"untouched": 8})
        base = NoIterationDict({"readonly": readonly, "change": 0})
        transaction = CursorTransaction(base)
        transaction["readonly"]
        transaction["change"] = 1
        transaction.commit()
        self.assertIs(base["readonly"], readonly)

    def test_replacement_discards_earlier_child_edits(self):
        original_child = {"value": 1}
        base = {"child": original_child}
        transaction = CursorTransaction(base)
        old = transaction["child"]
        old["value"] = 2
        transaction["child"] = {"replacement": 3}
        old["value"] = 4
        transaction["child"]["replacement"] = 5
        transaction.commit()
        self.assertEqual(base, {"child": {"replacement": 5}})
        self.assertEqual(original_child, {"value": 1})

    def test_deletion_discards_earlier_child_edits(self):
        original_child = {"value": 1}
        base = {"child": original_child}
        transaction = CursorTransaction(base)
        old = transaction["child"]
        old["value"] = 2
        transaction.pop("child")
        old["another"] = 3
        transaction.commit()
        self.assertEqual(base, {})
        self.assertEqual(original_child, {"value": 1})

    def test_pop_setdefault_and_length_follow_mapping_behavior(self):
        base = {"old": 1, "replace": 2}
        transaction = CursorTransaction(base)
        self.assertEqual(transaction.pop("absent", 7), 7)
        with self.assertRaises(KeyError):
            transaction.pop("absent")
        self.assertEqual(transaction.setdefault("old", 8), 1)
        transaction["new"] = 4
        transaction["replace"] = 5
        self.assertEqual(len(transaction), 3)
        self.assertEqual(transaction.pop("new"), 4)
        self.assertEqual(len(transaction), 2)
        transaction.pop("old")
        self.assertEqual(len(transaction), 1)
        transaction["old"] = 9
        self.assertEqual(len(transaction), 2)
        transaction.commit()
        self.assertEqual(base, {"old": 9, "replace": 5})

    def test_explicit_iteration_is_available_but_not_used_for_commit(self):
        transaction = CursorTransaction({"a": 1, "b": 2})
        transaction.pop("a")
        transaction["c"] = 3
        self.assertEqual(list(transaction), ["b", "c"])
        self.assertEqual(dict(transaction), {"b": 2, "c": 3})

    def test_mutable_non_dictionary_leaves_cannot_bypass_isolation(self):
        transaction = CursorTransaction({"list": [1]})
        with self.assertRaises(TypeError):
            transaction["list"]
        with self.assertRaises(TypeError):
            transaction["new"] = []
        with self.assertRaises(TypeError):
            transaction["proxy"] = CursorTransaction({})

    def test_proxy_itself_is_not_a_serializable_state_object(self):
        with self.assertRaises(TypeError):
            json.dumps(CursorTransaction({"a": 1}))

    def test_only_root_can_finish_and_finished_views_cannot_mutate_again(self):
        base = {"child": {"value": 1}}
        transaction = CursorTransaction(base)
        child = transaction["child"]
        with self.assertRaises(RuntimeError):
            child.commit()
        with self.assertRaises(RuntimeError):
            child.discard()
        transaction.commit()
        self.assertIs(transaction.commit(), base)
        with self.assertRaises(RuntimeError):
            child["value"] = 2
        discarded = CursorTransaction({})
        discarded.discard()
        discarded.discard()
        with self.assertRaises(RuntimeError):
            discarded.commit()

    def test_context_cut_can_be_retried_without_consuming_unfunded_cursors(self):
        collection = Collection()
        focus = collection.add("Inspect this question.", "operator")
        for text in ("one", "two", "three"):
            collection.link(focus, collection.add(text, "source"))
        account = {"id": "a1", "focus": focus, "uses": [], "context_cursors": {}}
        policy = validate({"neighbour_items": 1})

        def prepare():
            transaction = CursorTransaction(account["context_cursors"])
            view = {**account, "context_cursors": transaction}
            cut = compile_cut(collection, policy=policy, account=view, invitation="Continue.",
                              counter=lambda messages: len(json.dumps(messages)))
            return transaction, cut

        unfunded, first = prepare()
        self.assertEqual(account["context_cursors"], {})
        unfunded.discard()
        funded, retried = prepare()
        self.assertEqual(first.to_dict(), retried.to_dict())
        funded.commit()
        following, advanced = prepare()
        self.assertNotEqual(first.included, advanced.included)
        following.discard()
        self.assertIsInstance(json.loads(json.dumps(account["context_cursors"])), dict)


if __name__ == "__main__":
    unittest.main()
