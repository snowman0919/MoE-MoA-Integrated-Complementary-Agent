from __future__ import annotations

from pathlib import Path

import pytest
from dgx_moa.config import ModelConfig, Settings, load_settings, parse_bool
from pydantic import ValidationError


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on", True, 1])
def test_true_boolean_forms(value) -> None:  # type: ignore[no-untyped-def]
    assert parse_bool(value) is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", False, 0])
def test_false_boolean_forms(value) -> None:  # type: ignore[no-untyped-def]
    assert parse_bool(value) is False


def test_invalid_boolean_rejected(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "sometimes")
    monkeypatch.setenv("DGX_MOA_API_KEY", "valid-test-token")
    with pytest.raises(ValidationError, match="must be one of"):
        load_settings(config)


def test_auth_enabled_requires_real_key() -> None:
    with pytest.raises(ValidationError, match="DGX_MOA_API_KEY"):
        Settings(auth_enabled=True, api_key=None)
    with pytest.raises(ValidationError, match="non-placeholder"):
        Settings(auth_enabled=True, api_key="replace-with-a-long-random-token")


def test_auth_disabled_allows_missing_key() -> None:
    settings = Settings(auth_enabled=False, api_key=None)
    assert settings.api_key is None


def test_bind_environment_overrides(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.delenv("DGX_MOA_API_KEY", raising=False)
    monkeypatch.setenv("DGX_MOA_BIND_HOST", "100.64.1.2")
    monkeypatch.setenv("DGX_MOA_BIND_PORT", "9100")
    settings = load_settings(config)
    assert settings.bind_host == "100.64.1.2"
    assert settings.bind_port == 9100


def test_loop_engineering_environment_is_strict_and_disabled_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_LOOP_ENGINEERING",
        '{"enabled":true,"defaults":{"iterations":2},"no_progress_iteration_limit":1}',
    )

    settings = load_settings(config)

    assert settings.loop_engineering.enabled is True
    assert settings.loop_engineering.defaults["iterations"] == 2
    assert settings.loop_engineering.defaults["tool_calls"] == 30
    assert Settings(auth_enabled=False).loop_engineering.enabled is False


def test_loop_budget_overrides_merge_request_class_then_risk() -> None:
    settings = Settings(
        auth_enabled=False,
        loop_engineering={
            "request_class_overrides": {"recovery_task": {"iterations": 3}},
            "risk_level_overrides": {"high": {"iterations": 2, "frontier_calls": 1}},
        },
    )

    budget = settings.loop_engineering.budget_for("recovery_task", "high")

    assert budget["iterations"] == 2
    assert budget["frontier_calls"] == 1
    assert budget["tool_calls"] == 30


def test_runtime_skills_environment_is_bounded_and_disabled_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_RUNTIME_SKILLS",
        f'{{"enabled":true,"root":"{tmp_path / "skills"}","retrieval_limit":2}}',
    )

    settings = load_settings(config)

    assert settings.runtime_skills.enabled is True
    assert settings.runtime_skills.retrieval_limit == 2
    assert Settings(auth_enabled=False).runtime_skills.enabled is False


def test_remote_judge_requires_explicit_endpoint_and_environment_credential(
    monkeypatch, tmp_path: Path
) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_REMOTE_JUDGE",
        '{"enabled":true,"provider":"nvidia_nim","endpoint":"https://nim.invalid",'
        '"api_key_env":"NVIDIA_API_KEY","max_calls_per_request":2}',
    )

    settings = load_settings(config)

    assert settings.remote_judge.enabled is True
    assert settings.remote_judge.model == "z-ai/glm-5.2"
    assert settings.remote_judge.max_calls_per_request == 2
    assert Settings(auth_enabled=False).remote_judge.enabled is False
    with pytest.raises(ValidationError, match="requires an endpoint"):
        Settings(
            auth_enabled=False,
            remote_judge={"enabled": True, "provider": "nvidia_nim"},
        )


def test_runtime_knowledge_is_separate_bounded_and_disabled_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_RUNTIME_KNOWLEDGE",
        f'{{"enabled":true,"state_db":"{tmp_path / "knowledge.db"}","retrieval_limit":2}}',
    )

    settings = load_settings(config)

    assert settings.runtime_knowledge.enabled is True
    assert settings.runtime_knowledge.retrieval_limit == 2
    assert Settings(auth_enabled=False).runtime_knowledge.enabled is False


def test_runtime_evolution_registry_is_disabled_and_separate_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_RUNTIME_EVOLUTION",
        f'{{"enabled":true,"state_db":"{tmp_path / "evolution.db"}"}}',
    )

    settings = load_settings(config)

    assert settings.runtime_evolution.enabled is True
    assert Settings(auth_enabled=False).runtime_evolution.enabled is False


def test_declarative_policy_environment_is_strict_and_disabled_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_DECLARATIVE_POLICY",
        '{"enabled":true,"version":"test-1","policies":['
        '{"id":"review","when":{"task.review":true},"require":{"reviewer":true}}]}',
    )

    settings = load_settings(config)

    assert settings.declarative_policy.enabled is True
    assert settings.declarative_policy.policies[0].id == "review"
    assert Settings(auth_enabled=False).declarative_policy.enabled is False


def test_live_observation_secrets_are_external_and_hidden(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_LIVE_OBSERVATION",
        '{"enabled":true,"discord":{"webhook_url":"https://discord.invalid/secret"},'
        '"telegram":{"bot_token":"synthetic-token","chat_id":"chat-1"}}',
    )

    settings = load_settings(config)

    assert settings.live_observation.enabled is True
    assert settings.live_observation.discord is not None
    assert "discord.invalid" not in repr(settings.live_observation.discord.webhook_url)
    assert Settings(auth_enabled=False).live_observation.enabled is False


def test_training_store_is_disabled_separate_and_unknown_repositories_fail_closed(
    monkeypatch, tmp_path: Path
) -> None:
    config = tmp_path / "models.yaml"
    config.write_text("gateway: {}\nmodels: {}\n")
    monkeypatch.setenv("DGX_MOA_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGX_MOA_TRAINING_DATA",
        f'{{"enabled":true,"state_db":"{tmp_path / "training.db"}",'
        f'"object_root":"{tmp_path / "objects"}","minimum_free_bytes":0}}',
    )

    settings = load_settings(config)

    assert settings.training_data.enabled is True
    assert settings.training_data.repository_policies == {}
    assert Settings(auth_enabled=False).training_data.enabled is False
    with pytest.raises(ValidationError, match="must be separate"):
        Settings(
            auth_enabled=False,
            state_db=tmp_path / "same.db",
            training_data={"enabled": True, "state_db": tmp_path / "same.db"},
        )


def test_weekly_jobs_use_requested_disabled_seoul_defaults() -> None:
    settings = Settings(auth_enabled=False)

    assert settings.weekly_jobs.enabled is False
    assert settings.weekly_jobs.timezone == "Asia/Seoul"
    assert settings.weekly_jobs.skill_schedule == "0 3 * * 0"
    assert settings.weekly_jobs.package_schedule == "0 2 * * 1"
    assert settings.weekly_jobs.retention.weekly_archive_weeks == 52


def test_model_context_requires_64k(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 65536"):
        ModelConfig(
            repository="test/model",
            revision="abc",
            classification="test",
            base_url="http://127.0.0.1:8104",
            served_name="test",
            destination=tmp_path / "model",
            context_length=65_535,
        )
