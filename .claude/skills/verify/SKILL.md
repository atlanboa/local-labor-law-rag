---
name: verify
description: lawbot 변경이 기준선(eval/baseline.json)보다 나빠지지 않았는지 확인한다. Ollama 준비, pytest, index, 검색 평가, 답변 평가를 차례로 돌리고 PASS/FAIL을 낸다. 2단계 작업자가 자기 worktree(../lawbot-<작업명>)에서 병합 전에 쓴다. 평가는 GPU 하나를 쓰므로 컴퓨터 전체에서 한 번에 하나만 돌린다.
---

# lawbot 검증

실행한 폴더의 `data/chroma`, `data/chunks`, `eval/results`, `.env`만 쓴다. 다른 worktree의 파일은 읽지 않는다. `config.ROOT`가 이 폴더가 아니면 0단계에서 멈춘다.

## 지킬 것

- **한 번에 하나만.** 검증은 GPU 하나(Ollama)를 쓴다. 다른 worktree에서 `verify`, `eval`, `index`, `ask`가 돌고 있으면 끝날 때까지 기다린다. 동시에 돌리면 시간이 늘고 VRAM이 모자라 콜드 로드 오류가 난다.
- **`--save-baseline`을 쓰지 않는다.** 스크립트도 쓰지 않는다. 기준선 갱신은 사람이 정한다.
- **인증키를 출력하거나 파일에 쓰지 않는다.** 스크립트는 `.env`에 `ANTHROPIC_API_KEY`가 있는지만 본다. `.env`를 `cat`하지 않는다.
- **Claude 데스크톱 앱 안에서는** `uv`가 Python 설치에 실패한다. 앱이 `AppData` 쓰기를 다른 폴더로 돌리기 때문이다. `UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.local\share\uv\python`을 지정하고 실행한다. 일반 터미널의 `claude` CLI에서는 필요 없지만 지정해도 된다.

## 실행

worktree 폴더에서 실행한다. 시간 제한은 15분 이상으로 준다. 채점 캐시가 맞으면 전체 실행은 약 2분이다. 캐시가 비면 채점 시간이 더 든다.

Bash:

```bash
UV_PYTHON_INSTALL_DIR="$USERPROFILE\.local\share\uv\python" uv run python scripts/verify.py
```

PowerShell:

```powershell
$env:UV_PYTHON_INSTALL_DIR = "$env:USERPROFILE\.local\share\uv\python"; uv run python scripts/verify.py
```

채팅 모델을 바꿔 시험하면 `LAWBOT_CHAT_MODEL`을 같이 준다. 모델 이름은 스크립트가 `config`에서 읽는다.

종료 코드: `0` PASS, `1` FAIL, `2` 판정 전에 멈춤.

## 단계

`scripts/verify.py`가 순서대로 돌린다. 한 단계가 실패하면 그 자리에서 멈추고 이유를 적는다.

| 단계 | 하는 일 | 멈추는 조건 |
| --- | --- | --- |
| 0 폴더 | `config.ROOT`와 `git rev-parse --show-toplevel` 비교 | 다르면. 이 폴더에서 `uv sync` 후 다시 실행 |
| 1 준비 | `config.OLLAMA_URL/api/tags` 응답, `config.EMBED_MODEL`과 `config.CHAT_MODEL` 설치 여부 | 응답 없음, 없는 모델 이름 |
| 2 pytest | `uv run pytest -q` | 실패 |
| 3 index | `uv run index`. 출력의 저장 개수, `data/chunks/chunks.jsonl` 줄 수, Chroma 컬렉션 개수 비교 | 셋이 다르면 |
| 4 검색 | `uv run eval --only search`, 기준선의 검색 점수와 비교 | eval 실패 |
| 5 답변 | `.env`에 `ANTHROPIC_API_KEY`가 있을 때만 `uv run eval`. 없으면 `[SKIP]`으로 적는다 | eval 실패 |
| 6 판정 | 검색과 답변 점수가 모두 기준선 이상이면 PASS, 하나라도 낮으면 FAIL | |

- 채점은 `eval/results/judge-cache`를 쓴다. 답변이 기준선 때와 같으면 Claude API를 부르지 않는다(호출 0회). 새 worktree는 캐시가 비어 있어 41회 부른다. 1회 전체 채점은 Haiku 입력 약 22만, 출력 약 4만 토큰이다.
- 답변 평가를 건너뛰면 판정은 `PASS (검색만)`이다. 보고에 답변 평가를 하지 않았다고 적는다.
- 점수가 같아도 `새로 틀림`에 id가 있으면 보고에 적는다. 41문항에서 몇 문항 차이는 우연과 구분되지 않는다.
- `주의: chat_model가 기준선과 다르다`가 나오면 답변 점수 비교는 모델 차이를 포함한다.
- 4, 5단계가 `exit status 0xc0000409`나 `CUDA error`로 실패하면 Ollama 콜드 로드 오류다. 한 번 다시 실행한다.

## 출력 예

```text
verify 2026-11-04 20:42:56
[ OK ] 0 폴더 (0초): 폴더 <작업 폴더>\lawbot
[ OK ] 1 준비 (0초): Ollama http://127.0.0.1:11434, 임베딩 bge-m3:latest, 채팅 gemma4:12b-it-q4_K_M
[ OK ] 2 pytest (6초): 58 passed in 5.33s
[ OK ] 3 index (9초): 저장 394, chunks.jsonl 394줄, Chroma 394개
기준선: ...\lawbot\eval\baseline.json
[ OK ] 4 eval --only search (5초): ...\lawbot\eval\results\run-20261104-204314-769109.json
search: 0.639 (23/36) -> 0.639 (23/36) OK
  단일: 0.882 (15/17) -> 0.882 (15/17) +0.000
  복합: 0.471 (8/17) -> 0.471 (8/17) +0.000
  해석필요: 0.000 (0/2) -> 0.000 (0/2) +0.000
  새로 틀림: -
  새로 맞음: -
[ OK ] 5 eval (84초): ...\lawbot\eval\results\run-20261104-204319-367830.json
answer: 0.537 (22/41) -> 0.537 (22/41) OK
  근거없음: 1.000 (5/5) -> 1.000 (5/5) +0.000
  단일: 0.647 (11/17) -> 0.647 (11/17) +0.000
  복합: 0.353 (6/17) -> 0.353 (6/17) +0.000
  해석필요: 0.000 (0/2) -> 0.000 (0/2) +0.000
  새로 틀림: -
  새로 맞음: -
  Claude API 호출 0회, 캐시 41회, 입력 0 출력 0 토큰, 답변 79초
판정: PASS
걸린 시간: 104초
결과: ...\lawbot\eval\results\run-20261104-204314-769109.json
결과: ...\lawbot\eval\results\run-20261104-204319-367830.json
보고: ...\lawbot\eval\results\verify-20261104-204440.txt
```

## 보고

사용자에게는 짧게 적는다: 단계별 통과 여부, 기준선 대비 점수(유형별 변화 포함), 새로 틀린 문항 id, 걸린 시간, Claude API 호출 수, 결과 파일 경로. 출력의 마지막 줄 `보고:` 파일에 같은 내용이 남는다. `eval/results/`는 커밋하지 않는다.

## 다른 기준선과 비교

`--baseline PATH`로 다른 파일과 비교한다. `eval/baseline.json`은 고치지 않는다. 스크립트 자체를 시험할 때 쓴다. 예: 검색 점수를 높인 사본을 scratch 폴더에 만들고 FAIL이 나오는지 본다.

## 정리

스크립트는 서버를 띄우지 않는다. Ollama는 사용자가 띄운 것을 쓰고 끄지 않는다. 실행 후 `git status`에 변경이 없어야 한다. `data/chunks`, `data/chroma`, `eval/results`는 `.gitignore`에 있다.
