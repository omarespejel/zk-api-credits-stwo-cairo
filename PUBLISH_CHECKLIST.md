# Publish Checklist

Use this before sharing benchmark numbers outside the repo.

- [ ] `python3 scripts/ci/preflight.py` passed locally.
- [ ] Numbers come from a single prover engine/profile family.
- [ ] If numbers are mixed across families, use `scripts/bench/combine_tables.py` and keep the generated caveat.
- [ ] Unsupported-path caveats are included (for now: `zk_api_credits_v2_kernel` on raw `cairo-prove`).
- [ ] Verify logs are from the current run tag only (no stale logs).
- [ ] Report includes machine metadata (`machine`, `run_tag`, `prover_engine`, `profile`).
