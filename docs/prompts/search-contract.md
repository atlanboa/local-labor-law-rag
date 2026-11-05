# 검색 계약 지시문 (검색 개선 0단계)

검색 개선의 0단계다. 두 작업자(A 하이브리드, B 연결 붙이기)가 같은 파일을 고치지 않도록 검색을 두 단계로 나누는 계약을 고정한다. 그리고 공정한 비교 기준이 될 대조 측정을 한다.

새 CLI 세션 하나에서 진행한다. 결과 확인은 [agent-log.md](../agent-log.md)의 교훈대로 보고와 따로 한다.

## 준비

`lawbot` 폴더에서 worktree를 만들고, 그 폴더에서 세션을 시작한다. `.env`와 채점 캐시는 git에 없으므로 복사한다. 캐시를 복사하면 답변이 그대로인 문항은 API를 다시 부르지 않는다.

```bash
cd <작업 폴더>\lawbot
git worktree add ../lawbot-contract -b feat/search-contract
mkdir ..\lawbot-contract\eval\results
copy .env ..\lawbot-contract\.env
xcopy /E /I eval\results\judge-cache ..\lawbot-contract\eval\results\judge-cache
cd ..\lawbot-contract
claude
```

## 지시문

```text
lawbot의 검색을 두 단계로 나누고, 대조 측정을 해줘. 먼저 CLAUDE.md, docs/progress.md, eval/README.md, .claude/skills/verify/SKILL.md, src/lawbot/search.py, src/lawbot/config.py를 읽어.

지금 폴더(../lawbot-contract, 브랜치 feat/search-contract)에서만 작업해. 커밋까지만 하고 push와 병합은 하지 마.
수정할 파일: src/lawbot/search.py, src/lawbot/config.py, src/lawbot/evaluate.py(설정 기록 한 줄), 새 파일 src/lawbot/retrieve.py와 src/lawbot/expand.py, tests/test_search.py, 새 파일 eval/control-k8.json.
고치지 말 파일: src/lawbot/index.py, answer.py, models.py, cli.py, eval/questions.jsonl, eval/baseline.json, scripts/verify.py, pyproject.toml, uv.lock. 바꿔야 하면 멈추고 이유를 보고해.

배경: 다음 단계에서 작업자 두 명이 병렬로 검색을 고친다. A는 후보를 찾는 방법(의미 검색에 키워드 검색 섞기)을, B는 찾은 조문에 연결 조문을 붙이는 방법(refs 따라가기, 5인 미만 질문에 제11조, 시행령 제7조, 별표 1 붙이기)을 고친다. 둘이 같은 파일을 고치지 않게 단계를 파일로 나눈다. 그리고 조문을 많이 넘기면 검색 점수는 쉽게 오르므로, 답변에 넘기는 청크 수에 상한을 두고 같은 상한에서 비교한다.

할 일, 순서대로:
1. config.py에 두 값을 둔다. 둘 다 환경 변수로 바꿀 수 있게 한다.
   - TOP_K: 후보 수. LAWBOT_TOP_K, 기본 5.
   - MAX_CHUNKS: 답변에 넘기는 청크 수 상한. LAWBOT_MAX_CHUNKS, 기본 5.
   기본값에서는 지금과 결과가 같아야 한다.
2. 새 파일 retrieve.py에 retrieve(question: str, k: int) -> list[Chunk]를 둔다. 지금 search()의 의미 검색을 그대로 옮긴다. 관련도 높은 순서로 돌려준다.
3. 새 파일 expand.py에 expand(question: str, found: list[Chunk]) -> list[Chunk]를 둔다. found에 붙일 청크를 붙일 순서대로 돌려준다. 지금은 빈 리스트를 돌려준다.
4. search.py의 search(question: str, k: int = config.TOP_K) -> list[Chunk]는 retrieve(question, k)와 expand(question, found)를 부르고, found 뒤에 붙일 청크를 이어 붙인다. 중복 id는 처음 것만 남기고, config.MAX_CHUNKS개에서 자른다. 호출부(cli.py, evaluate.py)의 search(question, k) 사용법은 바꾸지 않는다. get_chunks는 그대로 둔다.
5. evaluate.py가 결과 파일에 top_k와 함께 max_chunks를 기록하게 한다. verify의 설정 비교가 이 값을 보게 된다.
6. tests/test_search.py에 search의 계약을 시험한다. retrieve와 expand를 가짜로 바꿔서: 붙인 청크가 뒤에 오는지, 중복 id가 빠지는지, MAX_CHUNKS에서 잘리는지. Ollama와 Chroma 없이 돌아야 한다.
7. 기본값으로 /verify를 실행한다. PASS이고 검색과 답변 점수가 기준선과 같아야 한다(검색 0.639, 답변 0.585).
8. 대조 측정: LAWBOT_TOP_K=8, LAWBOT_MAX_CHUNKS=8로 uv run eval을 실행한다. 지금 방식에서 후보만 8개로 늘린 결과다. 결과 파일을 eval/control-k8.json으로 복사해 커밋한다. 다음 단계 작업자들은 상한 8에서 이 파일과 비교한다.

지킬 것:
- --save-baseline은 쓰지 않는다. eval/baseline.json은 그대로 둔다.
- 평가는 GPU 하나를 쓰므로 동시에 하나만 돌린다.
- 인증키를 출력하거나 파일에 쓰지 않는다.
- Claude 데스크톱 앱 안에서는 UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.local\share\uv\python이 필요하다.

완료 보고에 포함해:
- 바뀐 파일과 핵심 위치(파일:줄)
- 7번 /verify 출력 요약과 API 호출 수
- 8번 결과: 검색과 답변 점수, 기준선(k=5) 대비 새로 맞힌 문항과 새로 틀린 문항, 유형별 점수
- 8번에서 늘어난 검색 점수가 검색 실패 13문항(q006, q007, q014, q019, q020, q021, q022, q030, q031, q034, q037, q039, q041) 중 어디서 나왔는지
```

## 검증할 것

보고를 받으면 메인 세션에서 확인한다.

- `git diff main...feat/search-contract`로 범위 밖 변경이 없는지 본다.
- 기본값에서 결과가 기준선과 같은지 직접 `/verify`를 돌린다.
- `eval/control-k8.json`의 `top_k`, `max_chunks`가 8인지 본다.
