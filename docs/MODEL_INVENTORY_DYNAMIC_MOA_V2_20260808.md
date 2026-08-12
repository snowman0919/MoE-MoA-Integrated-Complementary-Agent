# Dynamic MoA v2 model inventory

- captured_at: `2026-08-08T15:49:10+09:00`
- filesystem: `/dev/nvme0n1p2`
- free_before_cleanup: `103755317248` bytes
- policy: production/rollback/service/config/test reference가 있거나 pinned upstream 복구를
  검증하지 못한 model은 보존한다.

## Target models

| Role | Repository | Pinned revision | Upstream bytes | Local state | Decision |
| --- | --- | --- | ---: | --- | --- |
| Executor | `mistralai/Mistral-Small-4-119B-2603-NVFP4` | `b1a9048590131d38491bd23a7c9f6ed0962f0358` | `70846528432` | canonical cache verified 23/23; vLLM load failed global OOM | retain evidence; no deploy or same-profile retry |
| Reasoner | remote Ollama `Qwythos-v2-9B:Q4` | remote runtime | `7680305397` VRAM measured | `http://100.90.167.128:11434` | retain external; no HF pull |

Mistral repository는 2026-08-08 Hugging Face metadata로 revision/license를 검증했다.
`config.json`이 없는 Mistral consolidated layout이므로 backend는 이름만으로 지원
가능하다고 추정하지 않고 isolated load로 판정한다.

## Executor runtime and backend decision

- Runtime model: `mistralai/Mistral-Small-4-119B-2603-NVFP4` at the pinned
  revision above.
- Serving backend: vLLM first. Keep the Phase 3 safety envelope for the first
  physical gate: context `65536`, one sequence, `1700000000` KV bytes, and
  `gpu_memory_utilization=0.5`.
- The canonical cache passed checksum verification. Deployment remains blocked
  because the required isolated vLLM load failed before readiness with a global
  OOM; downstream API and unload checks were not run.

| Backend | Checkpoint evidence | Local/operational verdict |
| --- | --- | --- |
| vLLM | model card says recommended and provides exact serve flags; checkpoint is tagged `vLLM` and `compressed-tensors` | physical fail: the required 64K/one-sequence/1.7-GB-KV/0.5/MARLIN profile never reached readiness and caused global OOM; no same-profile retry |
| SGLang | model card marks support WIP; later upstream release lists Mistral Small 4 support | second physical candidate; installed 2026-07-25 image contains Mistral3, Mistral reasoning, compressed-tensors NVFP4, and NVFP4 MoE code, but still needs exact load/API validation |
| TensorRT-LLM / Triton | NVIDIA documents NVFP4 and `Mistral3ForConditionalGeneration` support | hold; exact Small 4 checkpoint and GB10 SM121 combination is not named in the current matrices |
| NVIDIA Dynamo | can orchestrate vLLM, SGLang, or TensorRT-LLM workers | not a competing inference engine; unnecessary for the current single-node, one-sequence path |
| Mistral `mistral-inference` | understands Mistral consolidated weights | reject for serving: upstream repository was archived on 2026-05-18 and does not list Small 4 |
| Hugging Face TGI | OpenAI-compatible serving exists | reject: maintenance mode and published quantization list does not include NVFP4 |
| llama.cpp / Docker Model Runner | broad local serving, GGUF-oriented | reject for this checkpoint: local image is llama.cpp `b9592`; conversion would create a different artifact and exact architecture parity is unverified |
| Transformers | useful reference loader/API | not a production backend candidate without a separate server and proven native NVFP4 path |

Primary references: [checkpoint card](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603-NVFP4),
[vLLM releases](https://github.com/vllm-project/vllm/releases),
[SGLang releases](https://github.com/sgl-project/sglang/releases),
[TensorRT-LLM model support](https://nvidia.github.io/TensorRT-LLM/models/supported-models.html),
[TensorRT-LLM quantization support](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/features/quantization.md),
[Mistral self-deployment](https://docs.mistral.ai/models/deployment/local-deployment),
[archived mistral-inference](https://github.com/mistralai/mistral-inference), and
[TGI status/quantization](https://github.com/huggingface/text-generation-inference).

## Retained local models

| Path | Repository/revision | Bytes | Evidence hash | References | Decision |
| --- | --- | ---: | --- | --- | --- |
| `/home/kotori9/models/dgx-moa/planner` | revision `49cee6bbed2edd4e2d305d948ac443714a2ab242` | `20768194560` | index `818afd13fd01b22dddb6215ed2fb7cf51c80b4ba889a4105d7436a41e0724fde` | legacy rollback | retain |
| `/home/kotori9/models/dgx-moa/reviewer` | `CohereLabs/North-Mini-Code-1.0-w4a16@1e55f4aa327aba4c0b7a1da0d0f24626d3af5c90` | `19383128064` | index `b02d9e50292c32873ac715b78b355714c754790f16a82e124e1e5ec67da0df86` | checked-in config/rollback | retain |
| `/home/kotori9/models/dgx-moa/reasoner` | existing Qwen2-based revision `77bd2cced09193c8b9a59a32bd8577bbd1f3e01c` | `6189162496` | index `7b85f79fd7612df2e5d7f03d7f92d65c8967f790a331146ca7f45658823060d3` | existing Reasoner rollback; differs from target Qwen3.5 model | retain through ablation |
| `/home/kotori9/models/specialist-unified-qwen36-27b-nvfp4` | `nvidia/Qwen3.6-27B-NVFP4@0893e1606ff3d5f97a441f405d5fc541a6bdf404` | `21941772288` | index `7aa103a2582b7d26631988de33dea19e8a308ee9c239e8e14feb374af30905e2` | checked-in/installed base Planner unit | retain until remote Planner gate+rollback |
| `/home/kotori9/models/specialist-unified-llama33-nemotron-super-49b-nvfp4` | repository ID unresolved; local revision `f0caaafd5152e07527c7a14e04aa67823107529f` | `31090679808` | index `60cb49e173b418153e2f93f5eba8dfeec64dbf30647f2cc092c7309d0c84f519` | upstream recovery `MISSING` | retain fail-closed |

`last_used`는 신뢰할 runtime invocation provenance가 없는 모델에 대해 파일 mtime으로
대체하지 않는다. 2026-07-25~30 download mtimes는 inventory metadata일 뿐 사용 증거가 아니다.

## Immediate cleanup candidates

| Exact path | Repository/revision | Bytes | Evidence hash | Reference and evidence verdict |
| --- | --- | ---: | --- | --- |
| `/home/kotori9/models/specialist-unified-devstral-24b` | `mistralai/Devstral-Small-2-24B-Instruct-2512@55c5b41e98c2dbd21b0c8afffc540dcfc9eb5128` | `25827393536` | model index `f6a3dddc47d001996444ad67e30c5742980fe2c3cff63cc1e28c57c4d24a2c0e` | rejected role-quality candidate; current service/config/test path refs 0; failed evidence preserved in stash/preservation ref; upstream verified |
| `/home/kotori9/models/specialist-unified-gpt-oss-20b` | `openai/gpt-oss-20b@6cee5e81ee83917806bbde320786a8fb61efebee` | `27540295680` | model index `0e085b977c4c9942f85938828e8c989ed7d5cdabf852e4da6a67c116cd502cd1` | current service/config/test/evidence path refs 0; upstream verified; includes local Metal copy |
| `/home/kotori9/models/specialist-unified-nemotron3-nano-30b-nvfp4` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4@ce1b118ae66ec705d02c241525192832eb045fd3` | `19362910208` | model index `e076394997f518b64a2b81b9648a58063faa611c95a1d5fb5495e77194e5dfb7` | rejected structured/privacy/parser gate; current service/config/test path refs 0; failure evidence preserved; upstream verified |

Planned exact recovery: `72730599424` bytes. 삭제 직전 다음을 다시 검증한다.

```text
각 exact path가 /home/kotori9/models 바로 아래의 예상 directory인지
active process argv/map reference 0
installed unit/config/current worktree reference 0
revision metadata와 evidence index hash 일치
filesystem free-space before snapshot
```

삭제 후 exact paths absent, 다른 model paths unchanged, free-space delta와 복구 repository를
기록한다. 삭제된 weight는 local recovery 불가지만 위 pinned public upstream에서 다시 받을 수 있다.

### Superseded Qwen3-Next and Gemma 4 cleanup

- stopped `dgx-moa-planner.service` before removing its mapped Gemma weights;
  service and GPU compute process were then absent.
- removed exact paths:
  - `/home/kotori9/models/dgx-moa/executor`
  - `/home/kotori9/models/experimental/qwen3-coder-next-modelopt-nvfp4-15c399c8`
  - `/home/kotori9/models/experimental/gemma-4-26b-a4b-nvfp4-a19cfe00`
- measured free-space delta: `111458578432` bytes.
- recovery: no local trash/backup; exact public upstream revisions remain recorded
  in the former inventory entries and Git history.

## Cleanup result

- removed_at: `2026-08-08`
- removed exact paths: 위 immediate cleanup candidates 3개만.
- free_before: `103754584064` bytes.
- free_after: `176485163008` bytes.
- measured free-space delta: `72730578944` bytes.
- retained model path checks: 8/8 present.
- recovery: local trash/backup 없음; pinned public upstream에서 재다운로드 가능.

The `8/8` retained-path result above is the immediate authorized-cleanup
snapshot. Later concurrent filesystem and runtime mutations changed that state;
their actor is not adjudicated here. The current measured cache completion,
unexpected retained-path absence, vLLM global-OOM failure, and gateway recovery
are recorded in `docs/DYNAMIC_MOA_CONCURRENT_RUNTIME_INCIDENT_20260808.md`.
