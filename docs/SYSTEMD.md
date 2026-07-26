# User Services

Install only the authenticated gateway and loopback socket:

```bash
scripts/install-systemd-user.sh --start
scripts/systemd-status.sh
scripts/runtime-status.sh
```

The approved isolated maintenance candidate runs Executor and Specialist
inference in pinned SGLang containers on loopback ports `18101` and `18102`.
The installer neither manages those containers nor installs or enables the old
resident/model targets. Candidate execution is not production deployment.

The checked-in vLLM Executor, Planner, Reviewer, Reasoner, Judge units and
targets are rollback assets only. Use only the separately acknowledged restore
scripts after stopping both SGLang containers. They are not a normal profile
switching interface.

Gateway logs:

```bash
journalctl --user -u dgx-moa-gateway.service
```
