from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from causal_benchmarks.run_killer_lookup_audit import (
    SCHEMA,
    TASKS,
    main,
    run_killer_lookup_audit,
)


class KillerLookupAuditRunnerTest(unittest.TestCase):
    def test_report_is_four_task_dev_only_and_seed_bound(self) -> None:
        report = run_killer_lookup_audit(episodes=120, seed=23)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(set(report["tasks"]), {task for task, _, _ in TASKS})
        self.assertEqual(report["scored_split"], "dev_only")
        for task, _module, offset in TASKS:
            row = report["tasks"][task]
            binding = row["generator_binding"]
            self.assertEqual(binding["task_seed"], 23 + offset)
            self.assertGreater(binding["train_episodes"], 0)
            self.assertGreater(binding["dev_episodes"], 0)
            self.assertGreaterEqual(binding["test_episodes_not_scored"], 0)
            self.assertEqual(row["evaluation_split"], "dev_only")
            self.assertEqual(
                set(row["headline"]), {"source_union", "query_signature"}
            )
            for arm in row["headline"].values():
                for field in (
                    "affected_precision",
                    "affected_exact_match",
                    "sufficient_mask_rate",
                    "unaffected_specificity",
                    "mean_write_fraction",
                ):
                    self.assertIn(field, arm)

    def test_cli_writes_requested_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "killer.json"
            self.assertEqual(
                main(
                    [
                        "--episodes",
                        "120",
                        "--seed",
                        "23",
                        "--out",
                        str(output),
                    ]
                ),
                0,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], SCHEMA)
            self.assertEqual(payload["scored_split"], "dev_only")


if __name__ == "__main__":
    unittest.main()
