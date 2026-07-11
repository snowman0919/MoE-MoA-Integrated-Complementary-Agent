# Dataset pipeline

`scripts/build-training-dataset.sh` converts decision points into redacted JSONL.
It supports executor/planner/reviewer, recovery, preference, and failure-class
dataset labels; assigns Gold/Silver/Bronze/Negative/Unknown tiers; defaults to
positive tiers; bounds each retained string; deduplicates; derives deterministic
train/validation/test splits; and writes a SHA-256 manifest. Unknown and
incomplete traces are excluded by default. V1 traces are legacy and excluded.
V2 records must be explicitly `training_eligibility=eligible`; production and
candidate-evaluation traces require review, while validation and diagnostic
traces are excluded by default. Repository policy may only make handling stricter.

Collection, dataset construction, export, and external training are separate
operations. No dataset is uploaded or used for training by this repository.
