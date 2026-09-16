"""Offline checks of experiment integrity; no external API or GPU."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from arena_recent_memory import Ledger, RecentMemory, ROOT
from arena_e2e_inherit import strip_decoder_base_from_memory_context
from yujia_meeting_artifacts import risk_case, setting_audit, travel_case


class IntegrityTests(unittest.TestCase):
    def test_same_history_selector_and_graph_ablation(self):
        case = travel_case(ROOT / "results/development/p2_recent_baselines_v0_debug")
        self.assertEqual(case["episode_id"], 101)
        self.assertEqual(len(case["prior_chunks"]), 2)
        self.assertTrue(all(c["name"] != "Jennifer" for c in case["prior_chunks"]))
        selected = case["selected_cells"]
        self.assertTrue(any(x["traveler"] == "Karen" and x["day"] == 2 and x["slot"] == "lunch" for x in selected))
        all_values = {(x["traveler"],x["day"],x["slot"],x["value"]) for x in case["all_cells"]}
        self.assertTrue(all((x["traveler"],x["day"],x["slot"],x["value"]) in all_values for x in selected))
        self.assertLess(len(selected),len(case["all_cells"]))

    def test_episode_memory_and_public_decoder_isolation(self):
        graph = str(ROOT / "results/real/p2_compact_v3/travel_learned_graph_holdout_111_120.json")
        with TemporaryDirectory() as tmp:
            a = RecentMemory("noGcompact", "data_101_test", tmp, graph)
            b = RecentMemory("noGcompact", "data_102_test", tmp, graph)
            chunk = json.dumps({"name":"Penny", "is_base_person":True,
                "final_plan":"=== Penny's Plan ===\nDay 1:\nBreakfast: Canary Bakery, Austin(Texas)"})
            a.add(chunk)
            self.assertNotIn("Canary Bakery", b.wrap_user_prompt("Breakfast on day 1"))
            self.assertNotEqual(a.store, b.store)
            self.assertEqual(a.backend.compact_serialization, True)
            self.assertEqual(a.backend.ablate_graph, True)

    def test_api_instrumentation_schema_and_accounting(self):
        calls = []
        response = SimpleNamespace(usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens":10,"completion_tokens":2}),
            model="deepseek-v4-flash", choices=[SimpleNamespace(finish_reason="stop",message=SimpleNamespace(content='{"ids":["0"]}'))])
        def create(**kwargs):
            calls.append(kwargs)
            return response
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with TemporaryDirectory() as tmp:
            ledger = Ledger(tmp,"amem",101,"instance")
            ledger.instrument(client)
            schema={"type":"object","properties":{"ids":{"type":"array","items":{"type":"string"}}}}
            client.chat.completions.create(messages=[{"role":"user","content":"test"}],
                response_format={"type":"json_schema","json_schema":{"schema":schema}})
            self.assertEqual(calls[0]["response_format"],{"type":"json_object"})
            self.assertIn('"string"', calls[0]["messages"][-1]["content"])
            self.assertEqual(calls[0]["extra_body"]["thinking"]["type"],"disabled")
            row=json.loads((Path(tmp)/"memory_events.jsonl").read_text())
            self.assertEqual(row["usage"]["prompt_tokens"],10)
            self.assertEqual(ledger.failed_calls,0)
            response.choices[0].message.content = '{"ids":[0]}'
            import jsonschema
            with self.assertRaises(jsonschema.ValidationError):
                client.chat.completions.create(messages=[{"role":"user","content":"test"}],
                    response_format={"type":"json_schema","json_schema":{"schema":schema}})
            self.assertEqual(ledger.failed_calls,1)

    def test_real_risk_trace_and_identifiability_boundary(self):
        case=risk_case()
        self.assertEqual(case["normal"]["answer"],"C")
        self.assertEqual(case["triggered"]["answer"],"H")
        self.assertEqual(case["triggered"]["groundtruth"],"D")
        self.assertGreater(len(case["triggered"]["retrieved"]),1)
        audit=setting_audit()
        self.assertFalse(audit["identifiability_established_on_real_data"])
        self.assertEqual(audit["n_variables"],7)


if __name__ == "__main__":
    unittest.main()
