import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("python_runtime.py")
SPEC = importlib.util.spec_from_file_location("python_runtime", MODULE_PATH)
python_runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(python_runtime)


class PythonRuntimeTests(unittest.TestCase):
    def test_normalize_version_pads_short_values(self):
        self.assertEqual(python_runtime.normalize_version("3.12"), (3, 12, 0))
        self.assertEqual(python_runtime.normalize_version("3.10.7"), (3, 10, 7))

    def test_choose_runtime_prefers_first_candidate_that_meets_min(self):
        candidates = [
            {"label": "env", "version": "3.10.4"},
            {"label": "brew-312", "version": "3.12.1"},
            {"label": "fallback", "version": "3.9.6"},
        ]

        selected = python_runtime.choose_runtime(candidates, "3.10")

        self.assertEqual(selected["label"], "env")
        self.assertTrue(candidates[0]["meets_min"])
        self.assertTrue(candidates[1]["meets_min"])
        self.assertFalse(candidates[2]["meets_min"])

    def test_choose_runtime_falls_back_to_first_candidate_when_none_meet_min(self):
        candidates = [
            {"label": "sys", "version": "3.9.6"},
            {"label": "command", "version": "3.9.1"},
        ]

        selected = python_runtime.choose_runtime(candidates, "3.10")

        self.assertEqual(selected["label"], "sys")
        self.assertFalse(candidates[0]["meets_min"])
        self.assertFalse(candidates[1]["meets_min"])


if __name__ == "__main__":
    unittest.main()
