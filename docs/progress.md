# 진행 상황

새 세션은 이 문서부터 읽는다. 마지막 갱신은 2026-11-03이다.

## 목표

- RTX 5070 Ti 16GB에서 도는 로컬 LLM으로 근로기준법 중심 상담봇을 만든다. 답변마다 근거 조문을 보여준다.
- 개발 과정에서 AI 에이전트를 잘 쓰는 방법을 익힌다. 병렬 작업, 검토 분리, 지시문 작성이 대상이다.
- 전체 계획은 [roadmap.md](roadmap.md)에 있다. 지금은 1단계 RAG MVP의 후반이다.

## 현재 위치

| 단계 | 상태 |
| --- | --- |
| 환경 (Ollama, uv, 모델 3개) | 완료 |
| 법령 수집 `collect.py` | 완료. 법령 5개 본문(`eflaw`), 법률 4개 연결표 |
| 평가 질문 41개 | 완료. 다른 모델의 원문 대조 2회. [eval/README.md](../eval/README.md) |
| 공유 설정과 계약 | 완료. `config.py`, `models.py`, `search.get_chunks`, 실행 명령 3개 |
| 청킹, 임베딩, 검색 | 시작 전. 브랜치 `feat/index` |
| 답변 생성, `ask` | 시작 전. 브랜치 `feat/answer` |
| 평가 스크립트 `eval` | 시작 전. 브랜치 `feat/evaluate` |
| 기준선 `eval/baseline.json` | 위 세 개를 병합한 뒤 |

`main`은 `origin/main`보다 3커밋 앞서 있다. 아직 푸시하지 않았다.

## 진행 중인 병렬 작업

worktree 3개가 `main`의 `69a706f`에서 만들어져 있다. 각 폴더에서 `claude`를 실행하고 [prompts/round2.md](prompts/round2.md)의 지시문을 붙여넣는다.

| worktree | 브랜치 | 수정 파일 |
| --- | --- | --- |
| `lawbot-index` | `feat/index` | `index.py`, `search.py`, `tests/test_index.py`, `tests/test_search.py` |
| `lawbot-answer` | `feat/answer` | `answer.py`, `cli.py`, `tests/test_answer.py`, `tests/test_cli.py` |
| `lawbot-evaluate` | `feat/evaluate` | `evaluate.py`, `tests/test_evaluate.py` |

세 작업 모두 `pyproject.toml`, `uv.lock`, `models.py`, `config.py`를 고치지 않는다. 고쳐야 하면 멈추고 보고하게 했다. `lawbot-evaluate`에만 `.env`를 복사했다. 채점에 Claude API 키가 필요하기 때문이다.

## 병합 전 검증

에이전트의 보고를 믿지 말고 아래를 직접 확인한다. 범위를 벗어난 파일 변경은 공통으로 본다.

```bash
git diff --stat main..feat/index
```

### 공통

- 지정한 파일 밖의 변경이 없다. 특히 공유 파일 4개가 그대로다.
- 해당 worktree에서 `uv run pytest`가 통과한다.
- 커밋과 파일에 인증키가 없다. 키 값을 `git grep -F`로 커밋마다 찾는다. 키를 출력하지 않는다.
- 보고에 요청한 항목이 모두 있다.

### `feat/index`

- 청크 ID가 `eval/questions.jsonl`의 모든 `required`와 정확히 일치한다. 남녀고용평등법 가운뎃점은 U+318D(`ㆍ`)다.
- 조문 수가 원문과 맞는다. 2026-11-02 수집본 기준으로 근로기준법 132개, 시행령 80개, 최저임금법 34개, 퇴직급여법 68개, 남녀고용평등법 72개다. 별표는 근로기준법 1개, 시행령 7개다.
- 조문여부가 `전문`인 장 제목 행은 청크가 아니다.
- 근로기준법 제11조의 `refs`에 시행령 제7조가 있고, 시행령 제7조의 `refs`에 근로기준법 제11조와 시행령 별표 1이 있다.
- 근로기준법 제13조의 `pending_effective_dates`에 `20261208`이 있다.
- `uv run index`를 두 번 실행해도 저장 개수가 같다.
- `search`가 refs를 따라 확장하지 않는다. 기준선은 단순 검색으로 낸다.

### `feat/answer`

- `Answer.text`의 끝에 출처 목록과 `config.DISCLAIMER`가 항상 붙는다. 청크가 비어 있을 때도 붙는다.
- 모델이 쓴 범위 밖의 `[번호]`는 `cited_ids`에서 빠진다.
- 실제 답변 3개(q001, q006, q030)를 읽고 원문에 없는 내용을 지어냈는지 본다. q030은 `해석필요` 유형이라 단정하지 않아야 한다.
- `prompt_eval_count`가 `NUM_CTX` 8192보다 충분히 작다.

### `feat/evaluate`

- `--only search`는 LLM을 호출하지 않는다.
- `근거없음` 문항은 검색 점수에서 빠진다.
- 채점 요청에 `temperature`, `top_p`, `top_k`가 없다. 2026-10-21부터 Claude API가 이 값을 거부한다.
- 같은 답변을 다시 채점하지 않는다. 캐시 키를 확인한다.
- 실제 채점 호출 1회의 결과와 토큰 사용량을 확인한다.

## 병합 후 순서

1. `feat/index`, `feat/answer`, `feat/evaluate` 순서로 `main`에 병합하고 `uv run pytest`를 돌린다.
2. `uv run index`로 Chroma를 만든다.
3. `uv run ask "5인 미만 사업장도 연차가 있나요?"`로 끝까지 동작하는지 본다.
4. `uv run eval --only search`로 검색 점수를 본다. 복합 유형 점수는 낮을 것으로 예상한다.
5. `uv run eval`로 전체 점수를 낸다. `LAWBOT_CHAT_MODEL=gemma4:12b-it-q4_K_M`으로 한 번 더 돌려 Qwen과 비교한다.
6. 채점자 확인: Haiku의 판정 일부를 직접 읽는다. 틀린 답을 맞다고 한 경우가 많으면 채점 모델을 `claude-sonnet-5-5`로 올린다.
7. 기준으로 삼을 결과를 `--save-baseline`으로 저장하고 커밋한다.
8. 점수가 낮은 문항은 정답지도 의심한다. 검토를 두 번 했지만 사람이 전부 본 것은 아니다.

## 결정 사항

| 결정 | 이유 |
| --- | --- |
| 법령 본문은 `target=eflaw` | `target=law`는 시행 전 문구를 현행처럼 준다 |
| 시행령은 `thdCmp`를 받지 않음 | 응답에 쓸 연결이 없다. [law-api.md](law-api.md) |
| 기준선은 refs 확장 없는 단순 벡터 검색 | 개선 효과를 점수로 비교하기 위해 |
| 채팅 기본 모델 `qwen3.5:9b-q8_0` | 임시. 5단계에서 Gemma와 비교해 정한다 |
| 채점 모델 `claude-haiku-5-5` | 비용이 작다. 사람 판정과 비교해 부족하면 올린다 |
| 평가 유형 `해석필요` 추가 | 조문만으로 답이 안 정해지는 질문을 빼면 점수가 부풀려진다 |
| 시행 예정 조문은 미리 넣지 않음 | 시행일이 지나면 다시 수집한다. 답변에는 예정일만 표시한다 |
| Chroma 사용 | 서버가 필요 없고 worktree마다 따로 둔다. 청크 약 400개 규모 |
| 병렬은 2~3개 | 파일이 겹치지 않는 작업만 나눈다 |

## 환경 메모

- 폴더: `<작업 폴더>\lawbot`. worktree는 그 옆에 만든다.
- 원격: `https://github.com/atlanboa/lawbot` (비공개). `gh`로 로그인되어 있다.
- `.env`: `LAW_API_OC`, `ANTHROPIC_API_KEY`. 각 worktree에는 필요한 경우만 복사한다. `dev-digging\.env`는 저장소 밖 파일이고 코드가 읽지 않는다.
- Claude 데스크톱 앱 안에서 `uv`가 Python을 설치하면 실패한다. 앱이 `AppData` 쓰기를 앱 전용 폴더로 돌리기 때문이다. `UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.local\share\uv\python`을 지정한다. 일반 터미널의 `claude` CLI에서는 이 문제가 없었다.
- Ollama 모델: `qwen3.5:9b-q8_0`(약 74~80 tok/s), `gemma4:12b-it-q4_K_M`(약 132~165 tok/s), `bge-m3:latest`(1024차원). 모델을 올리면 VRAM 여유가 약 4GB다.
- Gemma 콜드 로드가 `CUDA error: shared object initialization failed`로 한 번 실패한 적이 있다. 재현되지 않았다. Ollama 호출은 한 번 재시도한다.
- CLI 세션 기록: `%USERPROFILE%\.claude\projects\<폴더 경로>\*.jsonl`. 사용량과 지시 횟수를 여기서 뽑는다.

## 에이전트 사용 교훈

1. **공유 값은 병렬 작업 전에 고정한다.** 법령명 표기를 각 지시문에 따로 적었다가 어긋났다. 이번 라운드는 의존성, 설정, 계약을 먼저 커밋했다.
2. **제외 조건도 적는다.** 형식 검사를 통과해도 쓸 수 없는 결과가 나왔다. 예: 근거가 수집 범위 밖인 평가 질문
3. **삭제와 취소는 대상을 이름으로 지시한다.** "방어 코드는 제거해"를 넓게 해석해 필요한 검사까지 지워졌다.
4. **위험한 값은 지시하는 쪽이 먼저 확인한다.** 지시문에 `http://`를 적었더니 그대로 구현됐다.
5. **작성자와 검토자를 나눈다.** 감사 스킬과 다른 모델이 작성자 검토에서 놓친 문제를 찾았다. 시행 전 조문, 원문에 없는 "일요일 제외" 등이다.
6. **보고가 아니라 결과로 확인한다.** 데이터 대조와 가짜 응답 시험으로 빠진 검사를 찾았다.
7. **검토 지적은 선별한다.** 전부 반영하면 범위가 끝없이 커진다. 반영하지 않을 기준을 규칙으로 남긴다.
8. **긴 세션은 문서로 넘긴다.** 이 문서가 그 예다.

## 남은 일

**1단계에서 할 일**
- [ ] 세 브랜치 검증과 병합, 기준선
- [ ] `docs/agent-log.md`: 세션별 작업, 병렬 여부, 사용량, 사람이 수정을 지시한 횟수
- [ ] 기준선이 생긴 뒤 `/pstack:create-verification-skill`로 검증 스킬 만들기
- [ ] `main` 푸시

**기준선 이후 개선 후보.** 점수로 효과를 확인한다.
- refs를 따라 연결 조문 함께 가져오기
- 5인 미만 질문에 제11조, 시행령 제7조, 별표 1을 항상 붙이는 공통 규칙
- 키워드 검색 혼합(하이브리드)
- `lsDelegated` API를 `thdCmp`와 비교

**2단계**
- 판례(`target=prec`)나 법령 해석례로 `해석필요` 문항의 근거 보강
- 채팅 UI와 잡담 판단, 질문 재작성

**정리**
- 병합이 끝난 브랜치(`docs/law-api`, `prep/round2`, `eval/answer-key-review`, `feat/collect`, `feat/eval-questions`)와 worktree(`lawbot-collect`, `lawbot-eval`) 삭제
