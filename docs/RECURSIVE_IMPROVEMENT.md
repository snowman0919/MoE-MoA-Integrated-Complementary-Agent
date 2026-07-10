# Recursive improvement

`scripts/mine-improvements.sh` computes proposals from benchmark evidence without
an LLM. `scripts/create-improvement-branch.sh` only creates isolated worktrees;
it never merges. `scripts/evaluate-improvement.sh` compares fixed baseline and
candidate metrics, then emits a recommendation only.

All merges, deployment, security/network/systemd changes, external uploads, and
adapter promotions require human approval.
