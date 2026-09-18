"""Protect denominator, repeated-trial, and accounting rules of the new report."""
import json
from pathlib import Path
import tempfile
import unittest

from autodl_report import (combine_usage, episode_average, matched_coverage,
                           registered_cases, validate_case)
from faithful_report import usage


class ReportTests(unittest.TestCase):
    def test_scope_rejects_missing_or_duplicate_case(self):
        case = dict(key="implicit/ours/111/r0", variant="implicit", arm="ours", id=111, repeat=0)
        protocol = dict(episode_ids=[111], repeats=1, variants={"implicit": ["ours"]}, cases=[case])
        self.assertEqual(registered_cases(protocol), [case])
        for invalid in [[], [case, case]]:
            with self.assertRaises(ValueError):
                registered_cases({**protocol, "cases": invalid})

    def test_repeats_do_not_become_independent_episodes(self):
        repeated = [
            {"111": dict(ps=0, sps=20, sr=0), "112": dict(ps=100, sps=100, sr=100)},
            {"111": dict(ps=100, sps=40, sr=100), "112": dict(ps=100, sps=100, sr=100)},
            {"111": dict(ps=50, sps=60, sr=0), "112": dict(ps=100, sps=100, sr=100)},
        ]
        averaged = episode_average(repeated)
        self.assertEqual(len(averaged), 2)
        self.assertEqual(averaged["111"]["ps"], 50)
        self.assertEqual(averaged["111"]["sps"], 40)
        with self.assertRaises(ValueError):
            episode_average([repeated[0], {"111": repeated[1]["111"]}])

    def test_complete_blocks_require_all_arms_and_repeats(self):
        cases = [dict(key=f"implicit/{arm}/111/r{repeat}", variant="implicit", arm=arm,
                      id=111, repeat=repeat) for arm in ["ours", "full"] for repeat in range(3)]
        keys = {case["key"] for case in cases}
        partial = matched_coverage(cases, keys - {cases[-1]["key"]}, {"implicit": ["ours", "full"]})
        self.assertEqual(partial["implicit"]["complete_episode_blocks"], [])
        complete = matched_coverage(cases, keys, {"implicit": ["ours", "full"]})
        self.assertEqual(complete["implicit"]["complete_episode_blocks"], [111])

    def test_unknown_provider_price_is_not_zero_cost_claim(self):
        row = dict(event="llm", phase="actor", endpoint="https://www.autodl.art/api/v1",
                   usage=dict(prompt_tokens=100, completion_tokens=20), choices=[dict(finish_reason="stop")])
        totals = combine_usage([usage([row]), usage([row])])
        self.assertEqual(totals["calls"], 2)
        self.assertEqual(totals["unpriced_calls"], 2)
        self.assertEqual(totals["input_tokens"], 200)
        self.assertEqual(totals["phases"]["actor"]["output_tokens"], 40)

    def test_missing_person_rejected_even_with_complete_status(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            hashes = {"actor.py": "frozen"}
            contract = dict(event="actor_contract", hashes=hashes, custom_decoder=False,
                            custom_prompt=False, tool_filter=False)
            (folder / "events.jsonl").write_text(json.dumps(contract) + "\n")
            (folder / "status.json").write_text(json.dumps(dict(complete=True, arm="ours", id=111,
                                                                counts={"actor_contract": 1})))
            settings = dict(model="DeepSeek-V4.1-Flash", endpoint="https://www.autodl.art/api/v1",
                            actor_thinking="default", source_hashes={"runner.py": "source"})
            (folder / "provenance.json").write_text(json.dumps(settings))
            submissions = folder / "plans/submission"
            submissions.mkdir(parents=True)
            submission = submissions / "model_submission.jsonl"
            submission.write_text(json.dumps(dict(id=111, persons=[dict(person_idx=0)])) + "\n")
            with self.assertRaisesRegex(ValueError, "denominator"):
                validate_case(folder, dict(arm="ours", id=111), settings, {0, 1}, hashes)
            submission.write_text(json.dumps(dict(id=111, persons=[dict(person_idx=0), dict(person_idx=1)])) + "\n")
            record, _, _ = validate_case(folder, dict(arm="ours", id=111), settings, {0, 1}, hashes)
            self.assertEqual(len(record["persons"]), 2)


if __name__ == "__main__":
    unittest.main()
