import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "check_alignment.py"
SPEC = spec_from_file_location("check_alignment", MODULE_PATH)
MODULE = module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

check_alignment = MODULE.check_alignment
parse_program_output = MODULE.parse_program_output
to_args = MODULE.to_args


class InteropHelperTests(unittest.TestCase):
    def test_parse_program_output(self):
        text = """
blah
Program output:
1
-2
3
Saving output to: target/execute/foo
"""
        self.assertEqual(parse_program_output(text), [1, -2, 3])

    def test_parse_program_output_raises_on_missing_block(self):
        with self.assertRaises(ValueError):
            parse_program_output("no output here")

    def test_to_args(self):
        self.assertEqual(to_args([42, 0, -5]), "42,0,-5")

    def test_check_alignment_ok(self):
        check_alignment(
            {"nullifier": 7, "x": 10, "y": 20, "root": 30},
            {"x": 10, "scope": 5, "y": 20, "root": 30, "nullifier": 7},
            30,
        )

    def test_check_alignment_mismatch(self):
        with self.assertRaises(AssertionError):
            check_alignment(
                {"nullifier": 7, "x": 10, "y": 20, "root": 30},
                {"x": 10, "scope": 5, "y": 999, "root": 30, "nullifier": 7},
                30,
            )


if __name__ == "__main__":
    unittest.main()
