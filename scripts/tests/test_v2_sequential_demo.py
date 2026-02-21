import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "v2_sequential_demo.py"
SPEC = spec_from_file_location("v2_sequential_demo", MODULE_PATH)
MODULE = module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

build_v2_args = MODULE.build_v2_args
extract_prefix_and_remask = MODULE.extract_prefix_and_remask
parse_proof_path = MODULE.parse_proof_path


class V2SequentialDemoTests(unittest.TestCase):
    def test_extract_prefix_and_remask(self):
        base = [
            "0x2a",
            "0x3",
            "0x3039",
            "0x20",
            "0x20",
            "0x3e8",
            "0x0",
            "0x64",
            "0x0",
            "0x123",
            "0x2",
            "0x111",
            "0x222",
            "0xaa",
            "0x1",
            "0xbb",
            "0x9",
            "0xcc",
            "0xdd",
            "0xee",
            "0xff",
        ]
        prefix, remask = extract_prefix_and_remask(base)
        self.assertEqual(len(prefix), 13)
        self.assertEqual(remask, 9)

    def test_build_v2_args_rewrites_ticket_scope_and_tail(self):
        prefix = [42, 3, 12345, 32, 32, 1000, 0, 100, 0, 999, 0]
        remask_nonce = 9
        step = {
            "ticket_index": "0x5",
            "scope": "0x99",
            "refund_commitment_prev": "0x7b",
            "refund_amount": "0x1",
            "refund_commitment_next_expected": "0xabc",
            "server_pubkey": "0x1234",
            "signature_r": "0x5678",
            "signature_s": "0x9abc",
        }

        args = build_v2_args(prefix, remask_nonce, step)
        self.assertEqual(args[1], 5)
        self.assertEqual(args[3], 0x99)
        self.assertEqual(args[-7:], [0x7B, 0x1, 0xABC, 9, 0x1234, 0x5678, 0x9ABC])

    def test_parse_proof_path(self):
        output = "x\ny\nSaving proof to: target/execute/abc/proof/proof.json\nz\n"
        self.assertEqual(parse_proof_path(output), "target/execute/abc/proof/proof.json")

    def test_parse_proof_path_missing_raises(self):
        with self.assertRaises(ValueError):
            parse_proof_path("no proof path here")


if __name__ == "__main__":
    unittest.main()
