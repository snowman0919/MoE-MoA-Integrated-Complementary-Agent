# Graph Report - MoE-MoA-Integrated-Complementary-Agent  (2026-08-22)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 3574 nodes · 9308 edges · 212 communities (151 shown, 61 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 1266 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `75bee24a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ExecutionGraphRuntime
- frontier.py
- test_lifecycle.py
- Controller
- test_streaming.py
- test_api.py
- ModelConfig
- EvolutionRegistry
- SessionState
- UsageStore
- SkillRegistry
- remote_judge.py
- replay.py
- observation.py
- runtime_prepare.py
- create_app
- loop_engineering.py
- SessionState
- config.py
- run-client-quality-matrix.py
- api.py
- LifecycleStore
- policy.py
- Qwen3.8 NVFP4 and DSpark Physical Validation
- asyncio
- LifecycleCoordinator
- test_trace_v2.py
- StubProvider
- test_usage.py
- context_projection.py
- controller.py
- ModelProvider
- ExecutorScheduler
- test_training.py
- properties
- Settings
- Settings
- schemas.py
- ApiKeyStore
- required
- ValueError
- TrainingStore
- build_runtime_evidence_snapshot
- managed_http_client
- KnowledgeRegistry
- test_weekly.py
- type
- Trace Usage and Adaptive Lifecycle Design
- main
- properties
- test_client_quality_matrix.py
- Model Lifecycle Contract
- training.py
- StateStore
- properties
- improvement.py
- runtime_status.py
- serve.py
- ._observe
- Any
- parse_bool
- redact
- enum
- properties
- .record_failure
- properties
- Canonical Evidence Snapshot
- Dynamic MoA Production Completion Plan
- SystemdLifecycleDriver
- providers.py
- weekly.py
- LiveDashboardHub
- WeeklyPackager
- required
- security.py
- AdminCodexRunner
- atomic_disable_lifecycle
- required
- enum
- Repository Instructions
- RuntimeMetrics
- ArchiveRegistry
- enum
- evidence_graph
- dgx-moa
- Client Quality Evaluation Protocol
- MonkeyPatch
- required
- required
- main
- .__init__
- Executor Authority
- Deployment Authority Layers
- Any
- properties
- evaluate
- validate-live-client-matrix.py
- Evidence Graph
- Bounded Artifacts
- Current-Executor P0 Certification
- LifecycleDriver
- benchmark.py
- media_assets
- CronSchedule
- required
- run-raw-openai-tool-loop.py
- test_goal_tooling.py
- .__call__
- capture-opencode-sse.py
- Decisions
- Deterministic Synthetic Baseline
- OpenCodeGoExecutorProvider
- enum
- enum
- enum
- parametrize
- FailingJudge
- build
- .acquire_request_leases
- run-opencode-staging.py
- summarize
- validate
- test_validator_atomically_preserves_sanitized_partial_progress
- Architecture
- Authenticated Gateway
- Checked-In Fail-Closed Defaults
- Fail Closed Policy Enforcement
- Immutable Skill Promotion Gate
- evaluate-paired-noninferiority.py
- Human Approval Gate
- All-Role Storage Estimate
- Evidence-Based Completion Rule
- Backend-Neutral Executor and Live-Client Baseline
- _validate_canonical_json
- Current Production Topology
- enum
- CountingClient
- API Client Modes
- Model Compatibility
- API Client Modes and Streaming Design
- Unload Mechanism and 64K Design
- agent-trace-v2.json
- agent-trace-v3.json
- remote_script
- main
- Normally Resident Executor Policy
- Operator Owned Evidence Worktrees
- codex-profile.sh
- restart-gateway-drained.sh
- Dynamic MoA v2 Model Inventory
- tool_executions
- switch-profile.sh
- test_p0_audit_parses_concatenated_healthcheck_documents
- test_raw_tools_are_workspace_bounded_and_execute_tests
- test_request_path_baseline_separates_local_and_fallback
- Adapter Registry
- Live Observation
- Python Gateway Retention Decision
- Authenticated Gateway Security Boundary
- Dynamic Specialist Routing
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
- Safe Checked-In Model Defaults
- Improvement IMP-2026-0001 Not Recommended
- Incomplete Files State
- BudgetName
- LoopType
- ProjectionRole
- ProjectionStage
- TerminationReason
- AsyncClient
- ExecutorCapability
- dgx-moa-agent

## God Nodes (most connected - your core abstractions)
1. `Controller` - 180 edges
2. `create_app()` - 113 edges
3. `client_with_stub()` - 109 edges
4. `lifecycle()` - 88 edges
5. `StateStore` - 58 edges
6. `Settings` - 55 edges
7. `responses_sse()` - 55 edges
8. `UsageStore` - 52 edges
9. `ExecutionGraphRuntime` - 51 edges
10. `SessionState` - 51 edges

## Surprising Connections (you probably didn't know these)
- `Model Lifecycle` --semantically_similar_to--> `Lifecycle Configuration`  [INFERRED] [semantically similar]
  docs/ARCHITECTURE.md → config/models.yaml
- `Qwen3.8 Resident Target` --semantically_similar_to--> `Qwen3.8-27B Local Executor`  [INFERRED] [semantically similar]
  docs/ARCHITECTURE.md → config/models.yaml
- `Bounded Collaboration Contract` --semantically_similar_to--> `Executor Tool Routing and Final Synthesis Authority`  [INFERRED] [semantically similar]
  goal.md → AGENTS.md
- `Modes and Idle Policy` --semantically_similar_to--> `Lifecycle Configuration`  [INFERRED] [semantically similar]
  docs/MODEL_LIFECYCLE.md → config/models.yaml
- `Bounded Optional-Role Fan-In` --semantically_similar_to--> `Optional Fan-In Timeout`  [INFERRED] [semantically similar]
  docs/ARCHITECTURE.md → config/models.yaml

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Controlled Improvement Workflow** — agents_branch_roles, agents_knowledge_graph_refresh, agents_recursive_experiment_worktrees, agents_human_approval_gate [EXTRACTED 1.00]
- **Deployment Authority Separation** — docs_state_checked_in_fail_closed_defaults, docs_state_checked_in_candidate_manifest, docs_state_last_physically_promoted_deployment [EXTRACTED 1.00]
- **Executor-Directed Public API Contract** — agents_executor_authority, docs_api_client_modes_native_client_tool_loop [EXTRACTED 1.00]
- **Executor Lifecycle Safety Contract** — agents_phase_3_executor_baseline, agents_exact_service_restart_unload, agents_safe_lifecycle_defaults, agents_resident_executor_policy, agents_honest_cold_response_reporting, agents_lifecycle_rollback [EXTRACTED 1.00]
- **Executor Path Contract** — docs_operations_dgx_moa_fast_path [EXTRACTED 1.00]
- **P0 Four-Service Stack** — compose_p0_gateway, compose_p0_executor, compose_p0_reasoner, compose_p0_harness [EXTRACTED 1.00]
- **Qwen DSpark Validation and Promotion Chain** — docs_validation_qwen38_routing_lifecycle_validation, docs_validation_qwen38_nvfp4_dspark_physical_validation, docs_validation_qwen38_dspark_production_promotion [EXTRACTED 1.00]
- **Runtime Reliability Phases** — docs_superpowers_plans_2026_07_18_api_client_modes_streaming_api_client_modes_plan, docs_superpowers_plans_2026_07_18_lifecycle_usage_trace_lifecycle_usage_plan, docs_superpowers_plans_2026_07_19_memory_unload_64k_memory_unload_plan, docs_superpowers_plans_2026_07_19_phase_4_client_matrix_pr_gate_phase4_client_matrix_plan [EXTRACTED 1.00]
- **Structured Read-Only Role Contracts** — gateway_src_dgx_moa_prompts_planner_planner_contract, gateway_src_dgx_moa_prompts_reviewer_reviewer_contract, gateway_src_dgx_moa_prompts_judge_judge_contract [EXTRACTED 1.00]
- **Current-Executor Release Evidence** — docs_frontier_dominance_v2_current_executor_p0, docs_frontier_dominance_v2_component_e2e_run, docs_state_active_qwen_executor, docs_state_frontier_dominance_v2_audit [INFERRED 0.85]
- **Fail-Closed Operating Contract** — docs_frontier_dominance_v2_fail_closed_release_certification, docs_frontier_dominance_v2_frontier_floor, docs_frontier_dominance_v2_executiongraph_controller_parity, docs_state_checked_in_fail_closed_defaults [INFERRED 0.85]
- **Governed Promotion Controls** — docs_skill_governance_immutable_skill_promotion_gate, docs_runtime_self_improvement_governed_evolution_registry, docs_recursive_improvement_isolated_improvement_flow, docs_policy_engine_fail_closed_policy_enforcement [INFERRED 0.85]
- **Role Model Capacity Planning** — data_state_storage_estimate_all_all_role_storage_estimate, data_state_storage_estimate_executor_executor_storage_estimate, data_state_storage_estimate_planner_planner_storage_estimate, data_state_storage_estimate_reviewer_reviewer_storage_estimate, data_state_storage_estimate_judge_judge_storage_estimate [INFERRED 0.85]
- **Role-Specific Training Gates** — training_executor_readme_executor_training_package, training_planner_readme_planner_training_gate, training_reviewer_readme_reviewer_training_gate, docs_training_data_fail_closed_eligibility [INFERRED 0.85]
- **Runtime Evidence Continuity** — docs_evidence_graph_evidence_graph, docs_execution_replay_execution_replay, docs_dataset_pipeline_dataset_pipeline, docs_loop_engineering_loop_engineering [INFERRED 0.85]
- **Evidence-Gated Release Governance** — goal_release_stage_gates, goal_completion_rule, docs_benchmarks_measured_benchmarks [INFERRED 0.95]
- **Executor-Directed Collaboration** — docs_architecture_executor_sole_authority, docs_decisions_executor_authority, docs_moa_orchestration_executor_authority, docs_state_executor_authority_layers [INFERRED 0.95]
- **Measured Executor Runtime Contract** — compose_p0_measured_executor_profile, docs_validation_dspark_executor_profile, docs_validation_context_smoke_matrix, docs_validation_production_throughput_evidence [INFERRED 0.95]
- **Phase 3 Executor Safety Contract** — docs_decisions_phase_3_executor_baseline, docs_memory_optimization_memory_optimization, docs_context_tuning_context_tuning, docs_dynamic_moa_concurrent_runtime_incident_20260808_safety_disposition [INFERRED 0.95]

## Communities (212 total, 61 thin omitted)

### Community 0 - "ExecutionGraphRuntime"
Cohesion: 0.06
Nodes (65): _bounded_ids(), _canonical(), _checkpoint_hash(), compact_session_active_state(), compile_execution_graph(), EdgeType, execution_graph_parity(), ExecutionGraph (+57 more)

### Community 1 - "frontier.py"
Cohesion: 0.05
Nodes (99): bounded_external_evidence(), build_frontier_task(), classify_frontier_failure(), codex_command(), codex_usage(), CodexAppServerTurn, CodexOAuthCollaboration, CodexOAuthProvider (+91 more)

### Community 2 - "test_lifecycle.py"
Cohesion: 0.06
Nodes (113): Limits, block_real_service_commands(), lifecycle(), policy_record(), policy_usage(), policy_usage_from_gaps(), Any, asyncio (+105 more)

### Community 3 - "Controller"
Cohesion: 0.06
Nodes (104): Controller, asyncio, Exception, parametrize, StubProvider, test_action_budget_does_not_reopen_after_configured_limit_is_consumed(), test_architecture_reserves_last_frontier_call_for_review(), test_changed_implementation_allows_validation_retry() (+96 more)

### Community 4 - "test_streaming.py"
Cohesion: 0.05
Nodes (94): is_workspace_objective(), batch_goal_prerequisite_read(), batch_workspace_read(), compatible_edit_call(), completed_chat_sse(), forward_sse(), has_internal_protocol_leak(), has_korean_script_leak() (+86 more)

### Community 5 - "test_api.py"
Cohesion: 0.06
Nodes (94): client_with_stub(), StubProvider, test_admin_drain_rejects_new_work_and_can_be_cancelled(), test_admin_exact_replay_is_harness_callable_and_live_comparison_stays_internal(), test_api_validation(), test_auth_enabled_invalid_key_returns_401(), test_auth_models_and_tool_call_preservation(), test_chat_and_responses_share_one_disabled_by_default_graph_shadow_path() (+86 more)

### Community 6 - "ModelConfig"
Cohesion: 0.06
Nodes (50): AcquireCallback, ModelConfig, ExecutorBackend, Any, ExecutorCapability, Protocol, StageTimeout, LocalPlannerProvider (+42 more)

### Community 7 - "EvolutionRegistry"
Cohesion: 0.05
Nodes (54): ArtifactKind, ArtifactState, EvolutionArtifact, EvolutionCandidateGenerator, EvolutionEvaluation, EvolutionRegistry, EvolutionSignal, PromptRegistry (+46 more)

### Community 8 - "SessionState"
Cohesion: 0.07
Nodes (29): BudgetName, ExecutionGraphRuntime, FrontierCollaborationResult, active_failures(), effective_objective(), has_mcp_server_failure(), pending_goal_prerequisites(), PolicyBlocked (+21 more)

### Community 9 - "UsageStore"
Cohesion: 0.06
Nodes (33): classify_client(), _duration_summary(), _ewma(), lifecycle_statistics(), LifecycleSample, _percentile(), _percentiles(), Any (+25 more)

### Community 10 - "SkillRegistry"
Cohesion: 0.08
Nodes (36): BaseModel, Connection, field_validator, model_validator, Path, Immutable, versioned Executor procedure; models may only recommend it., RuntimeSkill, SkillCandidateEvaluation (+28 more)

### Community 11 - "remote_judge.py"
Cohesion: 0.08
Nodes (34): DisabledJudgeProvider, JudgeCallLimitExceeded, JudgeCriteria, JudgeEdit, JudgeEvidencePackage, JudgeFinding, JudgeProvider, JudgeProviderError (+26 more)

### Community 12 - "replay.py"
Cohesion: 0.09
Nodes (41): EvidenceNodeType, classify_evidence(), contradiction_resolutions(), EvidenceEdge, EvidenceNode, Any, BaseModel, Resolve a contradiction by explicit trust rank, preserving deterministic ties. (+33 more)

### Community 13 - "observation.py"
Cohesion: 0.08
Nodes (30): ObservationBus, ObservationCommandRequest, ObservationCommandStore, ObservationEvent, ObservationNonceRequest, ObservationProvider, public_event(), Any (+22 more)

### Community 14 - "runtime_prepare.py"
Cohesion: 0.13
Nodes (44): apply_runtime(), atomic_write(), build_overlay(), cached_checkpoint(), conversion_command(), convert_nvfp4(), download_checkpoint(), ensure_checkout() (+36 more)

### Community 15 - "create_app"
Cohesion: 0.07
Nodes (40): create_app(), ExecutorBackend, Settings, FakeLifecycleDriver, LifecycleDriver, OpenAICompatibleExecutorProvider, assert_no_request_leases(), direct_review() (+32 more)

### Community 16 - "loop_engineering.py"
Cohesion: 0.11
Nodes (39): CriterionState, FailureClass, AcceptanceCriterion, begin_iteration(), completion_ready(), consume_budget(), consume_usage(), _drop_unstable_evidence_fields() (+31 more)

### Community 17 - "SessionState"
Cohesion: 0.10
Nodes (36): ExecutorProvider, ChangeRisk, classify_request(), heavy_eligible(), needs_planner(), needs_reviewer(), optional_roles(), Any (+28 more)

### Community 18 - "config.py"
Cohesion: 0.09
Nodes (22): default_lifecycle_roles(), ExecutionGraphConfig, ExecutorSchedulingConfig, LifecycleRolePolicy, LiveObservationConfig, ModelRef, ModelRoutingConfig, ObservationControlConfig (+14 more)

### Community 19 - "run-client-quality-matrix.py"
Cohesion: 0.19
Nodes (37): baseline_reasoning_effort(), codex_moa_command(), docker_command(), epoch_metrics(), filtered_env(), git(), hermes_test_evidence(), log_text() (+29 more)

### Community 20 - "api.py"
Cohesion: 0.08
Nodes (26): _chat_response_payload(), _coerce_responses_input_messages(), _coerce_responses_tools(), DynamicRoleUnmanagedError, has_matching_tool_result(), main(), ollama_model_ready(), openai_inference_ready() (+18 more)

### Community 21 - "LifecycleStore"
Cohesion: 0.23
Nodes (6): LifecycleRecord, LifecycleStore, Any, Connection, StaleTransitionError, LifecycleState

### Community 22 - "policy.py"
Cohesion: 0.11
Nodes (24): DeclarativePolicyConfig, condition_matches(), lookup(), PolicyActions, PolicyDecision, PolicyEngine, PolicyRule, PolicySet (+16 more)

### Community 23 - "Qwen3.8 NVFP4 and DSpark Physical Validation"
Cohesion: 0.08
Nodes (34): Authenticated Wildcard Gateway Boundary, Bounded Compile Workers, DSpark Speculative Draft, P0 Executor Service, P0 Gateway Service, P0 Harness Service, Immutable Service Filesystems, Loopback Role Endpoints (+26 more)

### Community 24 - "asyncio"
Cohesion: 0.17
Nodes (34): ChatRequest, assert_terminal_evidence(), assert_usage(), chat_endpoint(), direct_chat(), asyncio, test_asgi_response_cancellation_while_sending_closes_stream_owner(), test_completed_retryable_failure_is_requeued_as_loading_on_the_next_request() (+26 more)

### Community 25 - "LifecycleCoordinator"
Cohesion: 0.13
Nodes (9): LifecyclePolicy, LifecycleCoordinator, LifecycleLoadError, Apply an explicit operator enable/disable to one managed role., UnknownRoleError, GuardKind, LifecycleMode, T (+1 more)

### Community 26 - "test_trace_v2.py"
Cohesion: 0.16
Nodes (29): validate_failure_record(), audit_traces(), export_trace(), final_status(), main(), Any, Path, Build bounded trajectory evidence; never source or hidden-reasoning archives. (+21 more)

### Community 27 - "StubProvider"
Cohesion: 0.11
Nodes (25): TestClient, Path, settings(), stub_provider(), StubProvider, Any, MonkeyPatch, Path (+17 more)

### Community 28 - "test_usage.py"
Cohesion: 0.19
Nodes (32): finalization(), Any, MonkeyPatch, parametrize, Path, read_sqlite_files(), start_record(), test_active_request_count_is_not_limited_by_statistics_window() (+24 more)

### Community 29 - "context_projection.py"
Cohesion: 0.12
Nodes (26): ContributionRole, _bounded_unique(), _canonical(), CanonicalRequestInput, _content_hash(), _evidence_retention_key(), _hash(), model_contribution() (+18 more)

### Community 30 - "controller.py"
Cohesion: 0.14
Nodes (27): clean_tool_output(), embedded_tool_exit_code(), FrontierRequiredUnavailable, JudgeCorrectionRequired, JudgeRequired, LoopAdmissionError, normalize_tool_result(), RuntimeError (+19 more)

### Community 31 - "ModelProvider"
Cohesion: 0.17
Nodes (28): AsyncByteStream, ModelProvider, asyncio, MonkeyPatch, parametrize, test_backend_contract_reports_identity_and_supports_cancel(), test_completion_timeout_has_exact_stage(), test_executor_context_fit_uses_served_tokenizer_limit() (+20 more)

### Community 32 - "ExecutorScheduler"
Cohesion: 0.13
Nodes (17): Future, ExecutorAdmission, ExecutorQueueFull, ExecutorQueueTimeout, ExecutorScheduler, ExecutorSchedulingError, RuntimeError, _Queued (+9 more)

### Community 33 - "test_training.py"
Cohesion: 0.20
Nodes (28): candidate_from_trace(), candidates_from_trace(), ContentStore, TrainingCollector, RepositoryTrainingPolicy, eligible_trace(), parametrize, Path (+20 more)

### Community 34 - "properties"
Cohesion: 0.07
Nodes (30): items, type, type, type, items, type, items, type (+22 more)

### Community 35 - "Settings"
Cohesion: 0.10
Nodes (27): MockJudgeProvider, RemoteJudgeVerdict, Any, Path, Settings, remote_verdict(), test_busy_executor_remote_stream_failure_is_observable(), test_busy_executor_routes_new_session_to_frontier() (+19 more)

### Community 36 - "Settings"
Cohesion: 0.17
Nodes (26): get_settings(), load_settings(), Path, Settings, Path, test_admin_key_authority_environment_is_bounded(), test_auth_disabled_allows_missing_key(), test_auth_enabled_requires_real_key() (+18 more)

### Community 37 - "schemas.py"
Cohesion: 0.13
Nodes (22): AdditionalAgentRecommendation, ChatMessage, JudgeVerdict, MandatoryChange, OrchestrationDecision, PlannerPlan, PlannerStep, ProfileResponse (+14 more)

### Community 38 - "ApiKeyStore"
Cohesion: 0.16
Nodes (6): admin_dependency(), ApiKeyStore, auth_dependency(), Any, Connection, Path

### Community 39 - "required"
Cohesion: 0.12
Nodes (27): agent_artifacts, agent_invocations, context_configuration, derived_confidence, events, evidence_graph, metrics, model_revisions (+19 more)

### Community 40 - "ValueError"
Cohesion: 0.11
Nodes (21): calculate_idle_policy(), _configured_quantile(), continuation_correlation(), _idle_bounds(), InvalidTransitionError, LifecycleError, LifecycleFailureEvent, LifecycleNotReadyError (+13 more)

### Community 41 - "TrainingStore"
Cohesion: 0.17
Nodes (5): now(), Connection, Path, TrainingStore, ReviewState

### Community 42 - "build_runtime_evidence_snapshot"
Cohesion: 0.21
Nodes (24): build_runtime_evidence_snapshot(), canonical_request_input(), project_role_context(), ProjectionRole, ProjectionStage, Versioned source of truth from which every role context is independently…, runtime_evidence_item(), RuntimeEvidenceSnapshot (+16 more)

### Community 43 - "managed_http_client"
Cohesion: 0.15
Nodes (17): make_http_client(), managed_http_client(), AsyncBaseTransport, AsyncClient, Shared HTTPX client helpers used across gateway modules., Create a single AsyncClient with optional timeout/transport overrides., Create one request-scoped AsyncClient and guarantee closure., OpenAICompatibleExecutorProvider (+9 more)

### Community 44 - "KnowledgeRegistry"
Cohesion: 0.19
Nodes (7): KnowledgeLifecycle, KnowledgeRegistry, Connection, model_validator, Path, RuntimeKnowledge, KnowledgeState

### Community 45 - "test_weekly.py"
Cohesion: 0.20
Nodes (23): candidate_path(), previous_complete_week(), payload(), test_frozen_paired_bootstrap_passes_only_complete_covered_matrix(), test_missing_or_incomplete_pair_fails_closed_without_exclusion(), candidate(), fake_7z(), parametrize (+15 more)

### Community 46 - "type"
Cohesion: 0.08
Nodes (25): items, type, items, type, items, type, items, type (+17 more)

### Community 47 - "Trace Usage and Adaptive Lifecycle Design"
Cohesion: 0.08
Nodes (24): Trace Usage and Lifecycle Plan, Role-Aware Adaptive Lifecycle Gap-Closure Plan, Lifecycle Activity Guards, Trace Usage and Adaptive Lifecycle Design, Single-Flight Cold Loading, External Lifecycle Control, External Ollama Reasoner Lifecycle Design, Nonblocking Systemd Activation (+16 more)

### Community 48 - "main"
Cohesion: 0.20
Nodes (20): KnowledgeConfidence, KnowledgeContent, KnowledgeEvidence, KnowledgeMatch, KnowledgeProvenance, KnowledgeQuery, KnowledgeValidation, BaseModel (+12 more)

### Community 49 - "properties"
Cohesion: 0.08
Nodes (24): type, type, type, items, type, type, properties, completion_evidence (+16 more)

### Community 50 - "test_client_quality_matrix.py"
Cohesion: 0.14
Nodes (16): matrix_args(), MonkeyPatch, Namespace, parametrize, Path, test_baseline_reasoning_effort_has_bounded_override(), test_codex_catalog_is_pinned_from_authenticated_gateway(), test_codex_command_uses_explicit_model_catalog() (+8 more)

### Community 51 - "Model Lifecycle Contract"
Cohesion: 0.13
Nodes (23): DSpark Speculative Decoding, Executor Scheduling, Fail-Closed Checked-In Defaults, Gateway Configuration, Judge Model, Lifecycle Configuration, Model Routing, Optional Fan-In Timeout (+15 more)

### Community 52 - "training.py"
Cohesion: 0.15
Nodes (19): is_sensitive_key(), assess_candidate(), CandidateQualityReport, CandidateReviewRequest, BaseModel, model_validator, SanitizationResult, sanitize() (+11 more)

### Community 53 - "StateStore"
Cohesion: 0.16
Nodes (7): Any, Connection, Path, Drop rebuildable continuation indexes without touching canonical sessions., StateStore, RuntimeChannel, TraceOrigin

### Community 54 - "properties"
Cohesion: 0.10
Nodes (22): items, type, items, type, type, items, type, type (+14 more)

### Community 55 - "improvement.py"
Cohesion: 0.22
Nodes (19): evaluate(), main(), Any, Path, register(), compare(), cooldown_active(), main() (+11 more)

### Community 56 - "runtime_status.py"
Cohesion: 0.21
Nodes (20): command(), dashboard_telemetry(), event_count(), _gpu_values(), main(), memory_available(), _memory_values(), minimum_memory() (+12 more)

### Community 57 - "serve.py"
Cohesion: 0.23
Nodes (18): command(), main(), role_bool_environment(), role_context_length(), role_environment(), _sglang_command(), _vllm_command(), MonkeyPatch (+10 more)

### Community 58 - "._observe"
Cohesion: 0.13
Nodes (13): argument_paths(), classify_failure(), compact_resolved_goal_history(), DuplicateFailedCall, failure_family(), fingerprint(), Detect repeated successful inspection since the latest file change., Successful exact reads since the latest file change. (+5 more)

### Community 59 - "Any"
Cohesion: 0.22
Nodes (8): AsyncClient, ExecutorCapability, Any, Fit local specialist output to the context actually served by vLLM., Return measured local context fit, or None when the tokenizer is unavailable., Run bounded English analysis, then finalize the structured local plan., ModelConfig, test_ollama_reasoner_contract()

### Community 60 - "parse_bool"
Cohesion: 0.14
Nodes (9): default_loop_budgets(), LoopEngineeringPolicy, parse_bool(), Any, field_validator, WeeklyJobsConfig, parametrize, test_false_boolean_forms() (+1 more)

### Community 61 - "redact"
Cohesion: 0.24
Nodes (15): compress_messages(), compress_text(), message_fingerprint(), Any, redact(), test_compression_keeps_a_user_anchor_for_long_tool_loops(), test_compression_keeps_assistant_preceding_retained_tool_results(), test_default_tool_output_budget_preserves_small_source_files() (+7 more)

### Community 62 - "enum"
Cohesion: 0.15
Nodes (17): partial, enum, degraded, ok, enum, observability_status, enum, blocked (+9 more)

### Community 63 - "properties"
Cohesion: 0.12
Nodes (16): type, type, type, properties, events, metrics, objective, schema_version (+8 more)

### Community 64 - ".record_failure"
Cohesion: 0.21
Nodes (8): IdlePolicyDecision, LifecycleAutomationStatus, LoadCheck, PersistedIdlePolicyDecision, BaseModel, Path, read_automation_status(), read_latest_decisions()

### Community 65 - "properties"
Cohesion: 0.12
Nodes (16): null, string, type, properties, commit, recommended_next_action, remaining_risks, root_cause (+8 more)

### Community 66 - "Canonical Evidence Snapshot"
Cohesion: 0.15
Nodes (15): ExecutionGraph Configuration, Allowlisted Role Projections, Bounded Optional-Role Fan-In, Bounded Streaming Forwarding, Canonical Evidence Snapshot, Concurrent Pre-Dispatch Collaboration, ExecutionGraph Shadow Parity, Executor Sole Authority (+7 more)

### Community 67 - "Dynamic MoA Production Completion Plan"
Cohesion: 0.15
Nodes (16): Context Tuning, Legacy Profile Tuner, Phase 3 Executor Baseline, Deterministic Graph Compiler, Dynamic MoA Production Completion Plan, Dynamic MoA Completion Plan v1 Recovery Snapshot, Dynamic MoA Production Completion Plan Epoch 2, Target Topology (+8 more)

### Community 68 - "SystemdLifecycleDriver"
Cohesion: 0.30
Nodes (4): DriverErrorKind, DriverOperation, LifecycleDriverError, SystemdLifecycleDriver

### Community 69 - "providers.py"
Cohesion: 0.15
Nodes (8): validate_executor_response(), mistral_messages(), mistral_tool_call_id(), OwnedByteStream, Response, qwen_messages(), response_message(), validate_assistant_response()

### Community 70 - "weekly.py"
Cohesion: 0.21
Nodes (14): KnowledgeMetrics, classify_knowledge(), classify_skill(), knowledge_overlap(), BaseModel, skill_overlap(), snapshot_version(), weekly_candidate_analysis() (+6 more)

### Community 71 - "LiveDashboardHub"
Cohesion: 0.25
Nodes (5): LiveDashboardHub, Any, Bounded API-key-scoped projection of durable runtime events., _Subscriber, Queue

### Community 72 - "WeeklyPackager"
Cohesion: 0.32
Nodes (5): Any, Path, sha256(), WeeklyPackager, WeeklyWindow

### Community 73 - "required"
Cohesion: 0.15
Nodes (15): command, exit_code, path, purpose, summary, items, type, additionalProperties (+7 more)

### Community 74 - "security.py"
Cohesion: 0.21
Nodes (10): FastAPI, ApiKeyRequest, ApiKeyUpdate, BaseModel, Any, asyncio, test_dashboard_is_disabled_by_default(), test_dashboard_projects_stream_output_and_terminal_status() (+2 more)

### Community 75 - "AdminCodexRunner"
Cohesion: 0.27
Nodes (5): AdminCodexRequest, AdminCodexRunner, Any, BaseModel, Path

### Community 76 - "atomic_disable_lifecycle"
Cohesion: 0.29
Nodes (12): atomic_disable_lifecycle(), _fsync_directory(), main(), Path, rollback(), MonkeyPatch, Path, test_atomic_disable_is_idempotent_and_preserves_evidence() (+4 more)

### Community 77 - "required"
Cohesion: 0.14
Nodes (13): acceptance_criteria, allowed_paths, base_commit, forbidden_actions, repository_identity, objective, task_id, schema_version (+5 more)

### Community 78 - "enum"
Cohesion: 0.14
Nodes (14): Bronze, Gold, Negative, Silver, test, train, Unknown, properties (+6 more)

### Community 79 - "Repository Instructions"
Cohesion: 0.18
Nodes (12): Authenticated Gateway Boundary, Bounded Collaboration, Codex OAuth Frontier Collaboration, dgx-moa-fast Executor-only Compatibility Path, dgx-moa Primary Reasoner and Executor Path, Exact Full Service Stop Start Executor Unload, Executor Tool Routing and Final Synthesis Authority, Knowledge Graph Refresh Workflow (+4 more)

### Community 80 - "RuntimeMetrics"
Cohesion: 0.22
Nodes (6): Any, Fixed, label-free metrics; event payload content is never retained., RuntimeMetrics, test_runtime_metrics_are_fixed_label_free_and_drop_event_content(), test_runtime_metrics_classify_loop_outcomes_without_reason_labels(), test_runtime_metrics_record_judge_usage_and_later_corrected_labels()

### Community 82 - "enum"
Cohesion: 0.15
Nodes (13): context, controller, infrastructure, model, routing, prompt, properties, proposal_id (+5 more)

### Community 83 - "evidence_graph"
Cohesion: 0.15
Nodes (13): edges, nodes, items, type, additionalProperties, properties, required, type (+5 more)

### Community 84 - "dgx-moa"
Cohesion: 0.18
Nodes (11): models, name, npm, options, model, dgx-moa, apiKey, baseURL (+3 more)

### Community 85 - "Client Quality Evaluation Protocol"
Cohesion: 0.17
Nodes (12): Artificial Analysis Coding Agent Index, Artificial Analysis Intelligence Index, Claude Opus 5, Client Quality Evaluation Protocol, External Anchors, Frontier Dominance v2, Frozen Local Panel, GPT-5.6 Sol (+4 more)

### Community 86 - "MonkeyPatch"
Cohesion: 0.23
Nodes (12): fixture, block_profile_control(), block_real_lifecycle_and_profile_commands(), MonkeyPatch, test_admin_flag_is_checked_before_authentication_for_every_admin_endpoint(), test_api_key_scheduler_pins_cross_key_turn_to_remote_fallback_and_projects_graph(), test_auth_disabled_allows_inference_headers_or_none(), test_graph_shadow_finish_failure_still_returns_terminal_response() (+4 more)

### Community 87 - "required"
Cohesion: 0.17
Nodes (11): changes, commit, recommended_next_action, remaining_risks, root_cause, status, additionalProperties, required (+3 more)

### Community 88 - "required"
Cohesion: 0.17
Nodes (11): evidence, proposal_id, proposed_change, requires_human_approval, risk, suspected_layer, title, required (+3 more)

### Community 89 - "main"
Cohesion: 0.35
Nodes (11): artifact_digest(), digest_pinned(), executor_probe_command(), json_stream(), main(), option_value(), Any, CompletedProcess (+3 more)

### Community 90 - ".__init__"
Cohesion: 0.18
Nodes (10): CodexOAuthCollaboration, ExecutorBackend, Settings, JudgeProvider, KnowledgeRegistry, PolicyEngine, PromptRegistry, SkillRegistry (+2 more)

### Community 91 - "Executor Authority"
Cohesion: 0.20
Nodes (10): Codex OAuth Frontier Configuration, Codex OAuth Frontier Example, Bubblewrap Loopback Blocker, Historical Codex Frontier Candidate-Edit Escalation, Executor Authority, External Ollama Reasoner Core, Codex OAuth Profiles, Frontier Collaboration (+2 more)

### Community 92 - "Deployment Authority Layers"
Cohesion: 0.20
Nodes (11): Operations, Deployment Authority Layers, Checked-In Candidate Manifest, Last Physically Promoted Deployment, PILOT_ACTIVE Release State, Current Operational State, dgx-moa, DGX MoA Agent 2.0 (+3 more)

### Community 93 - "Any"
Cohesion: 0.24
Nodes (6): detect_language(), execution_graph_training_projection(), near_duplicate(), normalized_text(), Any, test_near_duplicate_uses_normalized_content()

### Community 94 - "properties"
Cohesion: 0.18
Nodes (11): type, type, properties, type, command, exit_code, path, purpose (+3 more)

### Community 95 - "evaluate"
Cohesion: 0.42
Nodes (10): digest_ok(), evaluate(), evidence_ok(), finite_number(), lower_bound(), main(), percentile(), Any (+2 more)

### Community 96 - "validate-live-client-matrix.py"
Cohesion: 0.33
Nodes (10): client_env(), git_fingerprint(), main(), port_available(), CompletedProcess, Path, run(), start_gateway() (+2 more)

### Community 97 - "Evidence Graph"
Cohesion: 0.20
Nodes (10): Dataset Pipeline, Training Eligibility, Evidence Graph, Deterministic Trust Ordering, Exact Replay, Execution Replay, Knowledge Lifecycle, Runtime Knowledge Base (+2 more)

### Community 98 - "Bounded Artifacts"
Cohesion: 0.20
Nodes (10): Dynamic MoA Completion Audit, Dynamic MoA Pilot Context Epoch, Role Context Package v1, Dynamic MoA Pilot Feedback Epoch, Goal, Pilot Qualification, Bounded Artifacts, Frontier Collaboration (+2 more)

### Community 99 - "Current-Executor P0 Certification"
Cohesion: 0.15
Nodes (14): Current-Qwen Component E2E Run, Current-Executor P0 Certification, ExecutionGraph Controller Parity, Fail-Closed Release Certification, Frontier-Dominance v2 Evaluator, Frontier-Dominance v2 Release-Gate Report, Objective-Verifier Frontier Floor, Offline Rebuildable-Schema Rollback (+6 more)

### Community 100 - "LifecycleDriver"
Cohesion: 0.20
Nodes (3): DriverStatus, LifecycleDriver, Protocol

### Community 101 - "benchmark.py"
Cohesion: 0.44
Nodes (9): benchmark_models(), BenchmarkTask, _fixture(), main(), Any, Path, run(), _run_task() (+1 more)

### Community 102 - "media_assets"
Cohesion: 0.38
Nodes (8): _inline_identity(), media_assets(), media_placeholders(), Any, _redacted_reference(), _reference(), test_media_identity_is_bounded_and_visible_to_runtime(), test_remote_media_reference_drops_query_and_reports_unknown_content_hash()

### Community 103 - "CronSchedule"
Cohesion: 0.29
Nodes (4): CronSchedule, datetime, WeeklyScheduler, test_weekly_cron_uses_configured_seoul_calendar_and_rejects_unsupported_syntax()

### Community 104 - "required"
Cohesion: 0.20
Nodes (9): chosen, quality_tier, split, type, prompt, required, $schema, title (+1 more)

### Community 105 - "run-raw-openai-tool-loop.py"
Cohesion: 0.40
Nodes (9): completion(), emit(), execute_tool(), parse_args(), Any, Namespace, Path, run() (+1 more)

### Community 106 - "test_goal_tooling.py"
Cohesion: 0.27
Nodes (5): read_required_doc(), test_dataset_quality_tiers(), test_lifecycle_docs_link_canonical_contract_and_keep_evidence_pending(), test_model_lifecycle_documentation_contract(), test_model_lifecycle_safety_and_status_contract()

### Community 108 - ".__call__"
Cohesion: 0.22
Nodes (7): ASGIApp, DrainMiddleware, error_response(), JSONResponse, Receive, Scope, Send

### Community 109 - "capture-opencode-sse.py"
Cohesion: 0.42
Nodes (8): Client, capture(), completion_events(), expect(), main(), Any, Path, stamp()

### Community 110 - "Decisions"
Cohesion: 0.22
Nodes (9): Append-Oriented Traces, Branch and Worktree Policy, Decision-Trajectory Evidence, Decisions, Full-Service Stop Unload, Host vLLM 0.22.1, SQLite and Explicit State Machine, Exact Full Service Stop/Start (+1 more)

### Community 111 - "Deterministic Synthetic Baseline"
Cohesion: 0.22
Nodes (9): Benchmark-Session Mixing Prevention, Deterministic Synthetic Baseline, MVP Benchmark, Gateway MVP Boundary, MVP Scope, MVP Validation, Synthetic Six Shape Suite, Local Phase Evidence (+1 more)

### Community 112 - "OpenCodeGoExecutorProvider"
Cohesion: 0.47
Nodes (8): OpenCodeGoExecutorProvider, Compatibility name for existing integrations; model selection is explicit., asyncio, MonkeyPatch, test_model_failure_uses_rollback_but_provider_failure_does_not(), test_opencode_go_executor_preserves_native_tools_and_strips_private_fields(), test_opencode_go_executor_rejects_hidden_reasoning_without_public_output(), test_opencode_go_executor_treats_region_opt_in_as_unavailable()

### Community 113 - "enum"
Cohesion: 0.22
Nodes (9): candidate, dev, main, runtime_channel, enum, dev, main, runtime_channel (+1 more)

### Community 114 - "enum"
Cohesion: 0.28
Nodes (9): eligible, excluded, local_only, requires_review, training_eligibility, enum, eligible, training_eligibility (+1 more)

### Community 115 - "enum"
Cohesion: 0.33
Nodes (9): trace_origin, enum, benchmark, candidate_evaluation, diagnostic, production, validation, trace_origin (+1 more)

### Community 116 - "parametrize"
Cohesion: 0.22
Nodes (9): Exception, parametrize, test_explicit_reasoner_policy_is_required_when_cold(), test_failure_circuit_blocks_mutation_but_preserves_ready_traffic(), test_flash_invalid_output_alone_falls_back_to_frontier(), test_non_timeout_terminal_failure_records_one_timing_and_trace(), test_stage_timeout_returns_exact_typed_error(), test_tool_result_matching_requires_the_trailing_assistant_continuation() (+1 more)

### Community 117 - "FailingJudge"
Cohesion: 0.22
Nodes (5): FailingJudge, asyncio, MonkeyPatch, Path, test_validator_records_failed_case_without_raw_error()

### Community 118 - "build"
Cohesion: 0.46
Nodes (7): bounded(), build(), main(), Any, Path, quality_tier(), split_for()

### Community 119 - ".acquire_request_leases"
Cohesion: 0.43
Nodes (3): LifecycleLease, Row, RequestLeaseKind

### Community 120 - "run-opencode-staging.py"
Cohesion: 0.54
Nodes (7): create_fixture(), git(), main(), output_text(), project_config(), Path, Task

### Community 121 - "summarize"
Cohesion: 0.43
Nodes (7): main(), metrics(), percentile(), Any, datetime, Path, summarize()

### Community 122 - "validate"
Cohesion: 0.39
Nodes (7): digest(), main(), Any, Path, request(), usage(), validate()

### Community 123 - "test_validator_atomically_preserves_sanitized_partial_progress"
Cohesion: 0.25
Nodes (5): Provider, asyncio, MonkeyPatch, Path, test_validator_atomically_preserves_sanitized_partial_progress()

### Community 124 - "Architecture"
Cohesion: 0.29
Nodes (7): Resident Executor Judge Exclusion, Architecture, Model Lifecycle, Python Gateway Decision, Qwen3.8 Resident Target, Architecture Reasoner Endpoint, Python Gateway Retention

### Community 125 - "Authenticated Gateway"
Cohesion: 0.29
Nodes (7): Codex OAuth Frontier, API Key Registry, Authenticated Gateway, Disabled Development Features, Dynamic MoA Operational Boundary, Model Invocation Rate Report, SSE Continuity Acceptance

### Community 126 - "Checked-In Fail-Closed Defaults"
Cohesion: 0.50
Nodes (4): dgx-moa Reasoner and Executor Path, Loopback-Only Reasoner Endpoint, Authenticated Gateway and Private Role Endpoint Boundary, Checked-In Fail-Closed Defaults

### Community 127 - "Fail Closed Policy Enforcement"
Cohesion: 0.29
Nodes (7): Declarative Policy Engine, Fail Closed Policy Enforcement, Dry Run Retention, Privacy and Retention, Bounded Remote Quality Gate, Remote Judge, Sanitized Judge Evidence Package

### Community 128 - "Immutable Skill Promotion Gate"
Cohesion: 0.29
Nodes (7): Governed Evolution Registry, Runtime Self Improvement, Immutable Skill Promotion Gate, Skill Governance, Executor Controlled Skill Activation, Runtime Skills, Skill Registry

### Community 129 - "evaluate-paired-noninferiority.py"
Cohesion: 0.48
Nodes (6): evaluate(), main(), paired_bootstrap(), percentile(), Any, valid_digest()

### Community 130 - "Human Approval Gate"
Cohesion: 0.33
Nodes (6): Main and Dev Branch Roles, Generated Skills Promotion Gate, Human Approval Gate, Physically Gated Features, Python Gateway Policy, Recursive Experiment Worktrees

### Community 131 - "All-Role Storage Estimate"
Cohesion: 0.33
Nodes (6): All-Role Storage Estimate, Executor Storage Estimate, Judge Storage After Resident Downloads, Judge Storage Estimate, Planner Storage Estimate, Reviewer Storage Estimate

### Community 132 - "Evidence-Based Completion Rule"
Cohesion: 0.33
Nodes (6): Measured Benchmark Registry, CI Pipeline, Bounded Collaboration Contract, Evidence-Based Completion Rule, Dynamic MoA Release Direction, Release Stage Gates

### Community 133 - "Backend-Neutral Executor and Live-Client Baseline"
Cohesion: 0.33
Nodes (6): Backend Contract, Backend-Neutral Executor and Live-Client Baseline, Four-Client Live Matrix, Remote Overflow Executor, Validation Evidence Ledger, Verified Completion Boundary

### Community 135 - "Current Production Topology"
Cohesion: 0.33
Nodes (6): Checked-in Fail-Closed Manifest, Current-Executor P0 Certification Open, Current Production Topology, Loopback Reasoner Rule, Production Reasoner Endpoint Exception, Qwen3.8 Production Executor

### Community 136 - "enum"
Cohesion: 0.33
Nodes (6): conflicted, high, low, medium, enum, derived_confidence

### Community 138 - "API Client Modes"
Cohesion: 0.40
Nodes (5): Gateway Container Service, API Client Modes, Native Client Tool Loop, Authenticated OpenAI-Compatible API, Streaming Forwarding Contract

### Community 139 - "Model Compatibility"
Cohesion: 0.40
Nodes (5): Model Compatibility, GB10 vLLM Runtime Baseline, Selected Role Checkpoints, Model Downloads, Pinned Role Model Downloads

### Community 140 - "API Client Modes and Streaming Design"
Cohesion: 0.50
Nodes (5): API Client Modes and Streaming Plan, API Client Modes and Streaming Design, Executor-Only Client Modes, Immediate Bounded SSE Forwarding, Executor Native Tool Contract

### Community 141 - "Unload Mechanism and 64K Design"
Cohesion: 0.40
Nodes (5): Unload Mechanism and 64K Plan, Phase 4 Client Matrix and PR Gate Plan, Full Service Stop Fallback, Unload Mechanism and 64K Design, 65K Physical Quality Contract

### Community 142 - "agent-trace-v2.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $id, $schema, type

### Community 143 - "agent-trace-v3.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $id, $schema, type

### Community 144 - "remote_script"
Cohesion: 0.60
Nodes (4): encoded(), main(), Any, remote_script()

### Community 145 - "main"
Cohesion: 0.80
Nodes (4): ending_repository(), git(), main(), Path

### Community 146 - "Normally Resident Executor Policy"
Cohesion: 0.67
Nodes (4): Honest Cold Response Reporting, Lifecycle Rollback Procedure, Normally Resident Executor Policy, Safe Disabled Lifecycle Defaults

### Community 147 - "Operator Owned Evidence Worktrees"
Cohesion: 0.50
Nodes (4): Operator Owned Evidence Worktrees, Pilot Worktree Inventory, Isolated Improvement Flow, Recursive Improvement

### Community 148 - "codex-profile.sh"
Cohesion: 0.83
Nodes (3): codex-profile.sh script, show_status(), valid_profile()

### Community 149 - "restart-gateway-drained.sh"
Cohesion: 0.83
Nodes (3): cancel_drain(), request(), restart-gateway-drained.sh script

### Community 150 - "Dynamic MoA v2 Model Inventory"
Cohesion: 0.67
Nodes (3): Dynamic MoA v2 Model Inventory, Executor Backend Decision, Verified Model Cleanup

### Community 151 - "tool_executions"
Cohesion: 0.67
Nodes (3): tool_executions, items, type

## Knowledge Gaps
- **316 isolated node(s):** `$schema`, `title`, `type`, `chosen`, `quality_tier` (+311 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **61 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Controller` to `.__init__`, `ModelConfig`, `EvolutionRegistry`, `SessionState`, `media_assets`, `SkillRegistry`, `remote_judge.py`, `create_app`, `loop_engineering.py`, `main`, `SessionState`, `api.py`, `policy.py`, `._observe`, `StubProvider`, `controller.py`, `ModelProvider`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Why does `create_app()` connect `create_app` to `validate-live-client-matrix.py`, `ExecutionGraphRuntime`, `Controller`, `Settings`, `test_api.py`, `ModelConfig`, `ApiKeyStore`, `SessionState`, `Settings`, `security.py`, `api.py`, `parametrize`, `MonkeyPatch`, `asyncio`, `._observe`, `StubProvider`, `controller.py`, `ModelProvider`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Why does `UsageStore` connect `UsageStore` to `test_lifecycle.py`, `ValueError`, `runtime_status.py`, `LifecycleCoordinator`, `StubProvider`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 115 inferred relationships involving `Controller` (e.g. with `create_app()` and `ModelProvider`) actually correct?**
  _`Controller` has 115 INFERRED edges - model-reasoned connections that need verification._
- **Are the 171 inferred relationships involving `ValueError` (e.g. with `evaluate()` and `register()`) actually correct?**
  _`ValueError` has 171 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `create_app()` (e.g. with `Controller` and `DuplicateFailedCall`) actually correct?**
  _`create_app()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `$schema`, `title`, `type` to the rest of the system?**
  _316 weakly-connected nodes found - possible documentation gaps or missing edges._