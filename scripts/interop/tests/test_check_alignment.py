import subprocess
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "check_alignment.py"
SPEC = spec_from_file_location("check_alignment", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError("Failed to load check_alignment module spec")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

check_alignment = MODULE.check_alignment
parse_program_output = MODULE.parse_program_output
resolve_vivian_project_root = MODULE.resolve_vivian_project_root
run = MODULE.run
run_vivian_main = MODULE.run_vivian_main
to_args = MODULE.to_args
validate_vector = MODULE.validate_vector
load_vector = MODULE.load_vector
ensure_repo_dir = MODULE.ensure_repo_dir


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

    def test_parse_program_output_non_integer_line_raises_context(self):
        text = """
Program output:
123
not_a_number
Saving output to: target/execute/foo
"""
        with self.assertRaisesRegex(ValueError, "non-integer program output line"):
            parse_program_output(text)

    def test_to_args(self):
        self.assertEqual(to_args([42, 0, -5]), "42,0,-5")

    def test_check_alignment_ok(self):
        check_alignment(
            {"nullifier": 7, "x": 10, "y": 20, "root": 30},
            {"x": 10, "scope": 5, "y": 20, "root": 30, "nullifier": 7},
            30,
            30,
        )

    def test_check_alignment_mismatch(self):
        with self.assertRaises(AssertionError):
            check_alignment(
                {"nullifier": 7, "x": 10, "y": 20, "root": 30},
                {"x": 10, "scope": 5, "y": 999, "root": 30, "nullifier": 7},
                30,
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
        with self.assertRaisesRegex(ValueError, "key 'user_message_limit' must be an integer value"):
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

    def test_validate_vector_rejects_float(self):
        with self.assertRaisesRegex(ValueError, "must be an integer value, got float"):
            validate_vector(
                {
                    "identity_secret": 42,
                    "user_message_limit": 32.1,
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

    def test_validate_vector_rejects_bool(self):
        with self.assertRaisesRegex(ValueError, "must be an integer value, got bool"):
            validate_vector(
                {
                    "identity_secret": True,
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

    def test_load_vector_reports_json_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{ bad json")
            with self.assertRaisesRegex(ValueError, r"invalid json in vector file .*bad\.json"):
                load_vector(path)

    def test_run_vivian_main_uses_release_profile(self):
        vector = {
            "identity_secret": 42,
            "user_message_limit": 32,
            "ticket_index": 3,
            "x": 12345,
            "scope": 77,
            "vivian_merkle_proof_length": 2,
            "vivian_merkle_proof_indices": [0] * 10,
            "vivian_merkle_proof_siblings": [0] * 10,
            "vivian_expected_root": 999,
        }
        fake_output = "Program output:\n1\n2\n3\n4\n5\nSaving output to: target/execute/foo\n"
        with patch.object(MODULE, "run", return_value=fake_output) as run_mock:
            out = run_vivian_main(Path("."), "scarb", vector)
            cmd = run_mock.call_args.args[0]
            self.assertEqual(cmd[:3], ["scarb", "--release", "execute"])
            self.assertEqual(out["nullifier"], 5)

    def test_resolve_vivian_project_root_prefers_rln_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "rln").mkdir()
            (repo / "rln" / "Scarb.toml").write_text("[package]\nname='x'\n")
            resolved = resolve_vivian_project_root(repo)
            self.assertEqual(resolved, repo / "rln")

    def test_run_timeout_raises_runtime_error(self):
        with patch.object(
            MODULE.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["scarb", "build"], timeout=1),
        ):
            with self.assertRaisesRegex(RuntimeError, "command timed out"):
                run(["scarb", "build"], Path("."))

    def test_run_nonzero_returncode_raises_runtime_error(self):
        mock_result = subprocess.CompletedProcess(
            args=["scarb", "build"], returncode=1, stdout="build failed"
        )
        with patch.object(MODULE.subprocess, "run", return_value=mock_result):
            with self.assertRaisesRegex(RuntimeError, "command failed"):
                run(["scarb", "build"], Path("."))

    def test_ensure_repo_dir_missing_path_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing_repo"
            with self.assertRaisesRegex(FileNotFoundError, "repo path not found"):
                ensure_repo_dir(missing, "vivian")

    def test_ensure_repo_dir_non_directory_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "not_dir.txt"
            file_path.write_text("x")
            with self.assertRaisesRegex(NotADirectoryError, "is not a directory"):
                ensure_repo_dir(file_path, "vivian")


if __name__ == "__main__":
    unittest.main()
