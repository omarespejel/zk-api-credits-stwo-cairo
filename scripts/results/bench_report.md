# zk_api_credits Benchmark Report

Generated: 2026-02-14 23:38:01 UTC

## Inputs

- summary: `scripts/results/bench_summary.csv`
- relation_counts: `scripts/results/relation_counts.csv`

## Summary by Depth

| depth | samples | prove_wall_ms_min | prove_wall_ms_p50 | prove_wall_ms_p95 | prove_wall_ms_max | prove_wall_ms_avg | prove_log_ms_min | prove_log_ms_p50 | prove_log_ms_p95 | prove_log_ms_max | prove_log_ms_avg | verify_wall_ms_min | verify_wall_ms_p50 | verify_wall_ms_p95 | verify_wall_ms_max | verify_wall_ms_avg | proof_size_bytes_min | proof_size_bytes_p50 | proof_size_bytes_max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 10 | 12267 | 12734 | 17896 | 17896 | 13336 | 12160 | 12630 | 17790 | 17790 | 13235 | 60 | 66 | 71 | 71 | 66 | 14048899 | 14048899 | 14048899 |
| 16 | 10 | 8277 | 8589 | 9405 | 9405 | 8642 | 8170 | 8490 | 9320 | 9320 | 8537 | 63 | 66 | 72 | 72 | 66 | 14349849 | 14349849 | 14349849 |
| 20 | 10 | 10057 | 10400 | 13634 | 13634 | 10737 | 9950 | 10295 | 13490 | 13490 | 10626 | 57 | 64 | 68 | 68 | 63 | 14436847 | 14436847 | 14436847 |
| 32 | 10 | 12662 | 13169 | 15145 | 15145 | 13533 | 12550 | 13060 | 15050 | 15050 | 13428 | 57 | 64 | 72 | 72 | 63 | 14472551 | 14472551 | 14472551 |

## Verifier Relation Counts (representative successful run per depth)

| depth | Cube252 | MemoryAddressToId | MemoryIdToBig | Opcodes | Poseidon3PartialRoundsChain | PoseidonFullRoundChain | PoseidonRoundKeys | RangeCheckFelt252Width27 | RangeCheck_11 | RangeCheck_18 | RangeCheck_19 | RangeCheck_3_3_3_3_3 | RangeCheck_4_3 | RangeCheck_4_4 | RangeCheck_4_4_4_4 | RangeCheck_7_2_5 | RangeCheck_8 | RangeCheck_9_9 | VerifyInstruction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 3904 | 4016 | 2864 | 1296 | 1056 | 320 | 1280 | 3136 | 48 | 36864 | 230304 | 1600 | 512 | 3168 | 6336 | 512 | 32 | 198144 | 1296 |
| 16 | 7808 | 6032 | 3856 | 2096 | 2112 | 640 | 2560 | 6272 | 48 | 73728 | 459712 | 3200 | 512 | 6336 | 12672 | 512 | 64 | 390656 | 2096 |
| 20 | 7808 | 7728 | 5552 | 2640 | 2112 | 640 | 2560 | 6272 | 48 | 73728 | 460608 | 3200 | 512 | 6336 | 12672 | 512 | 64 | 396288 | 2640 |
| 32 | 15616 | 11440 | 7088 | 4112 | 4224 | 1280 | 5120 | 12544 | 48 | 147456 | 919424 | 6400 | 512 | 12672 | 25344 | 512 | 128 | 781312 | 4112 |

