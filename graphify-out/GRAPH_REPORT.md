# Graph Report - MoE-MoA-Integrated-Complementary-Agent  (2026-08-15)

## Corpus Check
- 247 files · ~342,835 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3273 nodes · 9384 edges · 186 communities (135 shown, 51 thin omitted)
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 1867 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9ef07583`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ExecutionGraphRuntime
- frontier.py
- Controller
- StubProvider
- EvolutionRegistry
- SessionState
- UsageStore
- SkillRegistry
- remote_judge.py
- test_lifecycle.py
- main
- create_app
- SpecialistRouter
- observation.py
- test_streaming.py
- loop_engineering.py
- replay.py
- Dynamic MoA Production Completion Plan
- ProfileManager
- test_goal_tooling.py
- asyncio
- config.py
- ModelProvider
- ApiKeyStore
- LifecycleStore
- LifecycleCoordinator
- ._decision
- properties
- run-client-quality-matrix.py
- conftest.py
- test_state_routing.py
- policy.py
- TrainingStore
- context_projection.py
- controller.py
- StageTimeout
- state.py
- training.py
- test_usage.py
- test_specialists.py
- api.py
- weekly.py
- ExecutorScheduler
- build_runtime_evidence_snapshot
- datetime
- ModelConfig
- load_settings
- required
- type
- properties
- required
- command
- managed_http_client
- ._connect
- required
- PolicyEngine
- schemas.py
- properties
- SystemdLifecycleDriver
- redact
- improvement.py
- enum
- test_client_quality_matrix.py
- type
- LifecycleDriver
- Deterministic Synthetic Baseline
- benchmark.py
- LiveDashboardHub
- Executor Authority
- AdminCodexRunner
- atomic_disable_lifecycle
- RuntimeMetrics
- ValueError
- evidence_graph
- required
- dgx-moa
- parse_bool
- enum
- properties
- Evidence Graph
- Phase 3 Executor Baseline
- MonkeyPatch
- required
- enum
- properties
- validate-live-client-matrix.py
- Privacy-Aware Training Data Pipeline
- Repository Instructions
- .record_failure
- capture-opencode-sse.py
- Model Lifecycle Coordination
- Disabled Policy Paths
- Trace Usage and Adaptive Lifecycle Design
- enum
- enum
- enum
- items
- enum
- FailingJudge
- Dynamic MoA Pilot Context Epoch
- API Client Modes
- enum
- run-opencode-staging.py
- agent-trace-v2.json
- test_validator_atomically_preserves_sanitized_partial_progress
- enum
- Fail Closed Policy Enforcement
- Immutable Skill Promotion Gate
- lifecycle.py
- agent_invocations
- required
- evaluate-paired-noninferiority.py
- failures
- Human Approval Gate
- All-Role Storage Estimate
- recommendation_resolutions
- Model Lifecycle Contract
- test_policy_redacts_specialist_state_event_and_evaluation_boundaries
- _validate_canonical_json
- required
- enum
- validate
- Model Compatibility
- API Client Modes and Streaming Design
- Unload Mechanism and 64K Design
- agent-trace-v3.json
- frontier-result-v1.json
- remote_script
- main
- Normally Resident Executor Policy
- type
- codex-profile.sh
- restart-gateway-drained.sh
- Dynamic MoA v2 Model Inventory
- switch-profile.sh
- Adapter Registry
- Live Observation
- Python Gateway Retention Decision
- Authenticated Gateway Security Boundary
- Client-Owned Tool Execution
- Goal Continuity
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
- .project_runtime_context
- dgx-moa-agent

## God Nodes (most connected - your core abstractions)
1. `StubProvider` - 289 edges
2. `Controller` - 213 edges
3. `create_app()` - 211 edges
4. `SessionState` - 203 edges
5. `StateStore` - 156 edges
6. `Settings` - 124 edges
7. `client_with_stub()` - 107 edges
8. `lifecycle()` - 87 edges
9. `ExecutionGraphRuntime` - 57 edges
10. `responses_sse()` - 57 edges

## Surprising Connections (you probably didn't know these)
- `Phase 3 Rollback Baseline` --semantically_similar_to--> `Phase 3 Executor Baseline`  [INFERRED] [semantically similar]
  docs/OPERATIONS.md → AGENTS.md
- `Bounded Collaboration Contract` --semantically_similar_to--> `Executor Tool Routing and Final Synthesis Authority`  [INFERRED] [semantically similar]
  goal.md → AGENTS.md
- `test_auth_disabled_allows_missing_key()` --uses--> `Settings`  [INFERRED]
  tests/test_config_auth.py → gateway/src/dgx_moa/config.py
- `test_auth_enabled_requires_real_key()` --uses--> `Settings`  [INFERRED]
  tests/test_config_auth.py → gateway/src/dgx_moa/config.py
- `test_executor_scheduler_is_bounded_disabled_and_requires_flash()` --uses--> `Settings`  [INFERRED]
  tests/test_config_auth.py → gateway/src/dgx_moa/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Controlled Improvement Workflow** — agents_branch_roles, agents_knowledge_graph_refresh, agents_recursive_experiment_worktrees, agents_human_approval_gate [EXTRACTED 1.00]
- **Current Production Executor Path** — docs_state_inspected_production_release, docs_state_active_executor, docs_state_overflow_executor, docs_state_fixed_lifecycle [EXTRACTED 1.00]
- **Executor-Directed Public API Contract** — agents_executor_authority, readme_public_model_catalog, docs_api_client_modes_native_client_tool_loop, docs_architecture_role_projection_pipeline [EXTRACTED 1.00]
- **Executor Lifecycle Safety Contract** — agents_phase_3_executor_baseline, agents_exact_service_restart_unload, agents_safe_lifecycle_defaults, agents_resident_executor_policy, agents_honest_cold_response_reporting, agents_lifecycle_rollback [EXTRACTED 1.00]
- **Operational Authority Chain** — docs_operations_operations, docs_state_state, docs_validation_validation [EXTRACTED 1.00]
- **Policy-Disabled Capability Set** — docs_operations_execution_graph_shadow, docs_operations_remote_judge, docs_operations_runtime_skills, docs_operations_declarative_policy, docs_operations_training_collection, docs_operations_weekly_packaging [EXTRACTED 1.00]
- **Runtime Reliability Phases** — docs_superpowers_plans_2026_07_18_api_client_modes_streaming_api_client_modes_plan, docs_superpowers_plans_2026_07_18_lifecycle_usage_trace_lifecycle_usage_plan, docs_superpowers_plans_2026_07_19_memory_unload_64k_memory_unload_plan, docs_superpowers_plans_2026_07_19_phase_4_client_matrix_pr_gate_phase4_client_matrix_plan [EXTRACTED 1.00]
- **Structured Read-Only Role Contracts** — gateway_src_dgx_moa_prompts_planner_planner_contract, gateway_src_dgx_moa_prompts_reviewer_reviewer_contract, gateway_src_dgx_moa_prompts_judge_judge_contract [EXTRACTED 1.00]
- **Quality Evidence Gates** — docs_mvp_validation_synthetic_six_shape_suite, docs_quality_evaluation_paired_noninferiority_gate, docs_remote_judge_bounded_remote_quality_gate, docs_phase_audit_local_phase_evidence [INFERRED 0.75]
- **Dynamic MoA Bounded Collaboration** — docs_moa_orchestration_dynamic_moa_orchestration, docs_frontier_frontier_collaboration, docs_moa_orchestration_bounded_artifacts, docs_decisions_executor_authority [INFERRED 0.85]
- **Governed Promotion Controls** — docs_skill_governance_immutable_skill_promotion_gate, docs_runtime_self_improvement_governed_evolution_registry, docs_recursive_improvement_isolated_improvement_flow, docs_policy_engine_fail_closed_policy_enforcement [INFERRED 0.85]
- **Role Lifecycle and Routing** — docs_model_lifecycle_lifecycle_state_machine, docs_specialist_routing_local_remote_specialist_selection [INFERRED 0.85]
- **Role Model Capacity Planning** — config_models_role_model_topology, data_state_storage_estimate_all_all_role_storage_estimate, data_state_storage_estimate_executor_executor_storage_estimate, data_state_storage_estimate_planner_planner_storage_estimate, data_state_storage_estimate_reviewer_reviewer_storage_estimate, data_state_storage_estimate_judge_judge_storage_estimate [INFERRED 0.85]
- **Role-Specific Training Gates** — training_executor_readme_executor_training_package, training_planner_readme_planner_training_gate, training_reviewer_readme_reviewer_training_gate, docs_training_data_fail_closed_eligibility [INFERRED 0.85]
- **Runtime Evidence Continuity** — docs_evidence_graph_evidence_graph, docs_execution_replay_execution_replay, docs_dataset_pipeline_dataset_pipeline, docs_loop_engineering_loop_engineering [INFERRED 0.85]
- **Evidence-Gated Release Governance** — goal_release_stage_gates, goal_completion_rule, docs_benchmarks_measured_benchmarks [INFERRED 0.95]
- **Phase 3 Executor Safety Contract** — docs_decisions_phase_3_executor_baseline, docs_memory_optimization_memory_optimization, docs_context_tuning_context_tuning, docs_dynamic_moa_concurrent_runtime_incident_20260808_safety_disposition [INFERRED 0.95]

## Communities (186 total, 51 thin omitted)

### Community 0 - "ExecutionGraphRuntime"
Cohesion: 0.06
Nodes (61): _bounded_ids(), _canonical(), _checkpoint_hash(), compact_session_active_state(), compile_execution_graph(), EdgeType, ExecutionGraph, ExecutionGraphRuntime (+53 more)

### Community 1 - "frontier.py"
Cohesion: 0.05
Nodes (95): bounded_external_evidence(), build_frontier_task(), classify_frontier_failure(), codex_command(), codex_usage(), CodexAppServerTurn, CodexOAuthCollaboration, CodexOAuthProvider (+87 more)

### Community 2 - "Controller"
Cohesion: 0.07
Nodes (107): Controller, Phase, StrEnum, StateStore, asyncio, Exception, parametrize, test_action_budget_does_not_reopen_after_configured_limit_is_consumed() (+99 more)

### Community 3 - "StubProvider"
Cohesion: 0.06
Nodes (100): Any, StubProvider, client_with_stub(), Path, test_admin_drain_rejects_new_work_and_can_be_cancelled(), test_admin_exact_replay_is_harness_callable_and_live_comparison_stays_internal(), test_api_validation(), test_auth_enabled_invalid_key_returns_401() (+92 more)

### Community 4 - "EvolutionRegistry"
Cohesion: 0.11
Nodes (21): ArtifactKind, ArtifactState, EvolutionArtifact, EvolutionCandidateGenerator, EvolutionEvaluation, EvolutionRegistry, EvolutionSignal, PromptRegistry (+13 more)

### Community 5 - "SessionState"
Cohesion: 0.07
Nodes (32): active_failures(), argument_paths(), compact_resolved_goal_history(), effective_objective(), fingerprint(), has_mcp_server_failure(), pending_goal_prerequisites(), PolicyBlocked (+24 more)

### Community 6 - "UsageStore"
Cohesion: 0.06
Nodes (49): command(), dashboard_telemetry(), event_count(), _gpu_values(), main(), memory_available(), _memory_values(), minimum_memory() (+41 more)

### Community 7 - "SkillRegistry"
Cohesion: 0.08
Nodes (38): BaseModel, Connection, field_validator, model_validator, Path, Immutable, versioned Executor procedure; models may only recommend it., RuntimeSkill, SkillCandidateEvaluation (+30 more)

### Community 8 - "remote_judge.py"
Cohesion: 0.08
Nodes (33): DisabledJudgeProvider, JudgeCallLimitExceeded, JudgeCriteria, JudgeEdit, JudgeEvidencePackage, JudgeFinding, JudgeProvider, JudgeProviderError (+25 more)

### Community 9 - "test_lifecycle.py"
Cohesion: 0.06
Nodes (112): Limits, block_real_service_commands(), lifecycle(), policy_record(), policy_usage(), policy_usage_from_gaps(), Any, asyncio (+104 more)

### Community 10 - "main"
Cohesion: 0.11
Nodes (28): KnowledgeConfidence, KnowledgeContent, KnowledgeEvidence, KnowledgeLifecycle, KnowledgeMatch, KnowledgeMetrics, KnowledgeProvenance, KnowledgeQuery (+20 more)

### Community 11 - "create_app"
Cohesion: 0.07
Nodes (73): create_app(), main(), get_settings(), Settings, FakeLifecycleDriver, MockJudgeProvider, admin_dependency(), auth_dependency() (+65 more)

### Community 12 - "SpecialistRouter"
Cohesion: 0.16
Nodes (8): _MockProvider, Any, AsyncBaseTransport, Exception, RuntimeError, SpecialistRouter, SpecialistUnavailable, SpecialistRole

### Community 13 - "observation.py"
Cohesion: 0.08
Nodes (30): ObservationBus, ObservationCommandRequest, ObservationCommandStore, ObservationEvent, ObservationNonceRequest, ObservationProvider, public_event(), Any (+22 more)

### Community 14 - "test_streaming.py"
Cohesion: 0.05
Nodes (95): _responses_payload(), is_workspace_objective(), batch_goal_prerequisite_read(), batch_workspace_read(), compatible_edit_call(), completed_chat_sse(), forward_sse(), has_internal_protocol_leak() (+87 more)

### Community 15 - "loop_engineering.py"
Cohesion: 0.11
Nodes (39): CriterionState, FailureClass, AcceptanceCriterion, begin_iteration(), completion_ready(), consume_budget(), consume_usage(), _drop_unstable_evidence_fields() (+31 more)

### Community 16 - "replay.py"
Cohesion: 0.10
Nodes (35): contradiction_resolutions(), EvidenceEdge, EvidenceNode, Any, BaseModel, Resolve a contradiction by explicit trust rank, preserving deterministic ties., stronger_evidence(), validate_evidence_graph() (+27 more)

### Community 17 - "Dynamic MoA Production Completion Plan"
Cohesion: 0.18
Nodes (14): Context Tuning, Legacy Profile Tuner, Decisions, Phase 3 Executor Baseline, Dynamic MoA Production Completion Plan, Dynamic MoA Completion Plan v1 Recovery Snapshot, Dynamic MoA Production Completion Plan Epoch 2, Dynamic MoA Concurrent Runtime Incident (+6 more)

### Community 18 - "ProfileManager"
Cohesion: 0.10
Nodes (30): classify_failure(), download_role(), main(), Any, Exception, Path, verify_model(), cached_bytes() (+22 more)

### Community 19 - "test_goal_tooling.py"
Cohesion: 0.13
Nodes (18): evaluate(), main(), Any, Path, register(), bounded(), build(), main() (+10 more)

### Community 20 - "asyncio"
Cohesion: 0.13
Nodes (44): ChatRequest, assert_no_request_leases(), assert_terminal_evidence(), assert_usage(), chat_endpoint(), direct_chat(), direct_review(), endpoint() (+36 more)

### Community 21 - "config.py"
Cohesion: 0.16
Nodes (17): DeclarativePolicyConfig, default_lifecycle_roles(), default_loop_budgets(), ExecutionGraphConfig, ExecutorSchedulingConfig, LifecycleRolePolicy, LiveObservationConfig, LoopEngineeringPolicy (+9 more)

### Community 22 - "ModelProvider"
Cohesion: 0.14
Nodes (29): AsyncByteStream, ModelProvider, Return measured local context fit, or None when the tokenizer is unavailable., CountingClient, CountingResponse, asyncio, MonkeyPatch, parametrize (+21 more)

### Community 23 - "ApiKeyStore"
Cohesion: 0.18
Nodes (4): ApiKeyStore, Any, Connection, Path

### Community 24 - "LifecycleStore"
Cohesion: 0.22
Nodes (7): LifecycleLease, LifecycleRecord, LifecycleStore, Any, Connection, Row, LifecycleState

### Community 25 - "LifecycleCoordinator"
Cohesion: 0.11
Nodes (13): LifecyclePolicy, calculate_idle_policy(), _configured_quantile(), LifecycleCoordinator, LoadCheck, Apply an explicit operator enable/disable to one managed role., _role_usage_gaps(), RoleUsageRecord (+5 more)

### Community 26 - "._decision"
Cohesion: 0.31
Nodes (5): IdlePolicyDecision, LifecycleFailureEvent, PersistedIdlePolicyDecision, BaseModel, read_latest_decisions()

### Community 27 - "properties"
Cohesion: 0.12
Nodes (16): type, type, type, properties, completion_evidence, controller_commit, observability_degraded, schema_version (+8 more)

### Community 28 - "run-client-quality-matrix.py"
Cohesion: 0.22
Nodes (32): baseline_reasoning_effort(), codex_moa_command(), docker_command(), filtered_env(), git(), hermes_test_evidence(), log_text(), main() (+24 more)

### Community 29 - "conftest.py"
Cohesion: 0.15
Nodes (15): Path, settings(), stub_provider(), MonkeyPatch, Path, test_admin_key_api_separates_permissions_and_returns_no_store(), test_frontier_device_auth_is_admin_only_streamed_and_profile_bounded(), test_key_store_enforces_expiry_limits_admin_cap_and_file_mode() (+7 more)

### Community 30 - "test_state_routing.py"
Cohesion: 0.13
Nodes (22): ExecutorProvider, classify_request(), optional_roles(), Any, RequestClass, RuntimeMode, Return deterministic route and machine-readable reasons., Select and pin one Executor provider using the legacy priority contract. (+14 more)

### Community 31 - "policy.py"
Cohesion: 0.18
Nodes (10): condition_matches(), lookup(), PolicyActions, PolicyDecision, PolicyRule, Any, BaseModel, field_validator (+2 more)

### Community 32 - "TrainingStore"
Cohesion: 0.15
Nodes (5): now(), Connection, Path, TrainingStore, ReviewState

### Community 33 - "context_projection.py"
Cohesion: 0.12
Nodes (26): ContributionRole, _bounded_unique(), _canonical(), CanonicalRequestInput, _content_hash(), _evidence_retention_key(), _hash(), model_contribution() (+18 more)

### Community 34 - "controller.py"
Cohesion: 0.08
Nodes (39): EvidenceNodeType, classify_failure(), clean_tool_output(), DuplicateFailedCall, embedded_tool_exit_code(), failure_family(), FrontierRequiredUnavailable, JudgeCorrectionRequired (+31 more)

### Community 35 - "StageTimeout"
Cohesion: 0.17
Nodes (13): OpenCodeGoExecutorProvider, OverflowExecutorInvalidOutput, OverflowExecutorUnavailable, Any, AsyncBaseTransport, RuntimeError, Pinned OpenCode Go Executor overflow provider., StageTimeout (+5 more)

### Community 36 - "state.py"
Cohesion: 0.16
Nodes (28): validate_failure_record(), audit_traces(), export_trace(), final_status(), main(), Any, Path, Build bounded trajectory evidence; never source or hidden-reasoning archives. (+20 more)

### Community 37 - "training.py"
Cohesion: 0.10
Nodes (46): candidate_from_trace(), CandidateQualityReport, CandidateReviewRequest, candidates_from_trace(), ContentStore, detect_language(), execution_graph_training_projection(), near_duplicate() (+38 more)

### Community 38 - "test_usage.py"
Cohesion: 0.19
Nodes (31): finalization(), Any, MonkeyPatch, parametrize, Path, read_sqlite_files(), start_record(), test_active_request_count_is_not_limited_by_statistics_window() (+23 more)

### Community 39 - "test_specialists.py"
Cohesion: 0.23
Nodes (23): MockPlannerProvider, MockReviewerProvider, SimpleNamespace, config(), ContextAwarePlannerProvider, Any, asyncio, MonkeyPatch (+15 more)

### Community 40 - "api.py"
Cohesion: 0.06
Nodes (34): ASGIApp, _chat_response_payload(), _coerce_responses_input_messages(), _coerce_responses_tools(), DrainMiddleware, DynamicRoleUnmanagedError, error_response(), has_matching_tool_result() (+26 more)

### Community 41 - "weekly.py"
Cohesion: 0.11
Nodes (21): assess_candidate(), model_validator, TrainingCandidate, ArchiveRegistry, classify_knowledge(), knowledge_overlap(), prepare_candidates(), Any (+13 more)

### Community 42 - "ExecutorScheduler"
Cohesion: 0.15
Nodes (15): Future, ExecutorAdmission, ExecutorQueueFull, ExecutorQueueTimeout, ExecutorScheduler, ExecutorSchedulingError, RuntimeError, _Queued (+7 more)

### Community 43 - "build_runtime_evidence_snapshot"
Cohesion: 0.21
Nodes (24): build_runtime_evidence_snapshot(), canonical_request_input(), project_role_context(), ProjectionRole, ProjectionStage, Versioned source of truth from which every role context is independently…, runtime_evidence_item(), RuntimeEvidenceSnapshot (+16 more)

### Community 44 - "datetime"
Cohesion: 0.15
Nodes (26): datetime, candidate_path(), CronSchedule, previous_complete_week(), WeeklyScheduler, payload(), test_frozen_paired_bootstrap_passes_only_complete_covered_matrix(), test_missing_or_incomplete_pair_fails_closed_without_exclusion() (+18 more)

### Community 45 - "ModelConfig"
Cohesion: 0.16
Nodes (15): AcquireCallback, ModelConfig, SpecialistRoutingConfig, LocalPlannerProvider, _LocalProvider, LocalReviewerProvider, PlannerProvider, ABC (+7 more)

### Community 46 - "load_settings"
Cohesion: 0.18
Nodes (21): load_settings(), Path, Path, test_admin_key_authority_environment_is_bounded(), test_auth_disabled_allows_missing_key(), test_auth_enabled_requires_real_key(), test_bind_environment_overrides(), test_declarative_policy_environment_is_strict_and_disabled_by_default() (+13 more)

### Community 47 - "required"
Cohesion: 0.08
Nodes (25): context, controller, evidence, infrastructure, model, proposal_id, proposed_change, requires_human_approval (+17 more)

### Community 48 - "type"
Cohesion: 0.09
Nodes (22): items, type, items, type, type, items, type, agent_artifacts (+14 more)

### Community 49 - "properties"
Cohesion: 0.10
Nodes (21): items, type, type, type, type, type, properties, agent_decisions (+13 more)

### Community 50 - "required"
Cohesion: 0.09
Nodes (23): agent_artifacts, agent_invocations, derived_confidence, evidence_graph, orchestration_decisions, reasoner_contributions, recommendation_resolutions, agent_decisions (+15 more)

### Community 51 - "command"
Cohesion: 0.26
Nodes (14): command(), main(), role_bool_environment(), role_context_length(), role_environment(), MonkeyPatch, test_configured_context_is_default(), test_executor_defaults_to_qualified_128k_profile() (+6 more)

### Community 52 - "managed_http_client"
Cohesion: 0.11
Nodes (19): make_http_client(), managed_http_client(), AsyncBaseTransport, AsyncClient, Shared HTTPX client helpers used across gateway modules., Create a single AsyncClient with optional timeout/transport overrides., Create one request-scoped AsyncClient and guarantee closure., mistral_messages() (+11 more)

### Community 53 - "._connect"
Cohesion: 0.13
Nodes (5): Any, Connection, Path, RuntimeChannel, TraceOrigin

### Community 54 - "required"
Cohesion: 0.12
Nodes (16): agent_decisions, completion_evidence, controller_commit, evaluations, failures, final_status, observability_status, runtime_channel (+8 more)

### Community 55 - "PolicyEngine"
Cohesion: 0.28
Nodes (11): PolicyEngine, PolicySet, policy_set(), test_controller_applies_policy_roles_limits_and_trace(), test_controller_blocks_missing_policy_approval_and_persists_reason(), test_controller_enforces_tool_deny_and_evidence_field_redaction(), test_policy_engine_traces_versioned_aggregated_decision(), test_policy_nonmatch_has_traceable_empty_decision() (+3 more)

### Community 56 - "schemas.py"
Cohesion: 0.13
Nodes (23): AdditionalAgentRecommendation, ChatMessage, JudgeVerdict, MandatoryChange, PlannerPlan, PlannerStep, ProfileResponse, Any (+15 more)

### Community 57 - "properties"
Cohesion: 0.06
Nodes (35): acceptance_criteria, allowed_paths, base_commit, forbidden_actions, repository_identity, items, type, additionalProperties (+27 more)

### Community 58 - "SystemdLifecycleDriver"
Cohesion: 0.27
Nodes (4): DriverErrorKind, DriverOperation, LifecycleDriverError, SystemdLifecycleDriver

### Community 59 - "redact"
Cohesion: 0.18
Nodes (17): compress_messages(), compress_text(), message_fingerprint(), Any, is_sensitive_key(), redact(), test_compression_keeps_assistant_preceding_retained_tool_results(), test_default_tool_output_budget_preserves_small_source_files() (+9 more)

### Community 60 - "improvement.py"
Cohesion: 0.36
Nodes (13): compare(), cooldown_active(), main(), mine(), proposal_fingerprint(), Any, Path, _read() (+5 more)

### Community 61 - "enum"
Cohesion: 0.20
Nodes (10): enum, blocked, cancelled, completed, degraded, failed, ok, enum (+2 more)

### Community 62 - "test_client_quality_matrix.py"
Cohesion: 0.20
Nodes (13): matrix_args(), MonkeyPatch, Namespace, Path, test_baseline_reasoning_effort_has_bounded_override(), test_codex_catalog_is_pinned_from_authenticated_gateway(), test_codex_command_uses_explicit_model_catalog(), test_docker_command_has_stable_unique_name() (+5 more)

### Community 63 - "type"
Cohesion: 0.15
Nodes (13): items, type, items, type, items, type, type, agent_decisions (+5 more)

### Community 64 - "LifecycleDriver"
Cohesion: 0.18
Nodes (3): DriverStatus, LifecycleDriver, Protocol

### Community 65 - "Deterministic Synthetic Baseline"
Cohesion: 0.13
Nodes (15): Deterministic Synthetic Baseline, MVP Benchmark, Gateway MVP Boundary, MVP Scope, MVP Validation, Synthetic Six Shape Suite, Local Phase Evidence, Phase Completion Audit (+7 more)

### Community 66 - "benchmark.py"
Cohesion: 0.44
Nodes (9): benchmark_models(), BenchmarkTask, _fixture(), main(), Any, Path, run(), _run_task() (+1 more)

### Community 67 - "LiveDashboardHub"
Cohesion: 0.18
Nodes (9): FastAPI, LiveDashboardHub, Any, Bounded API-key-scoped projection of durable runtime events., _Subscriber, Queue, asyncio, test_live_dashboard_isolates_keys_and_redacts_operator_stream() (+1 more)

### Community 68 - "Executor Authority"
Cohesion: 0.18
Nodes (12): Codex OAuth Frontier Configuration, Codex OAuth Frontier Example, Bubblewrap Loopback Blocker, Historical Codex Frontier Candidate-Edit Escalation, Executor Authority, Target Topology, Codex OAuth Profiles, Frontier Collaboration (+4 more)

### Community 69 - "AdminCodexRunner"
Cohesion: 0.21
Nodes (8): AdminCodexRequest, AdminCodexRunner, Any, BaseModel, Path, ApiKeyRequest, ApiKeyUpdate, BaseModel

### Community 70 - "atomic_disable_lifecycle"
Cohesion: 0.29
Nodes (12): atomic_disable_lifecycle(), _fsync_directory(), main(), Path, rollback(), MonkeyPatch, Path, test_atomic_disable_is_idempotent_and_preserves_evidence() (+4 more)

### Community 71 - "RuntimeMetrics"
Cohesion: 0.22
Nodes (6): Any, Fixed, label-free metrics; event payload content is never retained., RuntimeMetrics, test_runtime_metrics_are_fixed_label_free_and_drop_event_content(), test_runtime_metrics_classify_loop_outcomes_without_reason_labels(), test_runtime_metrics_record_judge_usage_and_later_corrected_labels()

### Community 72 - "ValueError"
Cohesion: 0.26
Nodes (4): model_validator, _idle_bounds(), model_validator, ValueError

### Community 73 - "evidence_graph"
Cohesion: 0.15
Nodes (13): edges, nodes, items, type, additionalProperties, properties, required, type (+5 more)

### Community 74 - "required"
Cohesion: 0.07
Nodes (29): context_configuration, events, metrics, model_revisions, type, completion_evidence, final_status, objective (+21 more)

### Community 75 - "dgx-moa"
Cohesion: 0.18
Nodes (11): models, name, npm, options, model, dgx-moa, apiKey, baseURL (+3 more)

### Community 76 - "parse_bool"
Cohesion: 0.23
Nodes (7): parse_bool(), Any, field_validator, WeeklyJobsConfig, parametrize, test_false_boolean_forms(), test_true_boolean_forms()

### Community 77 - "enum"
Cohesion: 0.29
Nodes (7): benchmark, candidate_evaluation, diagnostic, production, validation, trace_origin, enum

### Community 78 - "properties"
Cohesion: 0.20
Nodes (10): properties, recommended_next_action, remaining_risks, root_cause, schema_version, type, type, type (+2 more)

### Community 79 - "Evidence Graph"
Cohesion: 0.20
Nodes (10): Dataset Pipeline, Training Eligibility, Evidence Graph, Deterministic Trust Ordering, Exact Replay, Execution Replay, Knowledge Lifecycle, Runtime Knowledge Base (+2 more)

### Community 80 - "Phase 3 Executor Baseline"
Cohesion: 0.12
Nodes (19): Exact Full Service Stop Start Executor Unload, Phase 3 Executor Baseline, Authenticated Gateway, Codex OAuth Frontier, Dynamic MoA Operational Boundary, Exact Service Stop/Start, Executor Lifecycle, Operations (+11 more)

### Community 81 - "MonkeyPatch"
Cohesion: 0.48
Nodes (7): block_profile_control(), block_real_lifecycle_and_profile_commands(), MonkeyPatch, test_admin_flag_is_checked_before_authentication_for_every_admin_endpoint(), test_auth_disabled_allows_inference_headers_or_none(), test_nonstream_usage_is_content_free_and_uses_opaque_server_ids(), test_runtime_status_requires_admin_auth_and_returns_safe_usage()

### Community 82 - "required"
Cohesion: 0.08
Nodes (25): Bronze, chosen, Gold, Negative, quality_tier, Silver, split, test (+17 more)

### Community 83 - "enum"
Cohesion: 0.20
Nodes (10): enum, blocked, cancelled, completed, degraded, failed, ok, enum (+2 more)

### Community 84 - "properties"
Cohesion: 0.18
Nodes (11): type, type, properties, type, command, exit_code, path, purpose (+3 more)

### Community 85 - "validate-live-client-matrix.py"
Cohesion: 0.33
Nodes (10): client_env(), git_fingerprint(), main(), port_available(), CompletedProcess, Path, run(), start_gateway() (+2 more)

### Community 86 - "Privacy-Aware Training Data Pipeline"
Cohesion: 0.20
Nodes (10): Fail-Closed Training Eligibility, Privacy-Aware Training Data Pipeline, Verified Atomic 7z Archive, Weekly Maintenance and Packaging, Read-Only Planner Contract, Independent Read-Only Reviewer Contract, Executor LoRA Configuration, Executor Training Package (+2 more)

### Community 88 - "Repository Instructions"
Cohesion: 0.25
Nodes (9): Authenticated Gateway Boundary, Bounded Collaboration, Codex OAuth Frontier Collaboration, dgx-moa-fast Executor-only Compatibility Path, dgx-moa Primary Reasoner and Executor Path, Executor Tool Routing and Final Synthesis Authority, Knowledge Graph Refresh Workflow, Operational Authority Documents (+1 more)

### Community 89 - ".record_failure"
Cohesion: 0.33
Nodes (4): LifecycleAutomationStatus, Path, read_automation_status(), _sanitize_failure_class()

### Community 90 - "capture-opencode-sse.py"
Cohesion: 0.42
Nodes (8): Client, capture(), completion_events(), expect(), main(), Any, Path, stamp()

### Community 91 - "Model Lifecycle Coordination"
Cohesion: 0.29
Nodes (8): Safe Checked-In Model Defaults, Gateway Runtime Configuration, Role Model Topology, Resident Executor Judge Exclusion, Dynamic MoA Architecture, Exact Service Stop Start, Model Lifecycle Coordination, Role Projection Pipeline

### Community 92 - "Disabled Policy Paths"
Cohesion: 0.19
Nodes (15): Declarative Policy, DeepSeek V4 Flash, dgx-moa, dgx-moa-fast, Execution Graph Shadow, OpenCode Go Specialist, Remote Judge, Runtime Skills (+7 more)

### Community 93 - "Trace Usage and Adaptive Lifecycle Design"
Cohesion: 0.12
Nodes (16): Deterministic Graph Compiler, Trace Usage and Lifecycle Plan, Role-Aware Adaptive Lifecycle Gap-Closure Plan, Lifecycle Activity Guards, Trace Usage and Adaptive Lifecycle Design, Single-Flight Cold Loading, External Lifecycle Control, External Ollama Reasoner Lifecycle Design (+8 more)

### Community 94 - "enum"
Cohesion: 0.29
Nodes (7): partial, blocked, completed, failed, status, enum, type

### Community 95 - "enum"
Cohesion: 0.40
Nodes (5): candidate, dev, main, runtime_channel, enum

### Community 96 - "enum"
Cohesion: 0.33
Nodes (6): eligible, excluded, local_only, requires_review, training_eligibility, enum

### Community 97 - "items"
Cohesion: 0.25
Nodes (9): items, type, additionalProperties, type, changes, validation, items, items (+1 more)

### Community 98 - "enum"
Cohesion: 0.29
Nodes (7): benchmark, candidate_evaluation, diagnostic, production, validation, trace_origin, enum

### Community 99 - "FailingJudge"
Cohesion: 0.22
Nodes (5): FailingJudge, asyncio, MonkeyPatch, Path, test_validator_records_failed_case_without_raw_error()

### Community 100 - "Dynamic MoA Pilot Context Epoch"
Cohesion: 0.33
Nodes (6): Dynamic MoA Completion Audit, Dynamic MoA Pilot Context Epoch, Role Context Package v1, Dynamic MoA Pilot Feedback Epoch, Goal, Pilot Qualification

### Community 101 - "API Client Modes"
Cohesion: 0.13
Nodes (15): Gateway Container Service, API Client Modes, Native Client Tool Loop, Authenticated OpenAI-Compatible API, Streaming Forwarding Contract, Immutable Canonical Evidence Snapshot, Measured Benchmark Registry, CI Pipeline (+7 more)

### Community 102 - "enum"
Cohesion: 0.33
Nodes (6): eligible, excluded, local_only, requires_review, training_eligibility, enum

### Community 103 - "run-opencode-staging.py"
Cohesion: 0.54
Nodes (7): create_fixture(), git(), main(), output_text(), project_config(), Path, Task

### Community 104 - "agent-trace-v2.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $id, $schema, type

### Community 105 - "test_validator_atomically_preserves_sanitized_partial_progress"
Cohesion: 0.25
Nodes (5): Provider, asyncio, MonkeyPatch, Path, test_validator_atomically_preserves_sanitized_partial_progress()

### Community 106 - "enum"
Cohesion: 0.40
Nodes (5): candidate, dev, main, runtime_channel, enum

### Community 107 - "Fail Closed Policy Enforcement"
Cohesion: 0.29
Nodes (7): Declarative Policy Engine, Fail Closed Policy Enforcement, Dry Run Retention, Privacy and Retention, Bounded Remote Quality Gate, Remote Judge, Sanitized Judge Evidence Package

### Community 108 - "Immutable Skill Promotion Gate"
Cohesion: 0.29
Nodes (7): Governed Evolution Registry, Runtime Self Improvement, Immutable Skill Promotion Gate, Skill Governance, Executor Controlled Skill Activation, Runtime Skills, Skill Registry

### Community 109 - "lifecycle.py"
Cohesion: 0.15
Nodes (15): InvalidTransitionError, LifecycleError, LifecycleLoadError, LifecycleNotReadyError, LoadProgress, parse_load_progress(), RuntimeError, _reported_percent() (+7 more)

### Community 110 - "agent_invocations"
Cohesion: 0.67
Nodes (3): items, type, agent_invocations

### Community 111 - "required"
Cohesion: 0.22
Nodes (9): changes, commit, recommended_next_action, remaining_risks, root_cause, status, schema_version, validation (+1 more)

### Community 112 - "evaluate-paired-noninferiority.py"
Cohesion: 0.48
Nodes (6): evaluate(), main(), paired_bootstrap(), percentile(), Any, valid_digest()

### Community 113 - "failures"
Cohesion: 0.67
Nodes (3): items, type, failures

### Community 114 - "Human Approval Gate"
Cohesion: 0.33
Nodes (6): Main and Dev Branch Roles, Generated Skills Promotion Gate, Human Approval Gate, Physically Gated Features, Python Gateway Policy, Recursive Experiment Worktrees

### Community 115 - "All-Role Storage Estimate"
Cohesion: 0.33
Nodes (6): All-Role Storage Estimate, Executor Storage Estimate, Judge Storage After Resident Downloads, Judge Storage Estimate, Planner Storage Estimate, Reviewer Storage Estimate

### Community 116 - "recommendation_resolutions"
Cohesion: 0.67
Nodes (3): recommendation_resolutions, items, type

### Community 117 - "Model Lifecycle Contract"
Cohesion: 0.33
Nodes (6): Exact Full Service Stop Start, Honest Loading Progress, Lifecycle State Machine, Model Lifecycle Contract, Dynamic Specialist Routing, Local Remote Specialist Selection

### Community 120 - "required"
Cohesion: 0.33
Nodes (6): command, exit_code, path, purpose, summary, required

### Community 121 - "enum"
Cohesion: 0.33
Nodes (6): conflicted, high, low, medium, enum, derived_confidence

### Community 122 - "validate"
Cohesion: 0.43
Nodes (6): digest(), main(), Any, Path, usage(), validate()

### Community 123 - "Model Compatibility"
Cohesion: 0.40
Nodes (5): Model Compatibility, GB10 vLLM Runtime Baseline, Selected Role Checkpoints, Model Downloads, Pinned Role Model Downloads

### Community 124 - "API Client Modes and Streaming Design"
Cohesion: 0.50
Nodes (5): API Client Modes and Streaming Plan, API Client Modes and Streaming Design, Executor-Only Client Modes, Immediate Bounded SSE Forwarding, Executor Native Tool Contract

### Community 125 - "Unload Mechanism and 64K Design"
Cohesion: 0.40
Nodes (5): Unload Mechanism and 64K Plan, Phase 4 Client Matrix and PR Gate Plan, Full Service Stop Fallback, Unload Mechanism and 64K Design, 65K Physical Quality Contract

### Community 126 - "agent-trace-v3.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $id, $schema, type

### Community 127 - "frontier-result-v1.json"
Cohesion: 0.40
Nodes (4): additionalProperties, $schema, title, type

### Community 128 - "remote_script"
Cohesion: 0.60
Nodes (4): encoded(), main(), Any, remote_script()

### Community 129 - "main"
Cohesion: 0.80
Nodes (4): ending_repository(), git(), main(), Path

### Community 130 - "Normally Resident Executor Policy"
Cohesion: 0.67
Nodes (4): Honest Cold Response Reporting, Lifecycle Rollback Procedure, Normally Resident Executor Policy, Safe Disabled Lifecycle Defaults

### Community 132 - "type"
Cohesion: 0.50
Nodes (4): null, string, type, commit

### Community 133 - "codex-profile.sh"
Cohesion: 0.83
Nodes (3): codex-profile.sh script, show_status(), valid_profile()

### Community 134 - "restart-gateway-drained.sh"
Cohesion: 0.83
Nodes (3): cancel_drain(), request(), restart-gateway-drained.sh script

### Community 135 - "Dynamic MoA v2 Model Inventory"
Cohesion: 0.67
Nodes (3): Dynamic MoA v2 Model Inventory, Executor Backend Decision, Verified Model Cleanup

## Knowledge Gaps
- **355 isolated node(s):** `$schema`, `npm`, `baseURL`, `apiKey`, `model` (+350 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **51 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `create_app` to `ExecutionGraphRuntime`, `frontier.py`, `Controller`, `StubProvider`, `EvolutionRegistry`, `SessionState`, `UsageStore`, `SkillRegistry`, `remote_judge.py`, `main`, `SpecialistRouter`, `observation.py`, `test_streaming.py`, `replay.py`, `ProfileManager`, `asyncio`, `ModelProvider`, `ApiKeyStore`, `LifecycleStore`, `LifecycleCoordinator`, `conftest.py`, `test_state_routing.py`, `TrainingStore`, `controller.py`, `StageTimeout`, `state.py`, `training.py`, `api.py`, `weekly.py`, `ExecutorScheduler`, `datetime`, `ModelConfig`, `managed_http_client`, `PolicyEngine`, `schemas.py`, `SystemdLifecycleDriver`, `redact`, `LifecycleDriver`, `LiveDashboardHub`, `AdminCodexRunner`, `RuntimeMetrics`, `validate-live-client-matrix.py`, `lifecycle.py`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `ExecutionGraphRuntime`, `frontier.py`, `EvolutionRegistry`, `SessionState`, `UsageStore`, `SkillRegistry`, `remote_judge.py`, `main`, `create_app`, `SpecialistRouter`, `loop_engineering.py`, `replay.py`, `ModelProvider`, `context_projection.py`, `controller.py`, `StageTimeout`, `api.py`, `build_runtime_evidence_snapshot`, `PolicyEngine`, `schemas.py`, `.project_runtime_context`, `test_policy_redacts_specialist_state_event_and_evaluation_boundaries`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Why does `SessionState` connect `SessionState` to `ExecutionGraphRuntime`, `frontier.py`, `Controller`, `StubProvider`, `EvolutionRegistry`, `SkillRegistry`, `remote_judge.py`, `main`, `create_app`, `loop_engineering.py`, `controller.py`, `state.py`, `api.py`, `._connect`, `PolicyEngine`, `redact`, `.project_runtime_context`, `benchmark.py`, `test_policy_redacts_specialist_state_event_and_evaluation_boundaries`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 277 inferred relationships involving `StubProvider` (e.g. with `ModelConfig` and `test_admin_dashboard_runs_bounded_custom_provider_codex()`) actually correct?**
  _`StubProvider` has 277 INFERRED edges - model-reasoned connections that need verification._
- **Are the 148 inferred relationships involving `Controller` (e.g. with `create_app()` and `Settings`) actually correct?**
  _`Controller` has 148 INFERRED edges - model-reasoned connections that need verification._
- **Are the 85 inferred relationships involving `create_app()` (e.g. with `AdminCodexRequest` and `AdminCodexRunner`) actually correct?**
  _`create_app()` has 85 INFERRED edges - model-reasoned connections that need verification._
- **Are the 131 inferred relationships involving `SessionState` (e.g. with `create_app()` and `_run_task()`) actually correct?**
  _`SessionState` has 131 INFERRED edges - model-reasoned connections that need verification._