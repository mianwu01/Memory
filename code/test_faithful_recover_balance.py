import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import faithful_recover_balance as recover


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


class BalanceRecoveryPlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = self.root / "results/development/fam"
        write(self.base / "travel/noGcompact_101/status.json", {"complete": True})
        write(self.base / "travel/query_only_101/status.json", {"complete": True})
        write(self.base / "travel/ours_101/status.json", {"complete": False})
        write(self.base / "native/amem/validation.json", {"passed": False})
        write(self.base / "native/lightmem/validation.json", {"passed": False})

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_incomplete_gates_are_retried(self):
        travel, native = recover.plan(self.base, include_native=True)
        self.assertNotIn("noGcompact", travel)
        self.assertNotIn("query_only", travel)
        self.assertEqual(len(travel), 8)
        self.assertEqual(native, ["mem0", "amem", "lightmem"])

    def test_deferring_native_launches_travel_only(self):
        travel, native = recover.plan(self.base, include_native=False)
        self.assertEqual(len(travel), 8)
        self.assertEqual(native, [])

    def test_amem_amendment_redirects_native_source(self):
        write(self.base / "amem_budget_amendment.json", {"new_native_output": "native_amem_budget16k"})
        write(self.base / "native_amem_budget16k/validation.json", {"passed": True})
        _, native = recover.plan(self.base, include_native=True)
        self.assertEqual(native, ["mem0", "lightmem"])

    def test_registered_paths_cannot_escape_roots(self):
        with mock.patch.object(recover, "ROOT", self.root):
            self.assertEqual(recover.load_registered_path("probe.json"), self.root / "probe.json")
            with self.assertRaises(ValueError):
                recover.load_registered_path("../probe.json")
            with self.assertRaises(ValueError):
                recover.load_registered_path("/tmp/probe.json")
            with self.assertRaises(ValueError):
                recover.recovery_output(self.base, "../other")

    def test_amendment_binds_route_workers_and_probe_hashes(self):
        generation_path = self.root / "generation.json"
        concurrency_path = self.root / "concurrency.json"
        write(generation_path, {"schema": "faithful-memory-generation-probe/v1", "passed": True,
                                "endpoint": "https://aiaaa.cc/v1", "model": "deepseek-v4-flash-0731"})
        write(concurrency_path, {"schema": "faithful-memory-concurrency-probe/v1",
                                 "endpoint": "https://aiaaa.cc/v1", "model": "deepseek-v4-flash-0731",
                                 "levels": [{"concurrency": 8, "failed": 0}]})
        amendment = {"schema": "faithful-memory-balance-recovery/v1",
                     "endpoint": "https://aiaaa.cc/v1", "model": "deepseek-v4-flash-0731", "workers": 8,
                     "generation_probe_record": "generation.json",
                     "generation_probe_sha256": recover.digest(generation_path),
                     "concurrency_probe_record": "concurrency.json",
                     "concurrency_probe_sha256": recover.digest(concurrency_path)}
        environment = {"OPENAI_BASE_URL": "https://aiaaa.cc/v1", "OPENAI_MODEL": "deepseek-v4-flash-0731"}
        with mock.patch.object(recover, "ROOT", self.root), mock.patch.dict(os.environ, environment, clear=False):
            recover.validate_amendment(self.base, amendment, 8)
            with self.assertRaises(ValueError):
                recover.validate_amendment(self.base, amendment, 9)
            generation_path.write_text("{}")
            with self.assertRaises(ValueError):
                recover.validate_amendment(self.base, amendment, 8)


if __name__ == "__main__":
    unittest.main()
