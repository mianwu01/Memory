from __future__ import annotations

import unittest

from yujia_simulation_v2 import FAMILIES, generate, run_suite


class YujiaSimulationV2Test(unittest.TestCase):
    def test_deterministic_known_dgp(self):
        first = generate("mlp_latent", episodes=8, seed=3)
        second = generate("mlp_latent", episodes=8, seed=3)
        self.assertEqual(first["gold"], second["gold"])
        self.assertEqual(first["trajectories"].tolist(), second["trajectories"].tolist())
        self.assertEqual(first["gold"]["read_latent"], ["h"])

    def test_small_multifamily_suite(self):
        report = run_suite(seeds=range(2), episodes=80, delta=7)
        self.assertEqual(set(report["families"]), set(FAMILIES))
        self.assertIn("grouped_proxy_fallback", report["summary"]["mlp_latent"])
        for family in FAMILIES:
            self.assertEqual(len(report["families"][family]), 2)
            self.assertGreaterEqual(
                report["summary"][family]["regime_conditioned"]["read_f1_mean"],
                report["summary"][family]["pooled"]["read_f1_mean"],
            )


if __name__ == "__main__":
    unittest.main()
