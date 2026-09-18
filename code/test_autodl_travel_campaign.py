import json
from pathlib import Path
import tempfile
import unittest

from autodl_travel_campaign import dispatch_limit


class DispatchControl(unittest.TestCase):
    def test_limits_and_pause_do_not_exceed_process_ceiling(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control.json"
            for settings, expected in [
                ({"workers": 64}, 64),
                ({"workers": 96}, 96),
                ({"workers": 96, "pause_dispatch": True}, 0),
            ]:
                path.write_text(json.dumps(settings))
                self.assertEqual(dispatch_limit(path, 128), expected)
            for invalid in (0, 129, -1, True, "64"):
                path.write_text(json.dumps({"workers": invalid}))
                with self.assertRaises(ValueError):
                    dispatch_limit(path, 128)


if __name__ == "__main__":
    unittest.main()
