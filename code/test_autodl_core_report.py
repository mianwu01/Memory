import unittest

from autodl_core_report import derive


class PrespecifiedCore(unittest.TestCase):
    def test_preserves_every_episode_and_repeat_and_requires_full_scope(self):
        protocol = {
            "episode_ids": [111, 112],
            "repeats": 3,
            "variants": {
                "implicit": ["ours", "noGcompact", "query_only", "lightmem"],
                "explicit": ["ours", "noGcompact", "query_only"],
            },
        }
        protocol["cases"] = [
            dict(key=f"{variant}/{arm}/{ident}/r{repeat}", variant=variant, arm=arm,
                 id=ident, repeat=repeat)
            for variant, arms in protocol["variants"].items() for arm in arms
            for ident in protocol["episode_ids"] for repeat in range(3)
        ]
        core = derive(protocol)
        self.assertEqual(len(core["cases"]), 36)
        self.assertEqual(core["episode_ids"], protocol["episode_ids"])
        self.assertEqual(core["repeats"], 3)
        protocol["cases"].pop()
        with self.assertRaises(ValueError):
            derive(protocol)


if __name__ == "__main__":
    unittest.main()
