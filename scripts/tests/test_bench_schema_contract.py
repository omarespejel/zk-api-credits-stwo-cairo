import csv
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCHEMA_MODULE = importlib.import_module("scripts.bench.schema_contract")
DELTA_MODULE = importlib.import_module("scripts.bench.build_v1_v2_delta")

read_p50 = SCHEMA_MODULE.read_p50
validate_summary_headers = SCHEMA_MODULE.validate_summary_headers


def write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    """Write a CSV file from headers and row lists (test helper)."""
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


class BenchSchemaContractTests(unittest.TestCase):
    def test_validate_summary_headers_accepts_baseline_schema(self):
        """Legacy baseline column names (prove_wall_ms_p50 etc.) pass validation."""
        rows = [
            {
                "run_tag": "run1",
                "prover_engine": "cairo-prove",
                "profile": "release",
                "depth": "8",
                "samples": "1",
                "prove_wall_ms_p50": "100",
                "verify_wall_ms_p50": "10",
                "proof_size_bytes_p50": "200",
            }
        ]
        validate_summary_headers(rows, "baseline")

    def test_validate_summary_headers_accepts_compact_schema(self):
        rows = [
            {
                "run_tag": "run1",
                "prover_engine": "scarb-prove",
                "profile": "release",
                "depth": "8",
                "samples": "1",
                "prove_p50_ms": "100",
                "verify_p50_ms": "10",
                "size_p50_bytes": "200",
            }
        ]
        validate_summary_headers(rows, "compact")

    def test_validate_summary_headers_rejects_missing_metric(self):
        """Missing size metric column raises KeyError."""
        rows = [
            {
                "run_tag": "run1",
                "prover_engine": "scarb-prove",
                "profile": "release",
                "depth": "8",
                "samples": "1",
                "prove_p50_ms": "100",
                "verify_p50_ms": "10",
            }
        ]
        with self.assertRaises(KeyError):
            validate_summary_headers(rows, "missing-size")

    def test_read_p50_resolves_aliases(self):
        """read_p50 returns correct float from both legacy and compact column names."""
        old_row = {"prove_wall_ms_p50": "123"}
        new_row = {"prove_p50_ms": "456"}
        self.assertEqual(read_p50(old_row, "prove"), 123.0)
        self.assertEqual(read_p50(new_row, "prove"), 456.0)

    def test_build_delta_cli_handles_mixed_schemas(self):
        """Delta builder works when baseline uses legacy and v2 uses compact columns."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "baseline.csv"
            v2 = tmp_path / "v2.csv"
            out = tmp_path / "delta.csv"

            write_csv(
                baseline,
                [
                    "run_tag",
                    "prover_engine",
                    "profile",
                    "target",
                    "machine",
                    "depth",
                    "samples",
                    "prove_wall_ms_p50",
                    "verify_wall_ms_p50",
                    "proof_size_bytes_p50",
                ],
                [["run1", "cairo-prove", "release", "zk_api_credits", "m", "8", "1", "100", "10", "200"]],
            )
            write_csv(
                v2,
                [
                    "run_tag",
                    "prover_engine",
                    "profile",
                    "target",
                    "machine",
                    "depth",
                    "samples",
                    "prove_p50_ms",
                    "verify_p50_ms",
                    "size_p50_bytes",
                ],
                [["run2", "scarb-prove", "release", "zk_api_credits_v2_kernel", "m", "8", "1", "150", "15", "220"]],
            )

            # Invoke module main through argv-style patching.
            argv_backup = list(sys.argv)
            try:
                sys.argv = [
                    "build_v1_v2_delta.py",
                    "--baseline-summary",
                    str(baseline),
                    "--v2-summary",
                    str(v2),
                    "--out",
                    str(out),
                ]
                rc = DELTA_MODULE.main()
            finally:
                sys.argv = argv_backup

            self.assertEqual(rc, 0)
            with out.open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["depth"], "8")
            self.assertEqual(rows[0]["v1_prove_p50_ms"], "100")
            self.assertEqual(rows[0]["v2_prove_p50_ms"], "150")

    def test_build_delta_cli_zero_baseline_emits_nan_delta(self):
        """Zero baseline prove value produces NaN delta instead of crashing."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "baseline.csv"
            v2 = tmp_path / "v2.csv"
            out = tmp_path / "delta.csv"

            write_csv(
                baseline,
                [
                    "run_tag",
                    "prover_engine",
                    "profile",
                    "target",
                    "machine",
                    "depth",
                    "samples",
                    "prove_wall_ms_p50",
                    "verify_wall_ms_p50",
                    "proof_size_bytes_p50",
                ],
                [["run1", "cairo-prove", "release", "zk_api_credits", "m", "8", "1", "0", "10", "200"]],
            )
            write_csv(
                v2,
                [
                    "run_tag",
                    "prover_engine",
                    "profile",
                    "target",
                    "machine",
                    "depth",
                    "samples",
                    "prove_p50_ms",
                    "verify_p50_ms",
                    "size_p50_bytes",
                ],
                [["run2", "scarb-prove", "release", "zk_api_credits_v2_kernel", "m", "8", "1", "150", "15", "220"]],
            )

            argv_backup = list(sys.argv)
            try:
                sys.argv = [
                    "build_v1_v2_delta.py",
                    "--baseline-summary",
                    str(baseline),
                    "--v2-summary",
                    str(v2),
                    "--out",
                    str(out),
                ]
                rc = DELTA_MODULE.main()
            finally:
                sys.argv = argv_backup

            self.assertEqual(rc, 0)
            with out.open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["prove_delta_pct"].lower(), "nan")


if __name__ == "__main__":
    unittest.main()
