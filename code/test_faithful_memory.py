import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from faithful_memory import InvalidExecution, Runtime, StructuredMemory, request_mode_parameters


class FidelityGates(unittest.TestCase):
    def test_relay_mode_fix_is_separate_from_original_actor_and_output_budget(self):
        self.assertEqual(request_mode_parameters("https://aiaaa.cc/v1", "actor", "default"), {})
        for phase in ("memory_write", "memory_read", "native_qa"):
            mode = request_mode_parameters("https://aiaaa.cc/v1", phase, "default")
            self.assertEqual(mode["reasoning_effort"], "none")
            self.assertNotIn("max_tokens", mode)

    def test_actor_budget_failure_is_retained_but_memory_truncation_is_rejected(self):
        result = SimpleNamespace(usage={"completion_tokens": 32768},
                                 choices=[SimpleNamespace(finish_reason="length")])
        with tempfile.TemporaryDirectory() as tmp:
            r = Runtime(Path(tmp) / "run", "ours", "test")
            r.phase = "actor"
            r.validate_completion(result)
            self.assertFalse(r.failures)
            self.assertEqual(r.counts["actor_generation_failure"], 1)
            r.phase = "memory_write"
            with self.assertRaises(InvalidExecution):
                r.validate_completion(result)

    def test_silent_native_compression_error_rejects_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Runtime(Path(tmp) / "run", "lightmem", "test")
            with self.assertRaises(InvalidExecution):
                with r.native_call():
                    print("compress error, skip this message:")

    def test_query_only_isolates_graph_edges_with_same_base_and_parser(self):
        base = "=== Base's Plan ===\nDay 1:\nBreakfast: Base Cafe, Oslo\nLunch: Base Lunch, Oslo"
        karen = "=== Karen's Plan ===\nDay 1:\nBreakfast: Karen Cafe, Oslo\nLunch: Karen Lunch, Oslo"
        records = [dict(name="Base", query="Base itinerary", final_plan=base, is_base_person=True),
                   dict(name="Karen", query="Change breakfast and lunch on day 1", final_plan=karen)]
        query = "I want first-day lunch with a higher rating than Karen's first-day lunch."
        with tempfile.TemporaryDirectory() as tmp:
            outputs, selected = {}, {}
            for arm in ("ours", "query_only", "noGcompact"):
                memory = StructuredMemory(arm, Runtime(Path(tmp) / arm, arm, "test"))
                for row in records:
                    memory.add(json.dumps(row))
                outputs[arm] = memory.wrap_user_prompt(query)
                selected[arm] = memory.backend._ancestors_of(query)
                self.assertIn(base, outputs[arm])
                self.assertNotIn("decoder_base_itinerary", outputs[arm])
                self.assertNotIn("inheritance_policy", outputs[arm])
            self.assertIn(("Karen", 1, "lunch"), selected["query_only"])
            self.assertNotIn(("Karen", 1, "breakfast"), selected["query_only"])
            self.assertIn(("Karen", 1, "breakfast"), selected["ours"])
            self.assertIn(("Karen", 1, "breakfast"), selected["noGcompact"])


if __name__ == "__main__":
    unittest.main()
