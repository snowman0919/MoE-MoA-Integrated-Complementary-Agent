from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/restore-vllm-executor.sh"
DROPIN = Path(__file__).parents[1] / "config/executor-vllm-restore.conf"


def test_restore_is_approval_gated_and_uses_calling_users_bus() -> None:
    source = SCRIPT.read_text()

    assert "DGX_MOA_RESTORE_ACK" in source
    assert 'runtime_uid="${SUDO_UID:-$(id -u)}"' in source
    assert 'runtime_dir="/run/user/$runtime_uid"' in source
    assert 'DBUS_SESSION_BUS_ADDRESS="$runtime_bus"' in source
    assert "run_as_runtime_user systemctl --user" in source
    assert "stop candidate container before vLLM restore" in source


def test_restore_defaults_to_executor_only_and_verifies_vllm() -> None:
    source = SCRIPT.read_text()

    assert "DGX_MOA_RESTORE_SPECIALISTS:-0" in source
    assert '== *"/vllm serve "*' in source
    assert 'wait-model.sh" executor' in source
    assert DROPIN.read_text() == ("[Service]\nEnvironment=DGX_MOA_EXECUTOR_BACKEND=vllm\n")
