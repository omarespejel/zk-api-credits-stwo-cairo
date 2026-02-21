import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "ci" / "preflight.py"
SPEC = spec_from_file_location("preflight", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError("Failed to load preflight module spec")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

discover_benchmark_contract_paths = MODULE.discover_benchmark_contract_paths


class PreflightPathTests(unittest.TestCase):
    def test_discover_benchmark_contract_paths_filters_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            found = discover_benchmark_contract_paths(root)
            self.assertEqual(found, [])

    def test_discover_benchmark_contract_paths_returns_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "scripts/results/main_baseline/bench_summary.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("run_tag,depth\nr1,8\n")
            found = discover_benchmark_contract_paths(root)
            self.assertEqual(found, [path])


if __name__ == "__main__":
    unittest.main()
