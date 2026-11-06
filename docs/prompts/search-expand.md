# 검색 개선 B: 연결 조문 붙이기

검색 개선 1단계의 작업자 B다. A([search-hybrid.md](search-hybrid.md))와 동시에 진행한다. B는 연결 조문을 붙이는 `expand.py`만, A는 후보를 찾는 `retrieve.py`만 고친다. 계약과 상한 5를 정한 근거는 [progress.md](../progress.md)의 "검색 개선"에 있다.

**모델은 Sonnet으로 한다.** 계약과 범위가 정해진 작업을 가벼운 모델이 해낼 수 있는지 보는 실험이다. 같은 방식으로 검증해 A(Opus)와 수정 지시 횟수, 범위 밖 변경, 결과를 비교한다. 결과 확인은 보고와 따로 메인 세션에서 한다.

## 준비

`lawbot` 폴더에서 실행한다. `.env`와 채점 캐시는 git에 없으므로 복사한다.

```bash
cd <작업 폴더>\lawbot
git worktree add ../lawbot-expand -b feat/search-expand
mkdir ..\lawbot-expand\eval\results
copy .env ..\lawbot-expand\.env
xcopy /E /I eval\results\judge-cache ..\lawbot-expand\eval\results\judge-cache
cd ..\lawbot-expand
claude --model sonnet
```

## 지시문

```text
lawbot의 검색 결과에 연결 조문을 붙이는 단계를 만들어줘. 먼저 CLAUDE.md, docs/progress.md("검색 개선" 항목), eval/README.md, .claude/skills/verify/SKILL.md, src/lawbot/search.py, expand.py, config.py, models.py를 읽어.

지금 폴더(../lawbot-expand, 브랜치 feat/search-expand)에서만 작업해. 커밋까지만 하고 push와 병합은 하지 마.
수정할 파일: src/lawbot/expand.py, src/lawbot/config.py의 TOP_K 기본값 한 곳, 새 파일 tests/test_expand.py. tests/test_search.py는 test_search_returns_whole_chunks_without_following_refs 하나만, 깨질 때만 고친다.
고치지 말 파일: src/lawbot/search.py, retrieve.py, index.py, answer.py, models.py, cli.py, evaluate.py, eval/, scripts/, pyproject.toml, uv.lock. 바꿔야 하면 멈추고 이유를 보고해. 다른 작업자가 retrieve.py를 고치고 있다.

배경:
- search()는 retrieve(question, TOP_K)의 결과 뒤에 expand(question, found)가 돌려준 청크를 붙이고, 중복을 빼고, MAX_CHUNKS(5)에서 자른다. 상한 5는 고정이다. k=8에서 답변이 0.585 -> 0.488로 나빠졌기 때문이다.
- 그래서 TOP_K가 5면 붙인 청크는 모두 잘린다. 붙이려면 TOP_K를 낮춰 자리를 비워야 한다. k별 검색 점수는 3: 18/36, 4: 21/36, 5: 23/36이다. 붙인 청크가 k를 낮춰서 잃는 문항보다 많이 살려야 한다.
- Chunk.refs에 연결 조문 id가 있다. 색인 때 thdCmp 인용(knd=1)과 위임(knd=2) 연결표, 그리고 조문 본문의 별표 언급으로 만들었고, 종류 구분 없이 합쳐져 있다. 수집한 하위법령은 근로기준법 시행령뿐이라 연결은 근로기준법과 그 시행령 사이에만 있다.
- 기준선에서 refs로 살릴 수 있어 보이는 문항: q014(시행령 제17조), q031과 q037(제2조), q020(시행령 제9조. 제55조는 refs로 못 찾음).
- 5인 미만 질문 q006, q022는 제11조, 시행령 제7조, 별표 1이 상위 5개 중 3자리를 차지해 주제 조문(제26조, 제55조)이 밀렸다.

할 일:
1. 기준선(eval/baseline.json)의 검색 실패 문항마다, found의 refs를 따라가면 required를 얻는지 확인한다. 얻는다면 found의 몇 번째 청크에서 오는지도 본다. 몇 번째 청크까지 따라갈지 정하는 근거다.
2. expand.py에 refs 따라가기를 만든다. 붙일 청크를 붙일 순서대로 돌려준다. 청크 내용은 index.open_collection()에서 id로 가져온다. search.py의 get_chunks를 모듈 맨 위에서 import하면 순환 import가 된다(search가 expand를 import한다). 함수 안에서 import하거나 컬렉션을 직접 쓴다.
3. 5인 미만 규칙: 질문에 사업장 규모가 4명 이하, 5인 미만으로 나오면 제11조, 시행령 제7조, 별표 1을 붙인다. 표현은 문항 문구가 아니라 일반 패턴으로 잡는다(예: 숫자+명/인, 이하/미만). 이 규칙이 효과를 내려면 세 조문이 found에서 차지하던 자리가 비어야 한다. found와 붙인 청크의 순서를 search.py는 바꾸지 않으므로, 순서를 어떻게 할지 결과를 보고 판단해 보고해. search.py를 바꿔야 한다고 판단되면 멈추고 보고해.
4. 설정을 바꿔 가며 uv run eval --only search로 잰다. 최소한 (TOP_K 3, MAX 5), (TOP_K 4, MAX 5), (TOP_K 5, MAX 6). MAX 6은 상한을 1 늘리는 대안이라 답변 점수까지 봐야 판단할 수 있다.
5. 검색 점수가 가장 좋은 설정 하나와 (TOP_K 5, MAX 6) 중 검색이 기준선보다 높은 것만 전체 /verify를 돌린다. 각각 Haiku를 약 41번 부르므로 이 둘 말고는 전체 평가를 돌리지 마. 설정은 환경 변수(LAWBOT_TOP_K, LAWBOT_MAX_CHUNKS)로 준다.
6. 고른 설정이 TOP_K만 바꾸는 것이면 config.py의 TOP_K 기본값을 그 값으로 바꾼다. MAX_CHUNKS 기본값은 바꾸지 마. MAX 6이 더 낫다면 바꾸지 말고 보고해. 상한은 사람이 정한다.
7. tests/test_expand.py: refs 따라가기, 5인 미만 규칙과 해당하지 않는 질문, 이미 found에 있는 청크를 다시 붙이지 않는지. Ollama 없이 돌아야 한다. 기존 테스트도 모두 통과해야 한다.

지킬 것:
- 문항 id나 질문 문구를 코드에 넣지 마. 평가 문항 36개에 맞춘 조정은 과적합이다.
- --save-baseline은 쓰지 않는다.
- 다른 worktree에서 A도 평가를 돌릴 수 있다. 겹치면 시간 수치는 믿지 마.
- 답변 점수에서 새로 틀린 문항은 채점 사유까지 읽어. 채점기는 사유에 "충족"이라 쓰고 met을 false로 내는 경우가 있다. 그런 문항은 따로 표시하고, 채점기는 고치지 마.
- 인증키를 출력하거나 파일에 쓰지 않는다.
- Claude 데스크톱 앱 안에서는 UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.local\share\uv\python이 필요하다.

완료 보고에 포함해:
- 1번 분석 결과
- 바뀐 파일과 핵심 위치(파일:줄)
- 설정별 검색 점수 표, 새로 맞힌 문항과 새로 틀린 문항
- 전체 /verify 결과(돌린 설정마다): 검색과 답변 점수, 유형별 점수, API 호출 수
- 새로 틀린 답변 문항 중 채점기 모순으로 보이는 것
- 고른 설정과 이유. 상한을 6으로 바꾸자고 판단하면 그 근거
```

## 검증할 것

보고를 받으면 메인 세션에서 확인한다.

- `git diff main...feat/search-expand`로 범위 밖 변경이 없는지 본다. config.py는 `TOP_K` 기본값 한 곳만 바뀌어야 한다.
- 코드에 문항 id나 질문 문구가 없는지 본다.
- 기본값으로 직접 `/verify`를 돌린다. A와 겹치지 않게 돌린다.
- 새로 틀린 답변 문항의 채점 사유를 읽는다.
- A와 비교해 [agent-log.md](../agent-log.md)에 적는다: 사람 입력, 수정 지시, 범위 밖 변경, 출력 토큰, 결과.
