import subprocess
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "check_alignment.py"
SPEC = spec_from_file_location("check_alignment", MODULE_PATH)
MODULE = module_from_spec(SPEC)
if SPEC is None or SPEC.loader is None:
    raise ImportError("Failed to load check_alignment module spec")
SPEC.loader.exec_module(MODULE)

check_alignment = MODULE.check_alignment
parse_program_output = MODULE.parse_program_output
run = MODULE.run
to_args = MODULE.to_args
validate_vector = MODULE.validate_vector


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

    def test_validate_vector_ok(self):
        vector = validate_vector(
            {
                "name": "shared",
                "identity_secret": "42",
                "user_message_limit": 32,
                "ticket_index": 3,
                "x": 12345,
                "scope": 32,
                "deposit_low": "1000",
                "deposit_high": 0,
                "class_price_low": 100,
                "class_price_high": 0,
            },
            Path("vec.json"),
        )
        self.assertEqual(vector["identity_secret"], 42)
        self.assertEqual(vector["user_message_limit"], 32)
        self.assertEqual(vector["name"], "shared")

    def test_validate_vector_missing_required_key(self):
        with self.assertRaisesRegex(ValueError, "missing required key 'identity_secret'"):
            validate_vector(
                {
                    "user_message_limit": 32,
                    "ticket_index": 3,
                    "x": 12345,
                    "scope": 32,
                    "deposit_low": 1000,
                    "deposit_high": 0,
                    "class_price_low": 100,
                    "class_price_high": 0,
                },
                Path("vec.json"),
            )

    def test_validate_vector_invalid_required_type(self):
        with self.assertRaisesRegex(ValueError, "key 'user_message_limit' must be int-coercible"):
            validate_vector(
                {
                    "identity_secret": 42,
                    "user_message_limit": "thirty-two",
                    "ticket_index": 3,
                    "x": 12345,
                    "scope": 32,
                    "deposit_low": 1000,
                    "deposit_high": 0,
                    "class_price_low": 100,
                    "class_price_high": 0,
                },
                Path("vec.json"),
            )

    def test_run_timeout_raises_runtime_error(self):
        with patch.object(
            MODULE.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["scarb", "build"], timeout=1),
        ):
            with self.assertRaisesRegex(RuntimeError, "command timed out"):
                run(["scarb", "build"], Path("."))


if __name__ == "__main__":
    unittest.main()
