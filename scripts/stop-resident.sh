#!/usr/bin/env bash
set -Eeuo pipefail
systemctl --user stop dgx-moa-resident.target
