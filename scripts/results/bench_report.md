# zk_api_credits Benchmark Report

Generated: 2026-02-14 22:49:22 UTC

## Inputs

- summary: `scripts/results/bench_summary.csv`
- relation_counts: `scripts/results/relation_counts.csv`

## Summary by Depth

| depth | samples | prove_wall_ms_min | prove_wall_ms_p50 | prove_wall_ms_p95 | prove_wall_ms_max | prove_wall_ms_avg | prove_log_ms_min | prove_log_ms_p50 | prove_log_ms_p95 | prove_log_ms_max | prove_log_ms_avg | verify_wall_ms_min | verify_wall_ms_p50 | verify_wall_ms_p95 | verify_wall_ms_max | verify_wall_ms_avg | proof_size_bytes_min | proof_size_bytes_p50 | proof_size_bytes_max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 5 | 19934 | 26243 | 33383 | 33383 | 26435 | 19830 | 26100 | 32670 | 32670 | 26124 | 81 | 90 | 104 | 104 | 90 | 14048899 | 14048899 | 14048899 |
| 16 | 5 | 15951 | 17688 | 43066 | 43066 | 26114 | 15540 | 17230 | 41470 | 41470 | 25378 | 119 | 373 | 458 | 458 | 323 | 14349849 | 14349849 | 14349849 |
| 20 | 5 | 14968 | 16245 | 27244 | 27244 | 18103 | 14870 | 16130 | 27110 | 27110 | 17990 | 71 | 80 | 116 | 116 | 84 | 14436847 | 14436847 | 14436847 |
| 32 | 5 | 15659 | 19466 | 21843 | 21843 | 19214 | 15570 | 19360 | 21720 | 21720 | 19112 | 63 | 74 | 99 | 99 | 75 | 14472551 | 14472551 | 14472551 |

## Verifier Relation Counts (representative successful run per depth)

| depth | Cube252 | MemoryAddressToId | MemoryIdToBig | Opcodes | Poseidon3PartialRoundsChain | PoseidonFullRoundChain | PoseidonRoundKeys | RangeCheckFelt252Width27 | RangeCheck_11 | RangeCheck_18 | RangeCheck_19 | RangeCheck_3_3_3_3_3 | RangeCheck_4_3 | RangeCheck_4_4 | RangeCheck_4_4_4_4 | RangeCheck_7_2_5 | RangeCheck_8 | RangeCheck_9_9 | VerifyInstruction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 3904 | 4016 | 2864 | 1296 | 1056 | 320 | 1280 | 3136 | 48 | 36864 | 230304 | 1600 | 512 | 3168 | 6336 | 512 | 32 | 198144 | 1296 |
| 16 | 7808 | 6032 | 3856 | 2096 | 2112 | 640 | 2560 | 6272 | 48 | 73728 | 459712 | 3200 | 512 | 6336 | 12672 | 512 | 64 | 390656 | 2096 |
| 20 | 7808 | 7728 | 5552 | 2640 | 2112 | 640 | 2560 | 6272 | 48 | 73728 | 460608 | 3200 | 512 | 6336 | 12672 | 512 | 64 | 396288 | 2640 |
| 32 | 15616 | 11440 | 7088 | 4112 | 4224 | 1280 | 5120 | 12544 | 48 | 147456 | 919424 | 6400 | 512 | 12672 | 25344 | 512 | 128 | 781312 | 4112 |

