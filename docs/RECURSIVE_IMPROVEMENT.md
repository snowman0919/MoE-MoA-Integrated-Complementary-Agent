# Recursive improvement

`scripts/mine-improvements.sh` computes proposals from benchmark evidence without
an LLM. `scripts/create-improvement-branch.sh` only creates isolated worktrees;
it never merges. `scripts/evaluate-improvement.sh` compares fixed baseline and
candidate metrics, then emits a recommendation only.

All merges, deployment, security/network/systemd changes, external uploads, and
adapter promotions require human approval.

The normal post-baseline flow is:

`main` production traces -> miner -> proposal -> `auto/<layer>/<proposal-id>`
worktree from `dev` -> OpenCode driven by stable `main` MoA -> isolated candidate
evaluation -> `recommended_for_dev` or rejected -> dev stabilization -> PR ->
human review -> main deployment.

Evidence priority is explicit and configurable: main production, candidate
evaluation, dev validation, benchmark, then diagnostic. Resolved, expected,
synthetic, false-positive, and superseded failures are excluded by default;
unchanged proposal fingerprints enter cooldown. No recommendation auto-merges.
