Research Capability Benchmark Gate

Include Humanity’s Last Exam and SciCode as mandatory, pre-frozen research-capability strata within the blind non-inferiority protocol.

Evaluate each system under identical revisions, prompts, tool permissions, context budgets, timeout rules, retry limits, and hardware or provider conditions.

Run at least:

HLE text-only, closed-book
HLE multimodal, closed-book where supported
SciCode model-only
SciCode full-runtime with tools and execution
Private hidden research tasks derived from real project domains

Keep model-only and full-runtime results separate.

For each system and benchmark, report:

accuracy or resolve rate
pass@1 and pass@3 where applicable
domain-stratified score
calibration
false approval and false rejection
time to first useful result
time to verified result
p50 and p95 latency
cost per attempted task
cost per solved task
tool and execution failure rate
run-to-run reproducibility

Perform component ablations for:

Executor only
Executor + Reasoner
+ Planner
+ Reviewer
+ Judge
Full Dynamic MoA

Use paired tasks, frozen scoring rules, bootstrap confidence intervals, and a predeclared non-inferiority margin.

Do not claim non-inferiority when:

the confidence interval crosses the frozen margin
telemetry is incomplete
sample size is below the frozen requirement
benchmark contamination is suspected
task execution differs materially between systems
or any result is INCONCLUSIVE

Public benchmark success alone is insufficient. The private hidden set must include representative work from:

FPGA and RTL
RISC-V
embedded systems
robotics and ROS2
LLM inference systems
scientific computing
new-paper implementation
repository-scale experimental engineering

Preserve all failed runs and historical protocol epochs.

Any change to benchmark prompts, scoring, task selection, tool access, timeout, retry policy, or system topology invalidates cross-epoch comparison and requires a new evaluation epoch.
