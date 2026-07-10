#!/usr/bin/env bash
set -Eeuo pipefail
systemctl --user start dgx-moa-resident.target
