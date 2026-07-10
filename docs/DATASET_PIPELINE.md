# Dataset pipeline

`scripts/build-training-dataset.sh` converts decision points into redacted JSONL.
It supports executor/planner/reviewer, recovery, preference, and failure-class
dataset labels; assigns Gold/Silver/Bronze/Negative/Unknown tiers; defaults to
positive tiers; bounds each retained string; deduplicates; derives deterministic
train/validation/test splits; and writes a SHA-256 manifest. Unknown and
incomplete traces are excluded by default.

No dataset is uploaded or used for training by this repository.
