# Dataset pipeline

`scripts/build-training-dataset.sh` converts completed independently reviewed
decision points into redacted executor SFT JSONL. It assigns Silver quality to
synthetic reviewed tasks, derives deterministic train/validation/test splits, and
writes a SHA-256 manifest. Unknown and incomplete traces are excluded.

No dataset is uploaded or used for training by this repository.
