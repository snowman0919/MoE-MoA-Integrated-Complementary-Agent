#!/usr/bin/env bash
set -Eeuo pipefail
date --iso-8601=seconds
hostnamectl
uname -a
lscpu
free -b
nvidia-smi
cat /usr/local/cuda/version.json
df -B1 -T "$HOME" /var/lib/docker
docker version
docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L
tailscale version
tailscale status --json
tailscale serve status
hf auth whoami
vllm --version
systemctl --user is-system-running || true
sudo -n true || true
ss -lntup

