# Graph Report - dgx-moa-agent  (2026-09-15)

## Corpus Check
- 263 files · ~369,263 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3636 nodes · 10129 edges · 220 communities (165 shown, 55 thin omitted)
- Extraction: 81% EXTRACTED · 19% INFERRED · 0% AMBIGUOUS · INFERRED: 1944 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4d584d84`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ExecutionGraphRuntime
- test_frontier.py
- Controller
- StubProvider
- test_streaming.py
- SpecialistRouter
- EvolutionRegistry
- SessionState
- context_projection.py
- SkillRegistry
- UsageStore
- test_lifecycle.py
- test_training.py
- main
- remote_judge.py
- dgx-moa
- replay.py
- LifecycleStore
- observation.py
- runtime_prepare.py
- execution_graph.py
- create_app
- run-client-quality-matrix.py
- RuntimeSkill
- controller.py
- Qwen3.8 NVFP4 and DSpark Physical Validation
- asyncio
- MonkeyPatch
- test_usage.py
- config.py
- lifecycle.py
- LifecycleCoordinator
- ModelProvider
- serve.py
- ExecutorScheduler
- build_runtime_evidence_snapshot
- ._connect
- load_settings
- ApiKeyStore
- TrainingStore
- weekly.py
- type
- test_providers.py
- CronSchedule
- test_trace_v2.py
- test_weekly.py
- Trace Usage and Adaptive Lifecycle Design
- routing.py
- TrainingCandidate
- properties
- test_client_quality_matrix.py
- Model Lifecycle Contract
- required
- properties
- SystemdLifecycleDriver
- api.py
- LiveDashboardHub
- overflow_executor.py
- runtime_status.py
- ExecutionGraphStore
- Any
- policy.py
- compile_execution_graph
- enum
- security.py
- ValueError
- required
- properties
- PolicyEngine
- properties
- Bounded Artifacts
- Dynamic MoA Production Completion Plan
- required
- items
- Current-Executor P0 Certification
- frontier.py
- atomic_disable_lifecycle
- OwnedByteStream
- RuntimeMetrics
- ._run
- required
- evidence_graph
- type
- Repository Instructions
- .__init__
- Client Quality Evaluation Protocol
- benchmark.py
- required
- Path
- main
- specialists.py
- Executor Authority
- Deployment Authority Layers
- ResponseOwnedIterator
- required
- enum
- properties
- evaluate
- validate-live-client-matrix.py
- Dynamic MoA Pilot Context Epoch
- LifecycleDriver
- normalize_openrouter_tool_calls
- media_assets
- FrontierTask
- run-raw-openai-tool-loop.py
- .__call__
- capture-opencode-sse.py
- Evidence Graph
- Decisions
- Deterministic Synthetic Baseline
- providers.py
- state.py
- ArchiveRegistry
- enum
- enum
- enum
- FailingJudge
- ._decision
- test_admin_dashboard.py
- run-opencode-staging.py
- summarize
- test_validator_atomically_preserves_sanitized_partial_progress
- Architecture
- Authenticated Gateway
- Fail Closed Policy Enforcement
- Immutable Skill Promotion Gate
- .acquire_request_leases
- enum
- evaluate-paired-noninferiority.py
- validate
- Human Approval Gate
- All-Role Storage Estimate
- Evidence-Based Completion Rule
- Backend-Neutral Executor and Live-Client Baseline
- enum
- validate
- Current Production Topology
- enum
- API Client Modes
- Model Compatibility
- API Client Modes and Streaming Design
- Unload Mechanism and 64K Design
- agent-trace-v3.json
- remote_script
- main
- Normally Resident Executor Policy
- Fail-Closed Release Certification
- Operator Owned Evidence Worktrees
- codex-profile.sh
- restart-gateway-drained.sh
- test_api_keys.py
- Dynamic MoA v2 Model Inventory
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
- _validate_canonical_json
- required
- enum
- Q: 2번으로 진행하고 코드 수정도 진행해. models/.hf-cache의 다운로드 중단 파일은 삭제해
- agent-trace-v2.json
- enum
- frontier-result-v1.json
- model_validator
- type
- agent_invocations
- failures
- recommendation_resolutions
- ModelConfig
- schemas.py
- dgx-moa-agent

## God Nodes (most connected - your core abstractions)
1. `StubProvider` - 297 edges
2. `Controller` - 218 edges
3. `create_app()` - 213 edges
4. `SessionState` - 209 edges
5. `StateStore` - 165 edges
6. `Settings` - 128 edges
7. `client_with_stub()` - 111 edges
8. `lifecycle()` - 88 edges
9. `ExecutionGraphRuntime` - 59 edges
10. `responses_sse()` - 59 edges

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

## Communities (220 total, 55 thin omitted)

### Community 0 - "ExecutionGraphRuntime"
Cohesion: 0.17
Nodes (7): _bounded_ids(), ExecutionGraphRuntime, GraphEdge, GraphNode, NodeAttempt, _require_acyclic_base(), _utc_now()

### Community 1 - "test_frontier.py"
Cohesion: 0.23
Nodes (31): CodexOAuthCollaboration, FrontierConfig, asyncio, MonkeyPatch, parametrize, Path, test_app_server_auth_failure_does_not_use_cli_fallback(), test_app_server_unavailable_falls_back_once_to_stdin_exec() (+23 more)

### Community 2 - "Controller"
Cohesion: 0.07
Nodes (109): Controller, FrontierCollaborationResult, Phase, StrEnum, StateStore, test_collaborators_share_one_immutable_pre_dispatch_snapshot(), asyncio, Exception (+101 more)

### Community 3 - "StubProvider"
Cohesion: 0.06
Nodes (102): Any, StubProvider, client_with_stub(), Path, test_admin_drain_rejects_new_work_and_can_be_cancelled(), test_admin_exact_replay_is_harness_callable_and_live_comparison_stays_internal(), test_api_validation(), test_auth_enabled_invalid_key_returns_401() (+94 more)

### Community 4 - "test_streaming.py"
Cohesion: 0.06
Nodes (95): batch_goal_prerequisite_read(), batch_workspace_read(), completed_chat_sse(), forward_sse(), has_korean_script_leak(), has_non_evidence_evaluation_tool(), has_read_only_evaluation_mutation(), is_context_starved_response() (+87 more)

### Community 5 - "SpecialistRouter"
Cohesion: 0.22
Nodes (25): SpecialistRoutingConfig, MockPlannerProvider, MockReviewerProvider, SpecialistRouter, SimpleNamespace, config(), ContextAwarePlannerProvider, Any (+17 more)

### Community 6 - "EvolutionRegistry"
Cohesion: 0.11
Nodes (19): ArtifactKind, ArtifactState, EvolutionArtifact, EvolutionCandidateGenerator, EvolutionEvaluation, EvolutionRegistry, EvolutionSignal, BaseModel (+11 more)

### Community 7 - "SessionState"
Cohesion: 0.08
Nodes (27): A role-specific view that retains a verifiable link to one canonical snapshot., RoleContextProjection, active_failures(), effective_objective(), has_mcp_server_failure(), pending_goal_prerequisites(), PolicyBlocked, Any (+19 more)

### Community 8 - "context_projection.py"
Cohesion: 0.13
Nodes (24): ContributionRole, _bounded_unique(), _canonical(), CanonicalRequestInput, _content_hash(), _evidence_retention_key(), _hash(), model_contribution() (+16 more)

### Community 9 - "SkillRegistry"
Cohesion: 0.17
Nodes (27): BaseModel, SkillCandidateEvaluation, SkillMatch, SkillPattern, SkillProvenance, SkillQuery, SkillRegistry, SkillValidation (+19 more)

### Community 10 - "UsageStore"
Cohesion: 0.06
Nodes (34): classify_client(), _duration_summary(), _ewma(), lifecycle_statistics(), LifecycleSample, _percentile(), _percentiles(), Any (+26 more)

### Community 11 - "test_lifecycle.py"
Cohesion: 0.06
Nodes (113): Limits, block_real_service_commands(), lifecycle(), policy_record(), policy_usage(), policy_usage_from_gaps(), Any, asyncio (+105 more)

### Community 12 - "test_training.py"
Cohesion: 0.17
Nodes (29): candidate_from_trace(), candidates_from_trace(), ContentStore, execution_graph_training_projection(), TrainingCollector, RepositoryTrainingPolicy, eligible_trace(), parametrize (+21 more)

### Community 13 - "main"
Cohesion: 0.06
Nodes (66): CriterionState, FailureClass, KnowledgeConfidence, KnowledgeContent, KnowledgeEvidence, KnowledgeLifecycle, KnowledgeMatch, KnowledgeMetrics (+58 more)

### Community 14 - "remote_judge.py"
Cohesion: 0.08
Nodes (33): DisabledJudgeProvider, JudgeCallLimitExceeded, JudgeCriteria, JudgeEdit, JudgeEvidencePackage, JudgeFinding, JudgeProvider, JudgeProviderError (+25 more)

### Community 15 - "dgx-moa"
Cohesion: 0.05
Nodes (49): attachment, attachment, limit, modalities, name, options, reasoning, tool_call (+41 more)

### Community 16 - "replay.py"
Cohesion: 0.09
Nodes (38): contradiction_resolutions(), EvidenceEdge, EvidenceNode, Any, BaseModel, Resolve a contradiction by explicit trust rank, preserving deterministic ties., stronger_evidence(), validate_evidence_graph() (+30 more)

### Community 17 - "LifecycleStore"
Cohesion: 0.19
Nodes (7): LifecycleRecord, LifecycleStore, Any, Connection, StaleTransitionError, GuardKind, LifecycleState

### Community 18 - "observation.py"
Cohesion: 0.08
Nodes (30): ObservationBus, ObservationCommandRequest, ObservationCommandStore, ObservationEvent, ObservationNonceRequest, ObservationProvider, public_event(), Any (+22 more)

### Community 19 - "runtime_prepare.py"
Cohesion: 0.06
Nodes (76): artifact_provenance_error(), classify_failure(), download_role(), main(), Any, Exception, Path, verify_model() (+68 more)

### Community 20 - "execution_graph.py"
Cohesion: 0.12
Nodes (24): _checkpoint_hash(), compact_session_active_state(), execution_graph_parity(), ExecutionGraph, _graph_hash(), GraphBudget, GraphCheckpoint, GraphCheckpointIncompatible (+16 more)

### Community 21 - "create_app"
Cohesion: 0.08
Nodes (69): create_app(), main(), get_settings(), Settings, FakeLifecycleDriver, MockJudgeProvider, admin_dependency(), auth_dependency() (+61 more)

### Community 22 - "run-client-quality-matrix.py"
Cohesion: 0.19
Nodes (37): baseline_reasoning_effort(), codex_moa_command(), docker_command(), epoch_metrics(), filtered_env(), git(), hermes_test_evidence(), log_text() (+29 more)

### Community 23 - "RuntimeSkill"
Cohesion: 0.12
Nodes (7): Connection, field_validator, Path, Immutable, versioned Executor procedure; models may only recommend it., RuntimeSkill, SkillPackManifest, utc_now()

### Community 24 - "controller.py"
Cohesion: 0.07
Nodes (52): EvidenceNodeType, compress_messages(), compress_text(), message_fingerprint(), Any, argument_paths(), classify_failure(), clean_tool_output() (+44 more)

### Community 25 - "Qwen3.8 NVFP4 and DSpark Physical Validation"
Cohesion: 0.08
Nodes (34): Authenticated Wildcard Gateway Boundary, Bounded Compile Workers, DSpark Speculative Draft, P0 Executor Service, P0 Gateway Service, P0 Harness Service, Immutable Service Filesystems, Loopback Role Endpoints (+26 more)

### Community 26 - "asyncio"
Cohesion: 0.13
Nodes (44): ChatRequest, assert_no_request_leases(), assert_terminal_evidence(), assert_usage(), chat_endpoint(), direct_chat(), direct_review(), asyncio (+36 more)

### Community 27 - "MonkeyPatch"
Cohesion: 0.13
Nodes (19): _fixture(), Path, settings(), stub_provider(), block_profile_control(), block_real_lifecycle_and_profile_commands(), MonkeyPatch, test_admin_flag_is_checked_before_authentication_for_every_admin_endpoint() (+11 more)

### Community 28 - "test_usage.py"
Cohesion: 0.19
Nodes (32): finalization(), Any, MonkeyPatch, parametrize, Path, read_sqlite_files(), start_record(), test_active_request_count_is_not_limited_by_statistics_window() (+24 more)

### Community 29 - "config.py"
Cohesion: 0.11
Nodes (22): default_lifecycle_roles(), default_loop_budgets(), ExecutionGraphConfig, ExecutorSchedulingConfig, LifecycleRolePolicy, LiveObservationConfig, LoopEngineeringPolicy, ModelRef (+14 more)

### Community 30 - "lifecycle.py"
Cohesion: 0.13
Nodes (19): calculate_idle_policy(), _configured_quantile(), _idle_bounds(), LifecycleAutomationStatus, LifecycleFailureEvent, LoadCheck, LoadProgress, parse_load_progress() (+11 more)

### Community 31 - "LifecycleCoordinator"
Cohesion: 0.15
Nodes (6): LifecyclePolicy, LifecycleCoordinator, Apply an explicit operator enable/disable to one managed role., UnknownRoleError, LifecycleMode, Task

### Community 32 - "ModelProvider"
Cohesion: 0.17
Nodes (15): ModelProvider, Any, AsyncClient, Fit local specialist output to the context actually served by vLLM., Return measured local context fit, or None when the tokenizer is unavailable., Run bounded English analysis, then finalize the structured local plan., test_judge_is_read_only(), test_mistral_executor_does_not_put_system_messages_after_tools() (+7 more)

### Community 33 - "serve.py"
Cohesion: 0.22
Nodes (19): command(), main(), role_bool_environment(), role_context_length(), role_environment(), _sglang_command(), _vllm_command(), MonkeyPatch (+11 more)

### Community 34 - "ExecutorScheduler"
Cohesion: 0.13
Nodes (17): Future, ExecutorAdmission, ExecutorQueueFull, ExecutorQueueTimeout, ExecutorScheduler, ExecutorSchedulingError, RuntimeError, _Queued (+9 more)

### Community 35 - "build_runtime_evidence_snapshot"
Cohesion: 0.21
Nodes (24): build_runtime_evidence_snapshot(), canonical_request_input(), project_role_context(), ProjectionRole, ProjectionStage, Versioned source of truth from which every role context is independently…, runtime_evidence_item(), RuntimeEvidenceSnapshot (+16 more)

### Community 36 - "._connect"
Cohesion: 0.12
Nodes (6): Any, Connection, Path, Drop rebuildable continuation indexes without touching canonical sessions., RuntimeChannel, TraceOrigin

### Community 37 - "load_settings"
Cohesion: 0.13
Nodes (28): load_settings(), parse_bool(), Path, parametrize, Path, test_admin_key_authority_environment_is_bounded(), test_auth_disabled_allows_missing_key(), test_auth_enabled_requires_real_key() (+20 more)

### Community 38 - "ApiKeyStore"
Cohesion: 0.18
Nodes (4): ApiKeyStore, Any, Connection, Path

### Community 39 - "TrainingStore"
Cohesion: 0.17
Nodes (5): now(), Connection, Path, TrainingStore, ReviewState

### Community 40 - "weekly.py"
Cohesion: 0.17
Nodes (16): SkillMetrics, classify_knowledge(), classify_skill(), knowledge_overlap(), Any, Path, sha256(), skill_overlap() (+8 more)

### Community 41 - "type"
Cohesion: 0.09
Nodes (22): items, type, items, type, type, items, type, agent_artifacts (+14 more)

### Community 42 - "test_providers.py"
Cohesion: 0.17
Nodes (20): AsyncByteStream, CountingClient, CountingResponse, asyncio, MonkeyPatch, parametrize, test_backend_contract_reports_identity_and_supports_cancel(), test_completion_timeout_has_exact_stage() (+12 more)

### Community 43 - "CronSchedule"
Cohesion: 0.29
Nodes (4): CronSchedule, datetime, WeeklyScheduler, test_weekly_cron_uses_configured_seoul_calendar_and_rejects_unsupported_syntax()

### Community 44 - "test_trace_v2.py"
Cohesion: 0.07
Nodes (60): evaluate(), main(), Any, Path, register(), bounded(), build(), main() (+52 more)

### Community 45 - "test_weekly.py"
Cohesion: 0.20
Nodes (23): candidate_path(), previous_complete_week(), payload(), test_frozen_paired_bootstrap_passes_only_complete_covered_matrix(), test_missing_or_incomplete_pair_fails_closed_without_exclusion(), candidate(), fake_7z(), parametrize (+15 more)

### Community 46 - "Trace Usage and Adaptive Lifecycle Design"
Cohesion: 0.08
Nodes (24): Trace Usage and Lifecycle Plan, Role-Aware Adaptive Lifecycle Gap-Closure Plan, Lifecycle Activity Guards, Trace Usage and Adaptive Lifecycle Design, Single-Flight Cold Loading, External Lifecycle Control, External Ollama Reasoner Lifecycle Design, Nonblocking Systemd Activation (+16 more)

### Community 47 - "routing.py"
Cohesion: 0.13
Nodes (22): ExecutorProvider, classify_request(), optional_roles(), Any, RequestClass, RuntimeMode, Return deterministic route and machine-readable reasons., Select and pin one Executor provider using the legacy priority contract. (+14 more)

### Community 48 - "TrainingCandidate"
Cohesion: 0.13
Nodes (15): is_sensitive_key(), assess_candidate(), detect_language(), near_duplicate(), normalized_text(), Any, model_validator, sanitize() (+7 more)

### Community 49 - "properties"
Cohesion: 0.10
Nodes (21): items, type, type, type, type, type, properties, agent_decisions (+13 more)

### Community 50 - "test_client_quality_matrix.py"
Cohesion: 0.14
Nodes (16): matrix_args(), MonkeyPatch, Namespace, parametrize, Path, test_baseline_reasoning_effort_has_bounded_override(), test_codex_catalog_is_pinned_from_authenticated_gateway(), test_codex_command_uses_explicit_model_catalog() (+8 more)

### Community 51 - "Model Lifecycle Contract"
Cohesion: 0.13
Nodes (23): DSpark Speculative Decoding, Executor Scheduling, Fail-Closed Checked-In Defaults, Gateway Configuration, Judge Model, Lifecycle Configuration, Model Routing, Optional Fan-In Timeout (+15 more)

### Community 52 - "required"
Cohesion: 0.09
Nodes (23): agent_artifacts, agent_invocations, derived_confidence, evidence_graph, orchestration_decisions, reasoner_contributions, recommendation_resolutions, agent_decisions (+15 more)

### Community 53 - "properties"
Cohesion: 0.12
Nodes (16): type, type, type, properties, completion_evidence, controller_commit, observability_degraded, schema_version (+8 more)

### Community 54 - "SystemdLifecycleDriver"
Cohesion: 0.17
Nodes (9): DriverErrorKind, DriverOperation, InvalidTransitionError, LifecycleDriverError, LifecycleError, LifecycleLoadError, LifecycleNotReadyError, RuntimeError (+1 more)

### Community 55 - "api.py"
Cohesion: 0.08
Nodes (37): _chat_response_payload(), _coerce_responses_input_messages(), _coerce_responses_tools(), has_matching_tool_result(), ollama_model_ready(), openai_inference_ready(), openai_model_ready(), _public_completion_payload() (+29 more)

### Community 56 - "LiveDashboardHub"
Cohesion: 0.20
Nodes (8): LiveDashboardHub, Any, Bounded API-key-scoped projection of durable runtime events., _Subscriber, Queue, asyncio, test_live_dashboard_isolates_keys_and_redacts_operator_stream(), test_live_dashboard_replays_bounded_graph_events_or_requires_resync()

### Community 57 - "overflow_executor.py"
Cohesion: 0.18
Nodes (17): OpenAICompatibleExecutorProvider, OpenCodeGoExecutorProvider, OverflowExecutorInvalidOutput, OverflowExecutorModelFailure, OverflowExecutorUnavailable, Any, RuntimeError, OpenAI-compatible remote Executor fallback with model-only rollback. (+9 more)

### Community 58 - "runtime_status.py"
Cohesion: 0.23
Nodes (19): command(), dashboard_telemetry(), event_count(), _gpu_values(), main(), memory_available(), _memory_values(), minimum_memory() (+11 more)

### Community 59 - "ExecutionGraphStore"
Cohesion: 0.21
Nodes (8): _canonical(), ExecutionGraphStore, Any, Connection, Small SQLite persistence boundary; payloads stay strict JSON and append-only by…, _strict_loads(), _unsupported_json(), GraphEventListener

### Community 60 - "Any"
Cohesion: 0.14
Nodes (7): AcquireCallback, _MockProvider, Any, Exception, ReleaseCallback, SpecialistRole, WarmupCallback

### Community 61 - "policy.py"
Cohesion: 0.15
Nodes (12): DeclarativePolicyConfig, condition_matches(), lookup(), PolicyActions, PolicyDecision, PolicyRule, PolicySet, Any (+4 more)

### Community 62 - "compile_execution_graph"
Cohesion: 0.33
Nodes (23): compile_execution_graph(), EdgeType, NodeState, NodeType, StrEnum, Compile one of four allowlisted templates; model output is never graph…, SchedulingSnapshot, find_node() (+15 more)

### Community 63 - "enum"
Cohesion: 0.20
Nodes (10): enum, blocked, cancelled, completed, degraded, failed, ok, enum (+2 more)

### Community 64 - "security.py"
Cohesion: 0.18
Nodes (9): FastAPI, AdminCodexRequest, AdminCodexRunner, Any, BaseModel, Path, ApiKeyRequest, ApiKeyUpdate (+1 more)

### Community 65 - "ValueError"
Cohesion: 0.13
Nodes (6): Any, field_validator, model_validator, WeeklyJobsConfig, model_validator, ValueError

### Community 66 - "required"
Cohesion: 0.07
Nodes (29): context_configuration, events, metrics, model_revisions, type, completion_evidence, final_status, objective (+21 more)

### Community 67 - "properties"
Cohesion: 0.06
Nodes (35): acceptance_criteria, allowed_paths, base_commit, forbidden_actions, repository_identity, items, type, additionalProperties (+27 more)

### Community 68 - "PolicyEngine"
Cohesion: 0.28
Nodes (12): PolicyEngine, policy_set(), asyncio, test_controller_applies_policy_roles_limits_and_trace(), test_controller_blocks_missing_policy_approval_and_persists_reason(), test_controller_enforces_tool_deny_and_evidence_field_redaction(), test_policy_engine_traces_versioned_aggregated_decision(), test_policy_nonmatch_has_traceable_empty_decision() (+4 more)

### Community 69 - "properties"
Cohesion: 0.20
Nodes (10): properties, recommended_next_action, remaining_risks, root_cause, schema_version, type, type, type (+2 more)

### Community 70 - "Bounded Artifacts"
Cohesion: 0.13
Nodes (17): ExecutionGraph Configuration, Allowlisted Role Projections, Bounded Optional-Role Fan-In, Canonical Evidence Snapshot, Concurrent Pre-Dispatch Collaboration, ExecutionGraph Shadow Parity, Request-Path Telemetry, Authority and Profiles (+9 more)

### Community 71 - "Dynamic MoA Production Completion Plan"
Cohesion: 0.15
Nodes (16): Context Tuning, Legacy Profile Tuner, Phase 3 Executor Baseline, Deterministic Graph Compiler, Dynamic MoA Production Completion Plan, Dynamic MoA Completion Plan v1 Recovery Snapshot, Dynamic MoA Production Completion Plan Epoch 2, Target Topology (+8 more)

### Community 72 - "required"
Cohesion: 0.08
Nodes (25): Bronze, chosen, Gold, Negative, quality_tier, Silver, split, test (+17 more)

### Community 73 - "items"
Cohesion: 0.25
Nodes (9): items, type, additionalProperties, type, changes, validation, items, items (+1 more)

### Community 74 - "Current-Executor P0 Certification"
Cohesion: 0.20
Nodes (10): Current-Qwen Component E2E Run, Current-Executor P0 Certification, Frontier-Dominance v2 Evaluator, Frontier-Dominance v2 Release-Gate Report, Objective-Verifier Frontier Floor, Trace/Schema Fixture Only, Active Qwen3.8 27B NVFP4 and DSpark Executor, Executor Authority Layers (+2 more)

### Community 75 - "frontier.py"
Cohesion: 0.15
Nodes (19): bounded_external_evidence(), FrontierArchitectureResult, FrontierChange, FrontierDisagreementResult, FrontierExecutorFunction, FrontierExecutorToolCall, FrontierReviewResult, FrontierValidation (+11 more)

### Community 76 - "atomic_disable_lifecycle"
Cohesion: 0.29
Nodes (12): atomic_disable_lifecycle(), _fsync_directory(), main(), Path, rollback(), MonkeyPatch, Path, test_atomic_disable_is_idempotent_and_preserves_evidence() (+4 more)

### Community 78 - "RuntimeMetrics"
Cohesion: 0.22
Nodes (6): Any, Fixed, label-free metrics; event payload content is never retained., RuntimeMetrics, test_runtime_metrics_are_fixed_label_free_and_drop_event_content(), test_runtime_metrics_classify_loop_outcomes_without_reason_labels(), test_runtime_metrics_record_judge_usage_and_later_corrected_labels()

### Community 79 - "._run"
Cohesion: 0.13
Nodes (12): classify_frontier_failure(), codex_usage(), CodexAppServerTurn, _drain_bounded(), frontier_eligible(), CompletedProcess, run_codex_app_server(), run_codex_exec() (+4 more)

### Community 80 - "required"
Cohesion: 0.08
Nodes (25): context, controller, evidence, infrastructure, model, proposal_id, proposed_change, requires_human_approval (+17 more)

### Community 81 - "evidence_graph"
Cohesion: 0.15
Nodes (13): edges, nodes, items, type, additionalProperties, properties, required, type (+5 more)

### Community 82 - "type"
Cohesion: 0.15
Nodes (13): items, type, items, type, items, type, type, agent_decisions (+5 more)

### Community 83 - "Repository Instructions"
Cohesion: 0.17
Nodes (13): Authenticated Gateway Boundary, Bounded Collaboration, Codex OAuth Frontier Collaboration, dgx-moa-fast Executor-only Compatibility Path, dgx-moa Primary Reasoner and Executor Path, Exact Full Service Stop Start Executor Unload, Executor Tool Routing and Final Synthesis Authority, Knowledge Graph Refresh Workflow (+5 more)

### Community 84 - ".__init__"
Cohesion: 0.17
Nodes (8): FrontierRequiredUnavailable, JudgeCorrectionRequired, JudgeRequired, LoopAdmissionError, RuntimeError, ReasonerUnavailable, PromptRegistry, test_active_prompt_registry_changes_only_role_policy()

### Community 85 - "Client Quality Evaluation Protocol"
Cohesion: 0.17
Nodes (12): Artificial Analysis Coding Agent Index, Artificial Analysis Intelligence Index, Claude Opus 5, Client Quality Evaluation Protocol, External Anchors, Frontier Dominance v2, Frozen Local Panel, GPT-5.6 Sol (+4 more)

### Community 86 - "benchmark.py"
Cohesion: 0.36
Nodes (9): benchmark_models(), BenchmarkTask, main(), Any, Path, run(), _run_task(), summarize() (+1 more)

### Community 87 - "required"
Cohesion: 0.22
Nodes (9): changes, commit, recommended_next_action, remaining_risks, root_cause, status, schema_version, validation (+1 more)

### Community 88 - "Path"
Cohesion: 0.20
Nodes (13): codex_command(), CodexOAuthProvider, load_frontier_config(), main(), profile_home(), profile_lock(), profile_status(), Path (+5 more)

### Community 89 - "main"
Cohesion: 0.35
Nodes (11): artifact_digest(), digest_pinned(), executor_probe_command(), json_stream(), main(), option_value(), Any, CompletedProcess (+3 more)

### Community 90 - "specialists.py"
Cohesion: 0.18
Nodes (11): StageTimeout, PlannerProvider, ABC, AsyncBaseTransport, RuntimeError, RemotePlannerProvider, _RemoteProvider, RemoteReviewerProvider (+3 more)

### Community 91 - "Executor Authority"
Cohesion: 0.17
Nodes (12): Codex OAuth Frontier Configuration, Codex OAuth Frontier Example, Bounded Streaming Forwarding, Executor Sole Authority, Bubblewrap Loopback Blocker, Historical Codex Frontier Candidate-Edit Escalation, Executor Authority, External Ollama Reasoner Core (+4 more)

### Community 92 - "Deployment Authority Layers"
Cohesion: 0.20
Nodes (11): Operations, Deployment Authority Layers, Checked-In Candidate Manifest, Last Physically Promoted Deployment, PILOT_ACTIVE Release State, Current Operational State, dgx-moa, DGX MoA Agent 2.0 (+3 more)

### Community 93 - "ResponseOwnedIterator"
Cohesion: 0.18
Nodes (5): DynamicRoleUnmanagedError, RuntimeError, ResponseOwnedIterator, ResponseOwnedStreamingResponse, StreamingResponse

### Community 94 - "required"
Cohesion: 0.12
Nodes (16): agent_decisions, completion_evidence, controller_commit, evaluations, failures, final_status, observability_status, runtime_channel (+8 more)

### Community 95 - "enum"
Cohesion: 0.29
Nodes (7): benchmark, candidate_evaluation, diagnostic, production, validation, trace_origin, enum

### Community 96 - "properties"
Cohesion: 0.18
Nodes (11): type, type, properties, type, command, exit_code, path, purpose (+3 more)

### Community 97 - "evaluate"
Cohesion: 0.42
Nodes (10): digest_ok(), evaluate(), evidence_ok(), finite_number(), lower_bound(), main(), percentile(), Any (+2 more)

### Community 98 - "validate-live-client-matrix.py"
Cohesion: 0.33
Nodes (10): client_env(), git_fingerprint(), main(), port_available(), CompletedProcess, Path, run(), start_gateway() (+2 more)

### Community 99 - "Dynamic MoA Pilot Context Epoch"
Cohesion: 0.33
Nodes (6): Dynamic MoA Completion Audit, Dynamic MoA Pilot Context Epoch, Role Context Package v1, Dynamic MoA Pilot Feedback Epoch, Goal, Pilot Qualification

### Community 100 - "LifecycleDriver"
Cohesion: 0.18
Nodes (3): DriverStatus, LifecycleDriver, Protocol

### Community 101 - "normalize_openrouter_tool_calls"
Cohesion: 0.16
Nodes (10): FrontierExecutorResult, normalize_openrouter_tool_calls(), model_validator, Run one remote logical-Executor turn without granting host tool authority., Keep remote tool calls inside the client's own working directory., Keep only OpenAI-compatible fields from provider-specific tool calls., sanitize_executor_tool_paths(), test_executor_tool_calls_repair_only_known_freeform_arguments() (+2 more)

### Community 102 - "media_assets"
Cohesion: 0.38
Nodes (8): _inline_identity(), media_assets(), media_placeholders(), Any, _redacted_reference(), _reference(), test_media_identity_is_bounded_and_visible_to_runtime(), test_remote_media_reference_drops_query_and_reports_unknown_content_hash()

### Community 103 - "FrontierTask"
Cohesion: 0.31
Nodes (13): build_frontier_task(), evaluate_frontier_candidate(), FrontierResult, FrontierTask, record_frontier_run(), run_task(), validate_isolated_worktree(), validate_scope() (+5 more)

### Community 104 - "run-raw-openai-tool-loop.py"
Cohesion: 0.40
Nodes (9): completion(), emit(), execute_tool(), parse_args(), Any, Namespace, Path, run() (+1 more)

### Community 106 - ".__call__"
Cohesion: 0.22
Nodes (7): ASGIApp, DrainMiddleware, error_response(), JSONResponse, Receive, Scope, Send

### Community 107 - "capture-opencode-sse.py"
Cohesion: 0.42
Nodes (8): Client, capture(), completion_events(), expect(), main(), Any, Path, stamp()

### Community 108 - "Evidence Graph"
Cohesion: 0.20
Nodes (10): Dataset Pipeline, Training Eligibility, Evidence Graph, Deterministic Trust Ordering, Exact Replay, Execution Replay, Knowledge Lifecycle, Runtime Knowledge Base (+2 more)

### Community 109 - "Decisions"
Cohesion: 0.22
Nodes (9): Append-Oriented Traces, Branch and Worktree Policy, Decision-Trajectory Evidence, Decisions, Full-Service Stop Unload, Host vLLM 0.22.1, SQLite and Explicit State Machine, Exact Full Service Stop/Start (+1 more)

### Community 110 - "Deterministic Synthetic Baseline"
Cohesion: 0.22
Nodes (9): Benchmark-Session Mixing Prevention, Deterministic Synthetic Baseline, MVP Benchmark, Gateway MVP Boundary, MVP Scope, MVP Validation, Synthetic Six Shape Suite, Local Phase Evidence (+1 more)

### Community 111 - "providers.py"
Cohesion: 0.18
Nodes (15): make_http_client(), managed_http_client(), AsyncBaseTransport, AsyncClient, Shared HTTPX client helpers used across gateway modules., Create a single AsyncClient with optional timeout/transport overrides., Create one request-scoped AsyncClient and guarantee closure., mistral_messages() (+7 more)

### Community 112 - "state.py"
Cohesion: 0.23
Nodes (9): ChangeRisk, heavy_eligible(), needs_planner(), needs_reviewer(), completion_ready(), missing_evidence(), test_deterministic_routing_and_completion(), test_pending_tool_indexes_migrate_query_and_rollback() (+1 more)

### Community 114 - "enum"
Cohesion: 0.40
Nodes (5): candidate, dev, main, runtime_channel, enum

### Community 115 - "enum"
Cohesion: 0.33
Nodes (6): eligible, excluded, local_only, requires_review, training_eligibility, enum

### Community 116 - "enum"
Cohesion: 0.20
Nodes (10): enum, blocked, cancelled, completed, degraded, failed, ok, enum (+2 more)

### Community 117 - "FailingJudge"
Cohesion: 0.22
Nodes (5): FailingJudge, asyncio, MonkeyPatch, Path, test_validator_records_failed_case_without_raw_error()

### Community 118 - "._decision"
Cohesion: 0.36
Nodes (4): IdlePolicyDecision, PersistedIdlePolicyDecision, Path, read_latest_decisions()

### Community 119 - "test_admin_dashboard.py"
Cohesion: 0.25
Nodes (6): Any, MonkeyPatch, Path, StubFlashExecutor, test_admin_dashboard_runs_bounded_custom_provider_codex(), test_admin_dashboard_uses_live_probe_for_unmanaged_executor()

### Community 120 - "run-opencode-staging.py"
Cohesion: 0.54
Nodes (7): create_fixture(), git(), main(), output_text(), project_config(), Path, Task

### Community 121 - "summarize"
Cohesion: 0.43
Nodes (7): main(), metrics(), percentile(), Any, datetime, Path, summarize()

### Community 122 - "test_validator_atomically_preserves_sanitized_partial_progress"
Cohesion: 0.25
Nodes (5): Provider, asyncio, MonkeyPatch, Path, test_validator_atomically_preserves_sanitized_partial_progress()

### Community 123 - "Architecture"
Cohesion: 0.29
Nodes (7): Resident Executor Judge Exclusion, Architecture, Model Lifecycle, Python Gateway Decision, Qwen3.8 Resident Target, Architecture Reasoner Endpoint, Python Gateway Retention

### Community 124 - "Authenticated Gateway"
Cohesion: 0.29
Nodes (7): Codex OAuth Frontier, API Key Registry, Authenticated Gateway, Disabled Development Features, Dynamic MoA Operational Boundary, Model Invocation Rate Report, SSE Continuity Acceptance

### Community 125 - "Fail Closed Policy Enforcement"
Cohesion: 0.29
Nodes (7): Declarative Policy Engine, Fail Closed Policy Enforcement, Dry Run Retention, Privacy and Retention, Bounded Remote Quality Gate, Remote Judge, Sanitized Judge Evidence Package

### Community 126 - "Immutable Skill Promotion Gate"
Cohesion: 0.29
Nodes (7): Governed Evolution Registry, Runtime Self Improvement, Immutable Skill Promotion Gate, Skill Governance, Executor Controlled Skill Activation, Runtime Skills, Skill Registry

### Community 127 - ".acquire_request_leases"
Cohesion: 0.36
Nodes (3): LifecycleLease, Row, RequestLeaseKind

### Community 128 - "enum"
Cohesion: 0.29
Nodes (7): partial, blocked, completed, failed, status, enum, type

### Community 129 - "evaluate-paired-noninferiority.py"
Cohesion: 0.48
Nodes (6): evaluate(), main(), paired_bootstrap(), percentile(), Any, valid_digest()

### Community 130 - "validate"
Cohesion: 0.48
Nodes (6): main(), Any, Path, request_for(), validate(), write_status()

### Community 131 - "Human Approval Gate"
Cohesion: 0.33
Nodes (6): Main and Dev Branch Roles, Generated Skills Promotion Gate, Human Approval Gate, Physically Gated Features, Python Gateway Policy, Recursive Experiment Worktrees

### Community 132 - "All-Role Storage Estimate"
Cohesion: 0.33
Nodes (6): All-Role Storage Estimate, Executor Storage Estimate, Judge Storage After Resident Downloads, Judge Storage Estimate, Planner Storage Estimate, Reviewer Storage Estimate

### Community 133 - "Evidence-Based Completion Rule"
Cohesion: 0.33
Nodes (6): Measured Benchmark Registry, CI Pipeline, Bounded Collaboration Contract, Evidence-Based Completion Rule, Dynamic MoA Release Direction, Release Stage Gates

### Community 134 - "Backend-Neutral Executor and Live-Client Baseline"
Cohesion: 0.33
Nodes (6): Backend Contract, Backend-Neutral Executor and Live-Client Baseline, Four-Client Live Matrix, Remote Overflow Executor, Validation Evidence Ledger, Verified Completion Boundary

### Community 135 - "enum"
Cohesion: 0.29
Nodes (7): benchmark, candidate_evaluation, diagnostic, production, validation, trace_origin, enum

### Community 136 - "validate"
Cohesion: 0.43
Nodes (6): digest(), main(), Any, Path, usage(), validate()

### Community 137 - "Current Production Topology"
Cohesion: 0.33
Nodes (6): Checked-in Fail-Closed Manifest, Current-Executor P0 Certification Open, Current Production Topology, Loopback Reasoner Rule, Production Reasoner Endpoint Exception, Qwen3.8 Production Executor

### Community 138 - "enum"
Cohesion: 0.33
Nodes (6): conflicted, high, low, medium, enum, derived_confidence

### Community 139 - "API Client Modes"
Cohesion: 0.40
Nodes (5): Gateway Container Service, API Client Modes, Native Client Tool Loop, Authenticated OpenAI-Compatible API, Streaming Forwarding Contract

### Community 140 - "Model Compatibility"
Cohesion: 0.40
Nodes (5): Model Compatibility, GB10 vLLM Runtime Baseline, Selected Role Checkpoints, Model Downloads, Pinned Role Model Downloads

### Community 141 - "API Client Modes and Streaming Design"
Cohesion: 0.50
Nodes (5): API Client Modes and Streaming Plan, API Client Modes and Streaming Design, Executor-Only Client Modes, Immediate Bounded SSE Forwarding, Executor Native Tool Contract

### Community 142 - "Unload Mechanism and 64K Design"
Cohesion: 0.40
Nodes (5): Unload Mechanism and 64K Plan, Phase 4 Client Matrix and PR Gate Plan, Full Service Stop Fallback, Unload Mechanism and 64K Design, 65K Physical Quality Contract

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

### Community 147 - "Fail-Closed Release Certification"
Cohesion: 0.29
Nodes (7): ExecutionGraph Controller Parity, Fail-Closed Release Certification, Loopback-Only Reasoner Endpoint, Offline Rebuildable-Schema Rollback, Authenticated Gateway and Private Role Endpoint Boundary, Checked-In Fail-Closed Defaults, Preserved Phase 3 MARLIN Rollback Baseline

### Community 148 - "Operator Owned Evidence Worktrees"
Cohesion: 0.50
Nodes (4): Operator Owned Evidence Worktrees, Pilot Worktree Inventory, Isolated Improvement Flow, Recursive Improvement

### Community 149 - "codex-profile.sh"
Cohesion: 0.83
Nodes (3): codex-profile.sh script, show_status(), valid_profile()

### Community 150 - "restart-gateway-drained.sh"
Cohesion: 0.83
Nodes (3): cancel_drain(), request(), restart-gateway-drained.sh script

### Community 151 - "test_api_keys.py"
Cohesion: 0.43
Nodes (6): MonkeyPatch, Path, test_admin_key_api_separates_permissions_and_returns_no_store(), test_frontier_device_auth_is_admin_only_streamed_and_profile_bounded(), test_key_store_enforces_expiry_limits_admin_cap_and_file_mode(), test_legacy_plaintext_api_key_is_scrubbed_without_changing_credential()

### Community 152 - "Dynamic MoA v2 Model Inventory"
Cohesion: 0.67
Nodes (3): Dynamic MoA v2 Model Inventory, Executor Backend Decision, Verified Model Cleanup

### Community 205 - "required"
Cohesion: 0.33
Nodes (6): command, exit_code, path, purpose, summary, required

### Community 206 - "enum"
Cohesion: 0.33
Nodes (6): eligible, excluded, local_only, requires_review, training_eligibility, enum

### Community 207 - "Q: 2번으로 진행하고 코드 수정도 진행해. models/.hf-cache의 다운로드 중단 파일은 삭제해"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: 2번으로 진행하고 코드 수정도 진행해. models/.hf-cache의 다운로드 중단 파일은 삭제해, Source Nodes

### Community 208 - "agent-trace-v2.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $id, $schema, type

### Community 209 - "enum"
Cohesion: 0.40
Nodes (5): candidate, dev, main, runtime_channel, enum

### Community 210 - "frontier-result-v1.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $schema, title, type

### Community 212 - "type"
Cohesion: 0.50
Nodes (4): null, string, type, commit

### Community 213 - "agent_invocations"
Cohesion: 0.67
Nodes (3): items, type, agent_invocations

### Community 214 - "failures"
Cohesion: 0.67
Nodes (3): items, type, failures

### Community 215 - "recommendation_resolutions"
Cohesion: 0.67
Nodes (3): recommendation_resolutions, items, type

### Community 218 - "ModelConfig"
Cohesion: 0.19
Nodes (9): ModelConfig, ExecutorBackend, Any, ExecutorCapability, Protocol, ExecutorCapability, LocalPlannerProvider, _LocalProvider (+1 more)

### Community 219 - "schemas.py"
Cohesion: 0.16
Nodes (18): AdditionalAgentRecommendation, ChatMessage, JudgeVerdict, MandatoryChange, PlannerPlan, PlannerStep, ProfileResponse, Any (+10 more)

## Knowledge Gaps
- **413 isolated node(s):** `$schema`, `npm`, `baseURL`, `apiKey`, `attachment` (+408 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **55 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `create_app` to `ExecutionGraphRuntime`, `test_frontier.py`, `Controller`, `StubProvider`, `test_streaming.py`, `SpecialistRouter`, `SessionState`, `SkillRegistry`, `UsageStore`, `test_training.py`, `main`, `remote_judge.py`, `replay.py`, `LifecycleStore`, `observation.py`, `runtime_prepare.py`, `execution_graph.py`, `test_api_keys.py`, `controller.py`, `asyncio`, `MonkeyPatch`, `LifecycleCoordinator`, `ModelProvider`, `ExecutorScheduler`, `ApiKeyStore`, `TrainingStore`, `weekly.py`, `CronSchedule`, `test_weekly.py`, `routing.py`, `SystemdLifecycleDriver`, `api.py`, `LiveDashboardHub`, `overflow_executor.py`, `runtime_status.py`, `ExecutionGraphStore`, `compile_execution_graph`, `security.py`, `PolicyEngine`, `RuntimeMetrics`, `.__init__`, `benchmark.py`, `Path`, `ModelConfig`, `specialists.py`, `schemas.py`, `validate-live-client-matrix.py`, `LifecycleDriver`, `providers.py`, `ArchiveRegistry`, `test_admin_dashboard.py`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `ExecutionGraphRuntime`, `test_frontier.py`, `SpecialistRouter`, `SessionState`, `context_projection.py`, `SkillRegistry`, `UsageStore`, `main`, `remote_judge.py`, `replay.py`, `create_app`, `controller.py`, `ModelProvider`, `build_runtime_evidence_snapshot`, `api.py`, `ExecutionGraphStore`, `compile_execution_graph`, `PolicyEngine`, `.__init__`, `specialists.py`, `ModelConfig`, `schemas.py`, `media_assets`, `state.py`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `Settings` connect `create_app` to `security.py`, `ValueError`, `Controller`, `serve.py`, `StubProvider`, `load_settings`, `PolicyEngine`, `SkillRegistry`, `test_lifecycle.py`, `.__init__`, `execution_graph.py`, `test_admin_dashboard.py`, `api.py`, `controller.py`, `test_api_keys.py`, `asyncio`, `MonkeyPatch`, `config.py`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Are the 285 inferred relationships involving `StubProvider` (e.g. with `ModelConfig` and `test_admin_dashboard_runs_bounded_custom_provider_codex()`) actually correct?**
  _`StubProvider` has 285 INFERRED edges - model-reasoned connections that need verification._
- **Are the 153 inferred relationships involving `Controller` (e.g. with `create_app()` and `Settings`) actually correct?**
  _`Controller` has 153 INFERRED edges - model-reasoned connections that need verification._
- **Are the 86 inferred relationships involving `create_app()` (e.g. with `AdminCodexRequest` and `AdminCodexRunner`) actually correct?**
  _`create_app()` has 86 INFERRED edges - model-reasoned connections that need verification._
- **Are the 136 inferred relationships involving `SessionState` (e.g. with `create_app()` and `_run_task()`) actually correct?**
  _`SessionState` has 136 INFERRED edges - model-reasoned connections that need verification._