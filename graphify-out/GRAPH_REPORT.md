# Graph Report - MoE-MoA-Integrated-Complementary-Agent  (2026-08-18)

## Corpus Check
- 250 files · ~349,967 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3329 nodes · 9559 edges · 185 communities (132 shown, 53 thin omitted)
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 1885 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `eeb18c66`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- frontier.py
- ExecutionGraphRuntime
- Controller
- StubProvider
- context_projection.py
- test_streaming.py
- SkillRegistry
- create_app
- ApiKeyStore
- UsageStore
- SessionState
- test_lifecycle.py
- remote_judge.py
- observation.py
- test_providers.py
- replay.py
- KnowledgeRegistry
- asyncio
- SpecialistRouter
- Dynamic MoA Production Completion Plan
- ProfileManager
- schemas.py
- api.py
- main
- build_runtime_evidence_snapshot
- LifecycleStore
- properties
- state.py
- run-client-quality-matrix.py
- test_state_routing.py
- weekly.py
- test_training.py
- test_usage.py
- required
- test_specialists.py
- TrainingStore
- config.py
- ExecutorScheduler
- controller.py
- LifecycleCoordinator
- datetime
- lifecycle.py
- required
- required
- Trace Usage and Adaptive Lifecycle Design
- ValueError
- EvolutionRegistry
- overflow_executor.py
- training.py
- required
- SystemdLifecycleDriver
- load_settings
- type
- properties
- security.py
- runtime_status.py
- policy.py
- test_client_quality_matrix.py
- ModelConfig
- ._observe
- ._connect
- conftest.py
- ModelProvider
- properties
- required
- Deterministic Synthetic Baseline
- test_goal_tooling.py
- PolicyEngine
- LiveDashboardHub
- redact
- managed_http_client
- RuntimeMetrics
- ArchiveRegistry
- evidence_graph
- type
- dgx-moa
- LifecycleDriver
- .__call__
- properties
- OwnedByteStream
- improvement.py
- enum
- enum
- properties
- Repository Instructions
- benchmark.py
- capture-opencode-sse.py
- .record_failure
- field_validator
- WeeklyScheduler
- required
- items
- MonkeyPatch
- FailingJudge
- ModelRef
- media_assets
- OpenCodeGoExecutorProvider
- validate
- run-opencode-staging.py
- test_validator_atomically_preserves_sanitized_partial_progress
- evaluate
- Dynamic MoA Operational Boundary
- Fail Closed Policy Enforcement
- Immutable Skill Promotion Gate
- _validate_canonical_json
- main
- enum
- enum
- enum
- evaluate-paired-noninferiority.py
- Human Approval Gate
- message_fingerprint
- All-Role Storage Estimate
- Model Lifecycle Contract
- test_policy_redacts_specialist_state_event_and_evaluation_boundaries
- required
- enum
- enum
- enum
- Model Compatibility
- API Client Modes and Streaming Design
- Unload Mechanism and 64K Design
- agent-trace-v2.json
- enum
- agent-trace-v3.json
- enum
- frontier-result-v1.json
- remote_script
- Normally Resident Executor Policy
- type
- codex-profile.sh
- restart-gateway-drained.sh
- Dynamic MoA v2 Model Inventory
- agent_invocations
- failures
- recommendation_resolutions
- switch-profile.sh
- Adapter Registry
- Live Observation
- Python Gateway Retention Decision
- Authenticated Gateway Security Boundary
- audit-trace-completeness.sh
- benchmark.sh
- build-training-dataset.sh
- create-improvement-branch.sh
- download-models.sh
- estimate-model-storage.sh
- evaluate-adapter.sh
- evaluate-frontier-candidate.sh
- evaluate-improvement.sh
- export-agentic-traces.sh
- frontier-status.sh
- healthcheck.sh
- inspect-environment.sh
- inspect-model-repos.sh
- install-service.sh
- install-systemd-user.sh
- mine-improvements.sh
- register-adapter.sh
- rollback-lifecycle.sh
- run-frontier-codex.sh
- run-mvp-benchmark.sh
- runtime-status.sh
- smoke-test.sh
- start-judge.sh
- start-model.sh
- start-resident.sh
- stop-judge.sh
- stop-legacy-models.sh
- stop-model.sh
- stop-resident.sh
- systemd-status.sh
- uninstall-systemd-user.sh
- validate-opencode-loop.sh
- validate-opencode-synthetic.sh
- verify-models.sh
- verify-profile-stopped.sh
- wait-model.sh
- wait-profile.sh
- Improvement IMP-2026-0001 Not Recommended
- Incomplete Files State
- dgx-moa-agent

## God Nodes (most connected - your core abstractions)
1. `StubProvider` - 289 edges
2. `Controller` - 215 edges
3. `create_app()` - 212 edges
4. `SessionState` - 203 edges
5. `StateStore` - 157 edges
6. `Settings` - 127 edges
7. `client_with_stub()` - 107 edges
8. `lifecycle()` - 88 edges
9. `ExecutionGraphRuntime` - 57 edges
10. `responses_sse()` - 57 edges

## Surprising Connections (you probably didn't know these)
- `test_model_ref_splits_only_the_first_slash_and_accepts_legacy_alias()` --uses--> `ModelRef`  [INFERRED]
  tests/test_config_auth.py → gateway/src/dgx_moa/config.py
- `test_auth_disabled_allows_missing_key()` --uses--> `Settings`  [INFERRED]
  tests/test_config_auth.py → gateway/src/dgx_moa/config.py
- `test_auth_enabled_requires_real_key()` --uses--> `Settings`  [INFERRED]
  tests/test_config_auth.py → gateway/src/dgx_moa/config.py
- `test_executor_scheduler_is_bounded_disabled_and_requires_remote_endpoint()` --uses--> `Settings`  [INFERRED]
  tests/test_config_auth.py → gateway/src/dgx_moa/config.py
- `test_loop_budget_overrides_merge_request_class_then_risk()` --uses--> `Settings`  [INFERRED]
  tests/test_config_auth.py → gateway/src/dgx_moa/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Controlled Improvement Workflow** — agents_branch_roles, agents_knowledge_graph_refresh, agents_recursive_experiment_worktrees, agents_human_approval_gate [EXTRACTED 1.00]
- **Executor-Directed Public API Contract** — agents_executor_authority, readme_public_model_catalog, docs_api_client_modes_native_client_tool_loop, docs_architecture_role_projection_pipeline [EXTRACTED 1.00]
- **Executor Lifecycle Safety Contract** — agents_phase_3_executor_baseline, agents_exact_service_restart_unload, agents_safe_lifecycle_defaults, agents_resident_executor_policy, agents_honest_cold_response_reporting, agents_lifecycle_rollback [EXTRACTED 1.00]
- **Operational Authority Chain** — docs_operations_operations, docs_state_state, docs_validation_validation [EXTRACTED 1.00]
- **Primary Reasoner and Executor Runtime Path** — docs_validation_dgx_moa, docs_validation_reasoner, docs_validation_executor [EXTRACTED 1.00]
- **Runtime Reliability Phases** — docs_superpowers_plans_2026_07_18_api_client_modes_streaming_api_client_modes_plan, docs_superpowers_plans_2026_07_18_lifecycle_usage_trace_lifecycle_usage_plan, docs_superpowers_plans_2026_07_19_memory_unload_64k_memory_unload_plan, docs_superpowers_plans_2026_07_19_phase_4_client_matrix_pr_gate_phase4_client_matrix_plan [EXTRACTED 1.00]
- **Structured Read-Only Role Contracts** — gateway_src_dgx_moa_prompts_planner_planner_contract, gateway_src_dgx_moa_prompts_reviewer_reviewer_contract, gateway_src_dgx_moa_prompts_judge_judge_contract [EXTRACTED 1.00]
- **Quality Evidence Gates** — docs_mvp_validation_synthetic_six_shape_suite, docs_quality_evaluation_paired_noninferiority_gate, docs_remote_judge_bounded_remote_quality_gate, docs_phase_audit_local_phase_evidence [INFERRED 0.75]
- **Dynamic MoA Bounded Collaboration** — docs_moa_orchestration_dynamic_moa_orchestration, docs_frontier_frontier_collaboration, docs_moa_orchestration_bounded_artifacts, docs_decisions_executor_authority [INFERRED 0.85]
- **Governed Promotion Controls** — docs_skill_governance_immutable_skill_promotion_gate, docs_runtime_self_improvement_governed_evolution_registry, docs_recursive_improvement_isolated_improvement_flow, docs_policy_engine_fail_closed_policy_enforcement [INFERRED 0.85]
- **Production Control Boundary** — docs_operations_authenticated_gateway, docs_operations_executor_lifecycle, docs_state_active_executor, docs_state_overflow_executor [INFERRED 0.85]
- **Role Lifecycle and Routing** — docs_model_lifecycle_lifecycle_state_machine, docs_specialist_routing_local_remote_specialist_selection [INFERRED 0.85]
- **Role Model Capacity Planning** — config_models_role_model_topology, data_state_storage_estimate_all_all_role_storage_estimate, data_state_storage_estimate_executor_executor_storage_estimate, data_state_storage_estimate_planner_planner_storage_estimate, data_state_storage_estimate_reviewer_reviewer_storage_estimate, data_state_storage_estimate_judge_judge_storage_estimate [INFERRED 0.85]
- **Role-Specific Training Gates** — training_executor_readme_executor_training_package, training_planner_readme_planner_training_gate, training_reviewer_readme_reviewer_training_gate, docs_training_data_fail_closed_eligibility [INFERRED 0.85]
- **Runtime Evidence Continuity** — docs_evidence_graph_evidence_graph, docs_execution_replay_execution_replay, docs_dataset_pipeline_dataset_pipeline, docs_loop_engineering_loop_engineering [INFERRED 0.85]
- **Evidence-Gated Release Governance** — goal_release_stage_gates, goal_completion_rule, docs_benchmarks_measured_benchmarks [INFERRED 0.95]
- **Phase 3 Executor Safety Contract** — docs_decisions_phase_3_executor_baseline, docs_memory_optimization_memory_optimization, docs_context_tuning_context_tuning, docs_dynamic_moa_concurrent_runtime_incident_20260808_safety_disposition [INFERRED 0.95]

## Communities (185 total, 53 thin omitted)

### Community 0 - "frontier.py"
Cohesion: 0.05
Nodes (95): bounded_external_evidence(), build_frontier_task(), classify_frontier_failure(), codex_command(), codex_usage(), CodexAppServerTurn, CodexOAuthCollaboration, CodexOAuthProvider (+87 more)

### Community 1 - "ExecutionGraphRuntime"
Cohesion: 0.06
Nodes (60): _bounded_ids(), _canonical(), _checkpoint_hash(), compact_session_active_state(), compile_execution_graph(), EdgeType, ExecutionGraph, ExecutionGraphRuntime (+52 more)

### Community 2 - "Controller"
Cohesion: 0.07
Nodes (106): Controller, FrontierCollaborationResult, Phase, StrEnum, StateStore, asyncio, Exception, parametrize (+98 more)

### Community 3 - "StubProvider"
Cohesion: 0.06
Nodes (99): Any, StubProvider, client_with_stub(), Path, test_admin_drain_rejects_new_work_and_can_be_cancelled(), test_admin_exact_replay_is_harness_callable_and_live_comparison_stays_internal(), test_api_validation(), test_auth_enabled_invalid_key_returns_401() (+91 more)

### Community 4 - "context_projection.py"
Cohesion: 0.12
Nodes (26): ContributionRole, _bounded_unique(), _canonical(), CanonicalRequestInput, _content_hash(), _evidence_retention_key(), _hash(), model_contribution() (+18 more)

### Community 5 - "test_streaming.py"
Cohesion: 0.05
Nodes (95): _responses_payload(), is_workspace_objective(), batch_goal_prerequisite_read(), batch_workspace_read(), compatible_edit_call(), completed_chat_sse(), forward_sse(), has_internal_protocol_leak() (+87 more)

### Community 6 - "SkillRegistry"
Cohesion: 0.08
Nodes (38): BaseModel, Connection, field_validator, model_validator, Path, Immutable, versioned Executor procedure; models may only recommend it., RuntimeSkill, SkillCandidateEvaluation (+30 more)

### Community 7 - "create_app"
Cohesion: 0.08
Nodes (68): create_app(), main(), get_settings(), Settings, FakeLifecycleDriver, MockJudgeProvider, TestClient, test_admin_dashboard_controls_executor_and_uses_fallback_while_off() (+60 more)

### Community 8 - "ApiKeyStore"
Cohesion: 0.16
Nodes (6): admin_dependency(), ApiKeyStore, auth_dependency(), Any, Connection, Path

### Community 9 - "UsageStore"
Cohesion: 0.08
Nodes (30): classify_client(), _duration_summary(), _ewma(), lifecycle_statistics(), LifecycleSample, _percentile(), _percentiles(), Any (+22 more)

### Community 10 - "SessionState"
Cohesion: 0.08
Nodes (24): A role-specific view that retains a verifiable link to one canonical snapshot., RoleContextProjection, active_failures(), effective_objective(), has_mcp_server_failure(), pending_goal_prerequisites(), PolicyBlocked, Any (+16 more)

### Community 11 - "test_lifecycle.py"
Cohesion: 0.06
Nodes (113): Limits, block_real_service_commands(), lifecycle(), policy_record(), policy_usage(), policy_usage_from_gaps(), Any, asyncio (+105 more)

### Community 12 - "remote_judge.py"
Cohesion: 0.08
Nodes (33): DisabledJudgeProvider, JudgeCallLimitExceeded, JudgeCriteria, JudgeEdit, JudgeEvidencePackage, JudgeFinding, JudgeProvider, JudgeProviderError (+25 more)

### Community 13 - "observation.py"
Cohesion: 0.08
Nodes (30): ObservationBus, ObservationCommandRequest, ObservationCommandStore, ObservationEvent, ObservationNonceRequest, ObservationProvider, public_event(), Any (+22 more)

### Community 14 - "test_providers.py"
Cohesion: 0.17
Nodes (20): AsyncByteStream, CountingClient, CountingResponse, asyncio, MonkeyPatch, parametrize, test_backend_contract_reports_identity_and_supports_cancel(), test_completion_timeout_has_exact_stage() (+12 more)

### Community 15 - "replay.py"
Cohesion: 0.10
Nodes (35): contradiction_resolutions(), EvidenceEdge, EvidenceNode, Any, BaseModel, Resolve a contradiction by explicit trust rank, preserving deterministic ties., stronger_evidence(), validate_evidence_graph() (+27 more)

### Community 16 - "KnowledgeRegistry"
Cohesion: 0.12
Nodes (24): KnowledgeConfidence, KnowledgeContent, KnowledgeEvidence, KnowledgeLifecycle, KnowledgeMatch, KnowledgeMetrics, KnowledgeProvenance, KnowledgeQuery (+16 more)

### Community 17 - "asyncio"
Cohesion: 0.13
Nodes (44): ChatRequest, assert_no_request_leases(), assert_terminal_evidence(), assert_usage(), chat_endpoint(), direct_chat(), direct_review(), endpoint() (+36 more)

### Community 18 - "SpecialistRouter"
Cohesion: 0.12
Nodes (11): AcquireCallback, _MockProvider, Any, AsyncBaseTransport, Exception, RuntimeError, SpecialistRouter, SpecialistUnavailable (+3 more)

### Community 19 - "Dynamic MoA Production Completion Plan"
Cohesion: 0.05
Nodes (43): Codex OAuth Frontier Configuration, Codex OAuth Frontier Example, Bubblewrap Loopback Blocker, Historical Codex Frontier Candidate-Edit Escalation, Context Tuning, Legacy Profile Tuner, Dataset Pipeline, Training Eligibility (+35 more)

### Community 20 - "ProfileManager"
Cohesion: 0.09
Nodes (32): artifact_provenance_error(), classify_failure(), download_role(), main(), Any, Exception, Path, verify_model() (+24 more)

### Community 21 - "schemas.py"
Cohesion: 0.13
Nodes (22): AdditionalAgentRecommendation, ChatMessage, JudgeVerdict, MandatoryChange, PlannerPlan, PlannerStep, ProfileResponse, Any (+14 more)

### Community 22 - "api.py"
Cohesion: 0.09
Nodes (25): _chat_response_payload(), _coerce_responses_input_messages(), _coerce_responses_tools(), DynamicRoleUnmanagedError, has_matching_tool_result(), ollama_model_ready(), openai_inference_ready(), openai_model_ready() (+17 more)

### Community 23 - "main"
Cohesion: 0.10
Nodes (42): CriterionState, FailureClass, AcceptanceCriterion, begin_iteration(), completion_ready(), consume_budget(), consume_usage(), _drop_unstable_evidence_fields() (+34 more)

### Community 24 - "build_runtime_evidence_snapshot"
Cohesion: 0.23
Nodes (22): build_runtime_evidence_snapshot(), canonical_request_input(), project_role_context(), ProjectionRole, ProjectionStage, runtime_evidence_item(), RuntimeEvidenceKind, evidence_space() (+14 more)

### Community 25 - "LifecycleStore"
Cohesion: 0.19
Nodes (9): InvalidTransitionError, LifecycleLease, LifecycleRecord, LifecycleStore, Any, Connection, Row, StaleTransitionError (+1 more)

### Community 26 - "properties"
Cohesion: 0.06
Nodes (35): acceptance_criteria, allowed_paths, base_commit, forbidden_actions, repository_identity, items, type, additionalProperties (+27 more)

### Community 27 - "state.py"
Cohesion: 0.16
Nodes (28): validate_failure_record(), audit_traces(), export_trace(), final_status(), main(), Any, Path, Build bounded trajectory evidence; never source or hidden-reasoning archives. (+20 more)

### Community 28 - "run-client-quality-matrix.py"
Cohesion: 0.22
Nodes (32): baseline_reasoning_effort(), codex_moa_command(), docker_command(), filtered_env(), git(), hermes_test_evidence(), log_text(), main() (+24 more)

### Community 29 - "test_state_routing.py"
Cohesion: 0.12
Nodes (23): ExecutorProvider, classify_request(), optional_roles(), Any, RequestClass, RuntimeMode, Return deterministic route and machine-readable reasons., Select and pin one Executor provider using the legacy priority contract. (+15 more)

### Community 30 - "weekly.py"
Cohesion: 0.14
Nodes (22): assess_candidate(), model_validator, TrainingCandidate, classify_knowledge(), knowledge_overlap(), prepare_candidates(), Any, BaseModel (+14 more)

### Community 31 - "test_training.py"
Cohesion: 0.17
Nodes (29): candidate_from_trace(), candidates_from_trace(), ContentStore, TrainingCollector, RepositoryTrainingPolicy, eligible_trace(), parametrize, Path (+21 more)

### Community 32 - "test_usage.py"
Cohesion: 0.19
Nodes (31): finalization(), Any, MonkeyPatch, parametrize, Path, read_sqlite_files(), start_record(), test_active_request_count_is_not_limited_by_statistics_window() (+23 more)

### Community 33 - "required"
Cohesion: 0.07
Nodes (29): context_configuration, events, metrics, model_revisions, type, completion_evidence, final_status, objective (+21 more)

### Community 34 - "test_specialists.py"
Cohesion: 0.23
Nodes (23): MockPlannerProvider, MockReviewerProvider, SimpleNamespace, config(), ContextAwarePlannerProvider, Any, asyncio, MonkeyPatch (+15 more)

### Community 35 - "TrainingStore"
Cohesion: 0.17
Nodes (5): now(), Connection, Path, TrainingStore, ReviewState

### Community 36 - "config.py"
Cohesion: 0.18
Nodes (16): ExecutionGraphConfig, LiveObservationConfig, ModelRoutingConfig, ObservationControlConfig, BaseModel, RemoteJudgeConfig, RetentionConfig, RuntimeEvolutionConfig (+8 more)

### Community 37 - "ExecutorScheduler"
Cohesion: 0.15
Nodes (15): Future, ExecutorAdmission, ExecutorQueueFull, ExecutorQueueTimeout, ExecutorScheduler, ExecutorSchedulingError, RuntimeError, _Queued (+7 more)

### Community 38 - "controller.py"
Cohesion: 0.08
Nodes (38): EvidenceNodeType, clean_tool_output(), embedded_tool_exit_code(), FrontierRequiredUnavailable, JudgeCorrectionRequired, JudgeRequired, LoopAdmissionError, normalize_tool_result() (+30 more)

### Community 39 - "LifecycleCoordinator"
Cohesion: 0.14
Nodes (8): LifecyclePolicy, LifecycleCoordinator, Apply an explicit operator enable/disable to one managed role., UnknownRoleError, GuardKind, LifecycleMode, RequestLeaseKind, Task

### Community 40 - "datetime"
Cohesion: 0.21
Nodes (25): datetime, candidate_path(), previous_complete_week(), payload(), test_frozen_paired_bootstrap_passes_only_complete_covered_matrix(), test_missing_or_incomplete_pair_fails_closed_without_exclusion(), candidate(), fake_7z() (+17 more)

### Community 41 - "lifecycle.py"
Cohesion: 0.09
Nodes (25): calculate_idle_policy(), _configured_quantile(), _idle_bounds(), IdlePolicyDecision, LifecycleError, LifecycleFailureEvent, LifecycleLoadError, LifecycleNotReadyError (+17 more)

### Community 42 - "required"
Cohesion: 0.08
Nodes (25): Bronze, chosen, Gold, Negative, quality_tier, Silver, split, test (+17 more)

### Community 43 - "required"
Cohesion: 0.08
Nodes (25): context, controller, evidence, infrastructure, model, proposal_id, proposed_change, requires_human_approval (+17 more)

### Community 44 - "Trace Usage and Adaptive Lifecycle Design"
Cohesion: 0.08
Nodes (24): Trace Usage and Lifecycle Plan, Role-Aware Adaptive Lifecycle Gap-Closure Plan, Lifecycle Activity Guards, Trace Usage and Adaptive Lifecycle Design, Single-Flight Cold Loading, External Lifecycle Control, External Ollama Reasoner Lifecycle Design, Nonblocking Systemd Activation (+16 more)

### Community 45 - "ValueError"
Cohesion: 0.18
Nodes (6): default_lifecycle_roles(), ExecutorSchedulingConfig, LifecycleRolePolicy, Any, model_validator, ValueError

### Community 46 - "EvolutionRegistry"
Cohesion: 0.11
Nodes (19): ArtifactKind, ArtifactState, EvolutionArtifact, EvolutionCandidateGenerator, EvolutionEvaluation, EvolutionRegistry, EvolutionSignal, BaseModel (+11 more)

### Community 47 - "overflow_executor.py"
Cohesion: 0.25
Nodes (9): OpenAICompatibleExecutorProvider, OverflowExecutorInvalidOutput, OverflowExecutorModelFailure, OverflowExecutorUnavailable, Any, RuntimeError, OpenAI-compatible remote Executor fallback with model-only rollback., Provider-wide failure: retrying another model on the provider is pointless. (+1 more)

### Community 48 - "training.py"
Cohesion: 0.13
Nodes (19): is_sensitive_key(), CandidateQualityReport, CandidateReviewRequest, detect_language(), execution_graph_training_projection(), near_duplicate(), normalized_text(), Any (+11 more)

### Community 49 - "required"
Cohesion: 0.09
Nodes (23): agent_artifacts, agent_invocations, derived_confidence, evidence_graph, orchestration_decisions, reasoner_contributions, recommendation_resolutions, agent_decisions (+15 more)

### Community 50 - "SystemdLifecycleDriver"
Cohesion: 0.30
Nodes (4): DriverErrorKind, DriverOperation, LifecycleDriverError, SystemdLifecycleDriver

### Community 51 - "load_settings"
Cohesion: 0.06
Nodes (68): load_settings(), parse_bool(), Path, atomic_disable_lifecycle(), _fsync_directory(), main(), Path, rollback() (+60 more)

### Community 52 - "type"
Cohesion: 0.09
Nodes (22): items, type, items, type, type, items, type, agent_artifacts (+14 more)

### Community 53 - "properties"
Cohesion: 0.10
Nodes (21): items, type, type, type, type, type, properties, agent_decisions (+13 more)

### Community 54 - "security.py"
Cohesion: 0.15
Nodes (12): FastAPI, AdminCodexRequest, AdminCodexRunner, Any, BaseModel, Path, ApiKeyRequest, ApiKeyUpdate (+4 more)

### Community 55 - "runtime_status.py"
Cohesion: 0.21
Nodes (20): command(), dashboard_telemetry(), event_count(), _gpu_values(), main(), memory_available(), _memory_values(), minimum_memory() (+12 more)

### Community 56 - "policy.py"
Cohesion: 0.18
Nodes (10): condition_matches(), lookup(), PolicyActions, PolicyDecision, PolicyRule, Any, BaseModel, field_validator (+2 more)

### Community 57 - "test_client_quality_matrix.py"
Cohesion: 0.20
Nodes (13): matrix_args(), MonkeyPatch, Namespace, Path, test_baseline_reasoning_effort_has_bounded_override(), test_codex_catalog_is_pinned_from_authenticated_gateway(), test_codex_command_uses_explicit_model_catalog(), test_docker_command_has_stable_unique_name() (+5 more)

### Community 58 - "ModelConfig"
Cohesion: 0.15
Nodes (15): ModelConfig, ExecutorBackend, Any, ExecutorCapability, Protocol, LocalPlannerProvider, _LocalProvider, LocalReviewerProvider (+7 more)

### Community 59 - "._observe"
Cohesion: 0.13
Nodes (14): argument_paths(), classify_failure(), compact_resolved_goal_history(), DuplicateFailedCall, failure_family(), fingerprint(), Detect repeated successful inspection since the latest file change., text_content() (+6 more)

### Community 60 - "._connect"
Cohesion: 0.13
Nodes (5): Any, Connection, Path, RuntimeChannel, TraceOrigin

### Community 61 - "conftest.py"
Cohesion: 0.12
Nodes (16): Path, settings(), stub_provider(), Any, MonkeyPatch, Path, StubFlashExecutor, test_admin_dashboard_runs_bounded_custom_provider_codex() (+8 more)

### Community 62 - "ModelProvider"
Cohesion: 0.13
Nodes (17): ModelProvider, Any, AsyncClient, ExecutorCapability, Fit local specialist output to the context actually served by vLLM., Return measured local context fit, or None when the tokenizer is unavailable., Run bounded English analysis, then finalize the structured local plan., StageTimeout (+9 more)

### Community 63 - "properties"
Cohesion: 0.12
Nodes (16): type, type, type, properties, completion_evidence, controller_commit, observability_degraded, schema_version (+8 more)

### Community 64 - "required"
Cohesion: 0.12
Nodes (16): agent_decisions, completion_evidence, controller_commit, evaluations, failures, final_status, observability_status, runtime_channel (+8 more)

### Community 65 - "Deterministic Synthetic Baseline"
Cohesion: 0.13
Nodes (15): Deterministic Synthetic Baseline, MVP Benchmark, Gateway MVP Boundary, MVP Scope, MVP Validation, Synthetic Six Shape Suite, Local Phase Evidence, Phase Completion Audit (+7 more)

### Community 66 - "test_goal_tooling.py"
Cohesion: 0.18
Nodes (12): bounded(), build(), main(), Any, Path, quality_tier(), split_for(), read_required_doc() (+4 more)

### Community 67 - "PolicyEngine"
Cohesion: 0.26
Nodes (12): DeclarativePolicyConfig, PolicyEngine, PolicySet, policy_set(), test_controller_applies_policy_roles_limits_and_trace(), test_controller_blocks_missing_policy_approval_and_persists_reason(), test_controller_enforces_tool_deny_and_evidence_field_redaction(), test_policy_engine_traces_versioned_aggregated_decision() (+4 more)

### Community 68 - "LiveDashboardHub"
Cohesion: 0.20
Nodes (8): LiveDashboardHub, Any, Bounded API-key-scoped projection of durable runtime events., _Subscriber, Queue, asyncio, test_live_dashboard_isolates_keys_and_redacts_operator_stream(), test_live_dashboard_replays_bounded_graph_events_or_requires_resync()

### Community 69 - "redact"
Cohesion: 0.23
Nodes (14): compress_messages(), compress_text(), redact(), test_compression_keeps_assistant_preceding_retained_tool_results(), test_default_tool_output_budget_preserves_small_source_files(), test_redaction_and_compression(), test_redaction_covers_http_credential_keys(), test_redaction_preserves_token_and_cost_measurements() (+6 more)

### Community 70 - "managed_http_client"
Cohesion: 0.20
Nodes (14): make_http_client(), managed_http_client(), AsyncBaseTransport, AsyncClient, Shared HTTPX client helpers used across gateway modules., Create a single AsyncClient with optional timeout/transport overrides., Create one request-scoped AsyncClient and guarantee closure., mistral_messages() (+6 more)

### Community 71 - "RuntimeMetrics"
Cohesion: 0.22
Nodes (6): Any, Fixed, label-free metrics; event payload content is never retained., RuntimeMetrics, test_runtime_metrics_are_fixed_label_free_and_drop_event_content(), test_runtime_metrics_classify_loop_outcomes_without_reason_labels(), test_runtime_metrics_record_judge_usage_and_later_corrected_labels()

### Community 73 - "evidence_graph"
Cohesion: 0.15
Nodes (13): edges, nodes, items, type, additionalProperties, properties, required, type (+5 more)

### Community 74 - "type"
Cohesion: 0.15
Nodes (13): items, type, items, type, items, type, type, agent_decisions (+5 more)

### Community 75 - "dgx-moa"
Cohesion: 0.18
Nodes (11): models, name, npm, options, model, dgx-moa, apiKey, baseURL (+3 more)

### Community 77 - ".__call__"
Cohesion: 0.22
Nodes (7): ASGIApp, DrainMiddleware, error_response(), JSONResponse, Receive, Scope, Send

### Community 78 - "properties"
Cohesion: 0.18
Nodes (11): type, type, properties, type, command, exit_code, path, purpose (+3 more)

### Community 80 - "improvement.py"
Cohesion: 0.36
Nodes (13): compare(), cooldown_active(), main(), mine(), proposal_fingerprint(), Any, Path, _read() (+5 more)

### Community 81 - "enum"
Cohesion: 0.20
Nodes (10): enum, blocked, cancelled, completed, degraded, failed, ok, enum (+2 more)

### Community 82 - "enum"
Cohesion: 0.20
Nodes (10): enum, blocked, cancelled, completed, degraded, failed, ok, enum (+2 more)

### Community 83 - "properties"
Cohesion: 0.20
Nodes (10): properties, recommended_next_action, remaining_risks, root_cause, schema_version, type, type, type (+2 more)

### Community 85 - "Repository Instructions"
Cohesion: 0.07
Nodes (34): Authenticated Gateway Boundary, Bounded Collaboration, Codex OAuth Frontier Collaboration, dgx-moa-fast Executor-only Compatibility Path, dgx-moa Primary Reasoner and Executor Path, Exact Full Service Stop Start Executor Unload, Executor Tool Routing and Final Synthesis Authority, Knowledge Graph Refresh Workflow (+26 more)

### Community 86 - "benchmark.py"
Cohesion: 0.44
Nodes (9): benchmark_models(), BenchmarkTask, _fixture(), main(), Any, Path, run(), _run_task() (+1 more)

### Community 87 - "capture-opencode-sse.py"
Cohesion: 0.42
Nodes (8): Client, capture(), completion_events(), expect(), main(), Any, Path, stamp()

### Community 88 - ".record_failure"
Cohesion: 0.39
Nodes (4): LifecycleAutomationStatus, Path, read_automation_status(), _sanitize_failure_class()

### Community 89 - "field_validator"
Cohesion: 0.25
Nodes (3): default_loop_budgets(), LoopEngineeringPolicy, field_validator

### Community 91 - "required"
Cohesion: 0.22
Nodes (9): changes, commit, recommended_next_action, remaining_risks, root_cause, status, schema_version, validation (+1 more)

### Community 92 - "items"
Cohesion: 0.25
Nodes (9): items, type, additionalProperties, type, changes, validation, items, items (+1 more)

### Community 93 - "MonkeyPatch"
Cohesion: 0.39
Nodes (8): block_profile_control(), block_real_lifecycle_and_profile_commands(), MonkeyPatch, test_admin_flag_is_checked_before_authentication_for_every_admin_endpoint(), test_auth_disabled_allows_inference_headers_or_none(), test_graph_shadow_finish_failure_still_returns_terminal_response(), test_nonstream_usage_is_content_free_and_uses_opaque_server_ids(), test_runtime_status_requires_admin_auth_and_returns_safe_usage()

### Community 94 - "FailingJudge"
Cohesion: 0.22
Nodes (5): FailingJudge, asyncio, MonkeyPatch, Path, test_validator_records_failed_case_without_raw_error()

### Community 95 - "ModelRef"
Cohesion: 0.28
Nodes (4): ModelRef, RoleRoute, AsyncBaseTransport, ProviderName

### Community 96 - "media_assets"
Cohesion: 0.42
Nodes (7): _inline_identity(), media_assets(), media_placeholders(), Any, _redacted_reference(), _reference(), test_remote_media_reference_drops_query_and_reports_unknown_content_hash()

### Community 97 - "OpenCodeGoExecutorProvider"
Cohesion: 0.47
Nodes (8): OpenCodeGoExecutorProvider, Compatibility name for existing integrations; model selection is explicit., asyncio, MonkeyPatch, test_model_failure_uses_rollback_but_provider_failure_does_not(), test_opencode_go_executor_preserves_native_tools_and_strips_private_fields(), test_opencode_go_executor_rejects_hidden_reasoning_without_public_output(), test_opencode_go_executor_treats_region_opt_in_as_unavailable()

### Community 98 - "validate"
Cohesion: 0.39
Nodes (7): digest(), main(), Any, Path, request(), usage(), validate()

### Community 99 - "run-opencode-staging.py"
Cohesion: 0.54
Nodes (7): create_fixture(), git(), main(), output_text(), project_config(), Path, Task

### Community 100 - "test_validator_atomically_preserves_sanitized_partial_progress"
Cohesion: 0.25
Nodes (5): Provider, asyncio, MonkeyPatch, Path, test_validator_atomically_preserves_sanitized_partial_progress()

### Community 101 - "evaluate"
Cohesion: 0.48
Nodes (6): evaluate(), main(), Any, Path, register(), test_dataset_and_adapter_promotion_guard()

### Community 102 - "Dynamic MoA Operational Boundary"
Cohesion: 0.09
Nodes (27): Authenticated Gateway, Codex OAuth Frontier, DeepSeek V4 Flash, Dynamic MoA Operational Boundary, Exact Service Stop/Start, Execution Graph Shadow, Executor Lifecycle, Operations (+19 more)

### Community 103 - "Fail Closed Policy Enforcement"
Cohesion: 0.29
Nodes (7): Declarative Policy Engine, Fail Closed Policy Enforcement, Dry Run Retention, Privacy and Retention, Bounded Remote Quality Gate, Remote Judge, Sanitized Judge Evidence Package

### Community 104 - "Immutable Skill Promotion Gate"
Cohesion: 0.29
Nodes (7): Governed Evolution Registry, Runtime Self Improvement, Immutable Skill Promotion Gate, Skill Governance, Executor Controlled Skill Activation, Runtime Skills, Skill Registry

### Community 106 - "main"
Cohesion: 0.80
Nodes (4): ending_repository(), git(), main(), Path

### Community 107 - "enum"
Cohesion: 0.29
Nodes (7): partial, blocked, completed, failed, status, enum, type

### Community 108 - "enum"
Cohesion: 0.29
Nodes (7): benchmark, candidate_evaluation, diagnostic, production, validation, trace_origin, enum

### Community 109 - "enum"
Cohesion: 0.29
Nodes (7): benchmark, candidate_evaluation, diagnostic, production, validation, trace_origin, enum

### Community 110 - "evaluate-paired-noninferiority.py"
Cohesion: 0.48
Nodes (6): evaluate(), main(), paired_bootstrap(), percentile(), Any, valid_digest()

### Community 111 - "Human Approval Gate"
Cohesion: 0.33
Nodes (6): Main and Dev Branch Roles, Generated Skills Promotion Gate, Human Approval Gate, Physically Gated Features, Python Gateway Policy, Recursive Experiment Worktrees

### Community 113 - "All-Role Storage Estimate"
Cohesion: 0.33
Nodes (6): All-Role Storage Estimate, Executor Storage Estimate, Judge Storage After Resident Downloads, Judge Storage Estimate, Planner Storage Estimate, Reviewer Storage Estimate

### Community 114 - "Model Lifecycle Contract"
Cohesion: 0.33
Nodes (6): Exact Full Service Stop Start, Honest Loading Progress, Lifecycle State Machine, Model Lifecycle Contract, Dynamic Specialist Routing, Local Remote Specialist Selection

### Community 118 - "required"
Cohesion: 0.33
Nodes (6): command, exit_code, path, purpose, summary, required

### Community 119 - "enum"
Cohesion: 0.33
Nodes (6): conflicted, high, low, medium, enum, derived_confidence

### Community 120 - "enum"
Cohesion: 0.33
Nodes (6): eligible, excluded, local_only, requires_review, training_eligibility, enum

### Community 121 - "enum"
Cohesion: 0.33
Nodes (6): eligible, excluded, local_only, requires_review, training_eligibility, enum

### Community 123 - "Model Compatibility"
Cohesion: 0.40
Nodes (5): Model Compatibility, GB10 vLLM Runtime Baseline, Selected Role Checkpoints, Model Downloads, Pinned Role Model Downloads

### Community 124 - "API Client Modes and Streaming Design"
Cohesion: 0.50
Nodes (5): API Client Modes and Streaming Plan, API Client Modes and Streaming Design, Executor-Only Client Modes, Immediate Bounded SSE Forwarding, Executor Native Tool Contract

### Community 125 - "Unload Mechanism and 64K Design"
Cohesion: 0.40
Nodes (5): Unload Mechanism and 64K Plan, Phase 4 Client Matrix and PR Gate Plan, Full Service Stop Fallback, Unload Mechanism and 64K Design, 65K Physical Quality Contract

### Community 126 - "agent-trace-v2.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $id, $schema, type

### Community 127 - "enum"
Cohesion: 0.40
Nodes (5): candidate, dev, main, runtime_channel, enum

### Community 128 - "agent-trace-v3.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $id, $schema, type

### Community 129 - "enum"
Cohesion: 0.40
Nodes (5): candidate, dev, main, runtime_channel, enum

### Community 130 - "frontier-result-v1.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $schema, title, type

### Community 131 - "remote_script"
Cohesion: 0.60
Nodes (4): encoded(), main(), Any, remote_script()

### Community 133 - "Normally Resident Executor Policy"
Cohesion: 0.67
Nodes (4): Honest Cold Response Reporting, Lifecycle Rollback Procedure, Normally Resident Executor Policy, Safe Disabled Lifecycle Defaults

### Community 136 - "type"
Cohesion: 0.50
Nodes (4): null, string, type, commit

### Community 137 - "codex-profile.sh"
Cohesion: 0.83
Nodes (3): codex-profile.sh script, show_status(), valid_profile()

### Community 138 - "restart-gateway-drained.sh"
Cohesion: 0.83
Nodes (3): cancel_drain(), request(), restart-gateway-drained.sh script

### Community 139 - "Dynamic MoA v2 Model Inventory"
Cohesion: 0.67
Nodes (3): Dynamic MoA v2 Model Inventory, Executor Backend Decision, Verified Model Cleanup

### Community 141 - "agent_invocations"
Cohesion: 0.67
Nodes (3): items, type, agent_invocations

### Community 142 - "failures"
Cohesion: 0.67
Nodes (3): items, type, failures

### Community 143 - "recommendation_resolutions"
Cohesion: 0.67
Nodes (3): recommendation_resolutions, items, type

## Knowledge Gaps
- **350 isolated node(s):** `$schema`, `npm`, `baseURL`, `apiKey`, `model` (+345 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **53 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `create_app` to `frontier.py`, `ExecutionGraphRuntime`, `Controller`, `StubProvider`, `test_streaming.py`, `SkillRegistry`, `ApiKeyStore`, `UsageStore`, `SessionState`, `remote_judge.py`, `observation.py`, `replay.py`, `KnowledgeRegistry`, `asyncio`, `SpecialistRouter`, `ProfileManager`, `schemas.py`, `api.py`, `LifecycleStore`, `state.py`, `test_state_routing.py`, `weekly.py`, `test_training.py`, `TrainingStore`, `ExecutorScheduler`, `controller.py`, `LifecycleCoordinator`, `datetime`, `lifecycle.py`, `overflow_executor.py`, `training.py`, `SystemdLifecycleDriver`, `load_settings`, `security.py`, `runtime_status.py`, `ModelConfig`, `._observe`, `conftest.py`, `ModelProvider`, `PolicyEngine`, `LiveDashboardHub`, `redact`, `managed_http_client`, `RuntimeMetrics`, `ArchiveRegistry`, `LifecycleDriver`, `WeeklyScheduler`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `frontier.py`, `ExecutionGraphRuntime`, `context_projection.py`, `SkillRegistry`, `create_app`, `UsageStore`, `SessionState`, `remote_judge.py`, `replay.py`, `KnowledgeRegistry`, `SpecialistRouter`, `schemas.py`, `api.py`, `main`, `controller.py`, `ModelConfig`, `._observe`, `conftest.py`, `ModelProvider`, `PolicyEngine`, `test_policy_redacts_specialist_state_event_and_evaluation_boundaries`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Why does `Settings` connect `create_app` to `ExecutionGraphRuntime`, `Controller`, `StubProvider`, `config.py`, `PolicyEngine`, `controller.py`, `SkillRegistry`, `ApiKeyStore`, `test_lifecycle.py`, `ValueError`, `asyncio`, `load_settings`, `MonkeyPatch`, `security.py`, `api.py`, `field_validator`, `conftest.py`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 277 inferred relationships involving `StubProvider` (e.g. with `ModelConfig` and `test_admin_dashboard_runs_bounded_custom_provider_codex()`) actually correct?**
  _`StubProvider` has 277 INFERRED edges - model-reasoned connections that need verification._
- **Are the 150 inferred relationships involving `Controller` (e.g. with `create_app()` and `Settings`) actually correct?**
  _`Controller` has 150 INFERRED edges - model-reasoned connections that need verification._
- **Are the 86 inferred relationships involving `create_app()` (e.g. with `AdminCodexRequest` and `AdminCodexRunner`) actually correct?**
  _`create_app()` has 86 INFERRED edges - model-reasoned connections that need verification._
- **Are the 131 inferred relationships involving `SessionState` (e.g. with `create_app()` and `_run_task()`) actually correct?**
  _`SessionState` has 131 INFERRED edges - model-reasoned connections that need verification._