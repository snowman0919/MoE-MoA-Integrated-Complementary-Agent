# User Services

Install and validate:

```bash
scripts/install-systemd-user.sh
systemctl --user enable dgx-moa-resident.target
systemctl --user start dgx-moa.target
scripts/systemd-status.sh
```

Units: `dgx-moa-gateway.service`, `dgx-moa-executor.service`,
`dgx-moa-planner.service`, `dgx-moa-reviewer.service`, and
`dgx-moa-judge.service`. Targets: `dgx-moa.target`,
`dgx-moa-resident.target`, and `dgx-moa-judge.target`.

Resident and judge targets conflict. Model services use loopback ports and
systemd user journald. `MAX_JOBS=1` serializes FlashInfer CUDA JIT; concurrent
`cicc` processes previously exhausted unified memory. `ProtectHome=read-only`
and explicit cache `ReadWritePaths` are tested with the active profile.

Check lifecycle and logs:

```bash
systemctl --user status dgx-moa.target
journalctl --user -u dgx-moa-gateway.service
journalctl --user -u dgx-moa-executor.service
scripts/switch-profile.sh judge
scripts/switch-profile.sh restore
```

User lingering was not changed automatically. Inspect with
`loginctl show-user "$USER" -p Linger`; enable it manually with
`sudo loginctl enable-linger kotori9` if boot-persistent services are wanted.
