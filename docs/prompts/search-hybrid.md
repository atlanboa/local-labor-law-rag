# 검색 개선 A: 하이브리드 검색

검색 개선 1단계의 작업자 A다. B([search-expand.md](search-expand.md))와 동시에 진행한다. A는 후보를 찾는 `retrieve.py`만, B는 연결 조문을 붙이는 `expand.py`만 고친다. 계약과 상한 5를 정한 근거는 [progress.md](../progress.md)의 "검색 개선"에 있다.

모델은 기본(Opus)으로 한다. 결과 확인은 보고와 따로 메인 세션에서 한다.

## 준비

`lawbot` 폴더에서 실행한다. `.env`와 채점 캐시는 git에 없으므로 복사한다.

```bash
cd <작업 폴더>\lawbot
git worktree add ../lawbot-hybrid -b feat/search-hybrid
mkdir ..\lawbot-hybrid\eval\results
copy .env ..\lawbot-hybrid\.env
xcopy /E /I eval\results\judge-cache ..\lawbot-hybrid\eval\results\judge-cache
cd ..\lawbot-hybrid
claude
```

## 지시문

```text
lawbot의 검색 후보 단계에 키워드 검색을 섞어줘. 먼저 CLAUDE.md, docs/progress.md("검색 개선" 항목), eval/README.md, .claude/skills/verify/SKILL.md, src/lawbot/search.py, retrieve.py, config.py, models.py를 읽어.

지금 폴더(../lawbot-hybrid, 브랜치 feat/search-hybrid)에서만 작업해. 커밋까지만 하고 push와 병합은 하지 마.
수정할 파일: src/lawbot/retrieve.py, 키워드 검색용 새 파일 src/lawbot/bm25.py, 새 파일 tests/test_retrieve.py. tests/test_search.py는 test_search_ranks_by_cosine_not_euclidean_distance 하나만, 깨질 때만 고친다.
고치지 말 파일: src/lawbot/search.py, expand.py, config.py, index.py, answer.py, models.py, cli.py, evaluate.py, eval/, scripts/, pyproject.toml, uv.lock. 바꿔야 하면 멈추고 이유를 보고해. 다른 작업자가 expand.py와 config.py를 고치고 있다.

배경:
- 지금 retrieve()는 bge-m3 의미 검색만 한다. 검색 점수는 0.639(23/36)다.
- 후보 수 k를 15까지 늘려도 q014, q019, q020, q030, q034, q037, q039, q041의 required 조문은 찾지 못한다. 자리 수가 아니라 순위 문제다. k=5에서는 q006, q007, q021, q022, q031도 놓친다.
- 후보를 늘리면 답변이 나빠졌다(k=8에서 답변 0.585 -> 0.488). 그래서 상한은 5로 고정이다. 맞는 조문을 상위 5개 안으로 올리는 게 목표다.

할 일:
1. 위 13문항에서 required 조문이 왜 의미 검색에서 밀리는지 먼저 본다. 질문과 조문 사이에 겹치는 낱말이 있는지, 대신 올라온 조문이 무엇인지. eval/baseline.json의 retrieved_ids와 data/chunks/chunks.jsonl을 쓴다. 키워드 검색으로 살릴 수 있는 문항과 없는 문항을 나눈다.
2. bm25.py에 BM25 키워드 검색을 만든다. 말뭉치는 Chroma 컬렉션의 청크다(index.open_collection()). 394개라 질문 때 읽어도 되고, 한 번 만든 뒤 재사용해도 된다.
   - 한국어 토큰은 우선 새 라이브러리 없이 만든다. 예: 공백으로 나눈 낱말과 글자 2-gram. 형태소 분석기 같은 라이브러리가 필요하다고 판단되면 넣지 말고 이유와 기대 효과를 보고해. pyproject.toml은 공유 파일이다.
3. retrieve(question, k)에서 의미 검색 순위와 키워드 검색 순위를 합친다. 방법은 RRF(Reciprocal Rank Fusion)부터 시도한다. 반환은 그대로 관련도 높은 순서의 Chunk k개다.
4. 조정값(RRF 상수, 각 검색에서 가져올 후보 수, 토큰 방식)은 적게 둔다. 평가 문항은 36개뿐이라 문항에 맞춘 조정은 과적합이다. 문항 id나 질문 문구를 코드에 넣지 마. 조정값을 바꿔 본 결과를 표로 남겨.
5. tests/test_retrieve.py: 토큰화, BM25 순위, 순위 합치기를 Ollama 없이 시험한다. 기존 테스트도 모두 통과해야 한다.
6. 반복 측정은 uv run eval --only search로 한다. 검색만이라 API를 부르지 않는다.
7. 마지막에 기본값(TOP_K 5, MAX_CHUNKS 5)으로 /verify를 한 번 돌린다. 검색은 기준선보다 높아야 하고 답변은 0.585 이상이어야 한다.

지킬 것:
- --save-baseline은 쓰지 않는다.
- 다른 worktree에서 B도 평가를 돌릴 수 있다. 전체 /verify는 마지막 한 번만 돌린다. 겹치면 시간 수치는 믿지 마.
- 답변 점수에서 새로 틀린 문항은 채점 사유까지 읽어. 채점기는 사유에 "충족"이라 쓰고 met을 false로 내는 경우가 있다. 그런 문항은 따로 표시하고, 채점기는 고치지 마.
- 인증키를 출력하거나 파일에 쓰지 않는다.
- Claude 데스크톱 앱 안에서는 UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.local\share\uv\python이 필요하다.

완료 보고에 포함해:
- 1번 분석: 13문항 각각 키워드로 살릴 수 있는지와 이유 한 줄
- 바뀐 파일과 핵심 위치(파일:줄)
- 조정값별 검색 점수 표와 고른 값
- 최종 /verify 출력 요약: 검색과 답변 점수, 새로 맞힌 문항과 새로 틀린 문항, 유형별 점수, API 호출 수
- 새로 틀린 답변 문항 중 채점기 모순으로 보이는 것
- 키워드 검색으로도 못 살린 문항과, 다음에 시도할 만한 방법
```

## 검증할 것

보고를 받으면 메인 세션에서 확인한다.

- `git diff main...feat/search-hybrid`로 범위 밖 변경이 없는지 본다.
- 코드에 문항 id나 질문 문구가 없는지 본다.
- 기본값으로 직접 `/verify`를 돌린다. B와 겹치지 않게 돌린다.
- 새로 틀린 답변 문항의 채점 사유를 읽는다.
