# Dynamic MoA Imagegen Addendum

동결일: 2026-07-27 KST
대상 계획: `docs/DYNAMIC_MOA_COMPLETION_PLAN.md`
protocol ID: `imagegen-capability-v1`

이 addendum은 기존 동결 계획과 품질 평가 protocol을 덮어쓰지 않는다.
imagegen 구현·prompt·scorer·model·artifact 검사가 바뀌면 이전 결과를
진단 자료로 보존하고 새 protocol ID와 hash를 만든다.

## 안전 경계

- 기존 Codex OAuth Frontier는 계속 `read-only`이며 host 도구나 파일 변경
  권한을 받지 않는다.
- image generation은 Frontier collaboration과 분리된 Executor 전용
  `generate_image` capability다. 생성 호출은 Executor가 선택하고 gateway가
  검증하며 다른 역할은 호출할 수 없다.
- provider는 Codex OAuth의 명시적 `$imagegen` skill과 built-in
  `gpt-image-2`만 허용한다. OpenRouter fallback과 API-key 기반 OpenAI Image
  API를 사용하지 않는다.
- 기능은 기본 비활성이다. 아래 모든 물리 gate가 통과한 고정 config에서만
  활성화한다.
- prompt, hidden reasoning, OAuth material, credential, raw Codex event/output을
  trace, metric, usage table, audit event, training archive에 저장하지 않는다.

## 요청·인증·사용량

- 기존 authenticated inference 요청 안에서 Executor만 `generate_image`를
  선택할 수 있다. admin endpoint나 Planner/Reviewer/Reasoner/Frontier가
  대신 호출할 수 없다.
- API key의 기존 expiry/revocation/request/token quota를 먼저 적용하고,
  별도의 content-free image invocation quota를 적용한다.
- 한 tool call은 한 image만 생성한다. 동시 생성은 profile singleflight로
  직렬화하고 timeout/cancellation 후 동일 generation을 재사용하거나
  명확히 실패한다.
- audit에는 opaque artifact ID, safe API-token ID, provider/model, status,
  latency, byte size, 검증 결과만 남긴다. prompt와 host path는 남기지 않는다.

## 비밀값·artifact 경계

- prompt를 Codex에 보내기 전에 기존 credential redaction을 적용한다.
  redaction 결과가 원문과 다르면 요청을 fail closed한다.
- 출력은 owner-only artifact root 아래의 새 opaque directory에만 허용한다.
  caller가 host output path를 지정할 수 없다.
- 최종 artifact는 regular file, canonical root containment, 허용된 PNG/JPEG/
  WebP magic, nonzero size, configurable 최대 byte, 이미지 dimension 상한,
  mode `0600`을 모두 검증한다.
- symlink, hard-link escape, executable/HTML/SVG, 다중 artifact, 기존 파일
  overwrite, 외부 URL만 반환하는 결과는 거부한다.
- 실패한 임시 artifact는 해당 generation directory 안에서만 제거하며 다른
  generation이나 Codex profile 파일을 삭제하지 않는다.

## 물리 capability probe

고정 Codex CLI/version과 OAuth profile에서 다음을 새 immutable run ID로
검증한다.

1. `codex exec --sandbox read-only`가 명시적 `$imagegen`을 선택한다.
2. provider provenance가 Codex OAuth이고 image model이 `gpt-image-2`임을
   신뢰 가능한 event/tool metadata에서 확인한다.
3. 생성 artifact를 owner-only root로 가져와 magic, dimension, byte,
   containment, permission 검사를 통과한다.
4. prompt와 raw event를 저장하지 않은 content-free audit/usage row가
   정확히 한 건 생성된다.
5. 미인증, quota 초과, credential-shaped prompt, malformed event, timeout,
   cancellation, symlink, oversized/non-image artifact가 fail closed한다.
6. 같은 OAuth profile의 기존 read-only Frontier 호출과 상호 잠금되어
   credential/profile state를 손상하지 않는다.
7. 활성화 전 전체 Ruff, strict mypy, 전체 테스트와 실제 생성 canary를
   통과한다.

모든 gate가 통과하기 전 `generate_image`는 capability/status에
`disabled_unverified`로만 노출한다. 물리 probe가 현재 Codex surface에서
`$imagegen` 또는 `gpt-image-2` provenance를 증명하지 못하면 구현을
활성화하지 않고 `BLOCKED` 증거를 보존한다.
