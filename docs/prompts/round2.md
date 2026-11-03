# 2라운드 지시문

청킹·검색, 답변·CLI, 평가 스크립트를 동시에 개발하는 지시문이다. worktree마다 `claude`를 실행하고 해당 지시문을 붙여넣는다. 검증 방법은 [progress.md](../progress.md)의 "병합 전 검증"에 있다.

## 창 1: 청킹, 임베딩, 검색

```bash
cd <작업 폴더>\lawbot-index
```

```text
/pstack:poteto-mode
data/raw의 법령 원문으로 청크를 만들고 Chroma에 저장하는 index와 search를 구현해줘. 먼저 CLAUDE.md, docs/law-api.md, eval/README.md를 읽어.

수정할 파일: src/lawbot/index.py, src/lawbot/search.py, tests/test_index.py, tests/test_search.py.
고치지 말 파일: pyproject.toml, uv.lock, src/lawbot/models.py, src/lawbot/config.py. 바꿔야 하면 멈추고 이유를 보고해.

청킹 규칙:
1. 조문마다 청크 1개. 조문여부가 "전문"인 행은 뺀다. 항, 호, 목 내용은 순서대로 본문에 합친다.
2. Chunk.id는 "법령명 제N조" 또는 "법령명 제N조의M". 법령명은 기본정보/법령명_한글 그대로 쓴다.
3. Chunk.text는 "법령명 제N조(제목) 본문".
4. 별표는 별표마다 청크 1개. id는 "법령명 별표 N", text는 "법령명 별표 N 별표제목" 뒤에 별표내용.
5. refs: 각 법률의 thdCmp knd1과 knd2를 합쳐 법률 조문과 시행령 조문을 양방향으로 잇는다. 코퍼스에 없는 시행규칙 등으로 가는 연결은 버리고 개수를 센다. 조문 글에 같은 법령의 "별표 N"이 나오면 그 별표도 refs에 넣는다.
6. pending_effective_dates: manifest.json의 article_effective_dates를 조문 단위로 넣는다. "제110조제1호"는 제110조에 속한다.
7. effective_date는 그 법령의 기본정보/시행일자, collected_at은 manifest의 collected_at.

index 명령: 청크를 data/chunks/chunks.jsonl로 저장하고, config.COLLECTION을 지운 뒤 새로 만들어 config.EMBED_MODEL 임베딩으로 저장해. 코사인 거리를 쓴다. 다시 실행해도 같은 결과가 나와야 해.
search(question, k): 질문을 같은 모델로 임베딩해 가까운 k개를 돌려줘. refs를 따라 확장하지는 마. 기준선은 단순 검색으로 낸다.
get_chunks(ids): 저장된 청크를 id 순서대로 돌려주고 없는 id는 건너뛴다.

테스트는 네트워크와 Ollama 없이 돌게 해. 청킹 테스트는 data/raw의 실제 파일을 써도 된다.

완료 보고에 포함해:
- 바뀐 파일과 핵심 코드 위치(파일:줄)
- 법령별 청크 수, refs 수, 버린 연결 수
- 근로기준법 제11조, 시행령 제7조, 시행령 별표 1 청크의 refs
- 실제 index 실행 시간과 저장 개수
- "5인 미만 사업장도 연차가 있나요?", "잘렸는데 미리 말 안 해줬어요", "퇴직금은 언제까지 받아야 하나요?"의 검색 상위 5개 id와 거리
- 테스트 결과

feat/index 브랜치에 커밋까지만 하고 push와 병합은 하지 마.
```

## 창 2: 답변 생성과 CLI

```bash
cd <작업 폴더>\lawbot-answer
```

```text
질문과 검색된 청크로 답변을 만드는 answer와 ask 명령을 구현해줘. 먼저 CLAUDE.md와 eval/README.md를 읽어.

수정할 파일: src/lawbot/answer.py, src/lawbot/cli.py, tests/test_answer.py, tests/test_cli.py.
고치지 말 파일: pyproject.toml, uv.lock, src/lawbot/models.py, src/lawbot/config.py, src/lawbot/search.py. 바꿔야 하면 멈추고 이유를 보고해.

answer(question, chunks) -> Answer:
1. 청크를 [1], [2]처럼 번호를 붙여 프롬프트에 넣고 Ollama /api/chat으로 config.CHAT_MODEL을 호출해. options는 temperature 0, num_ctx는 config.NUM_CTX. think는 false.
2. 규칙: 주어진 조문만 근거로 답한다. 근거로 쓴 조문은 [번호]로 표시한다. 조문에 없는 내용은 지어내지 않는다. 조문만으로 확정할 수 없으면 조문이 말하는 데까지만 답하고 그렇다고 밝힌다. 관련 조문이 없으면 없다고 말한다.
3. 모델이 쓴 [번호]를 청크 id로 바꿔 Answer.cited_ids에 넣어. 범위 밖 번호는 버린다.
4. Answer.text = 모델 답변 + 출처 목록(청크 id와 effective_date 기준일) + 인용한 청크에 pending_effective_dates가 있으면 "YYYY-MM-DD 시행 예정 개정이 있습니다" + config.DISCLAIMER. 이 부분은 코드가 붙여서 빠지지 않게 해.
5. chunks가 비어 있으면 LLM을 부르지 말고 관련 조문을 찾지 못했다는 답과 안내 문구를 돌려줘.
6. 프롬프트가 num_ctx를 넘으면 잘리니, 응답의 prompt_eval_count가 num_ctx에 가까우면 경고를 stderr에 출력해.
7. Ollama 호출이 실패하면 한 번 재시도한다. 모델 로드 중 CUDA 오류가 난 적이 있어.

ask 명령: uv run ask "질문"으로 search(question, config.TOP_K) 다음 answer를 호출해 출력해. search는 아직 다른 브랜치에서 개발 중이라 지금은 NotImplementedError를 낸다. ask에는 개발용으로 --chunks 옵션을 두어, 청크 id 목록을 받으면 data/raw에서 직접 청크를 만들어 쓰게 해.

테스트는 Ollama 없이 httpx.MockTransport로 돌게 해.

완료 보고에 포함해:
- 바뀐 파일과 핵심 코드 위치(파일:줄)
- 실제 Ollama로 실행한 답변 3개 전문: q001(근로기준법 제26조), q006(근로기준법 제11조, 시행령 제7조, 시행령 별표 1, 근로기준법 제26조), q030(근로기준법 제60조, 제61조, 제36조). 질문은 eval/questions.jsonl에 있다
- 각 답변의 소요 시간과 prompt_eval_count
- 테스트 결과

feat/answer 브랜치에 커밋까지만 하고 push와 병합은 하지 마.
```

## 창 3: 평가 스크립트

```bash
cd <작업 폴더>\lawbot-evaluate
```

```text
eval/questions.jsonl로 검색 점수와 답변 점수를 내는 eval 명령을 구현해줘. 먼저 CLAUDE.md와 eval/README.md를 읽어. Claude API 코드는 claude-api 스킬을 읽고 공식 anthropic SDK로 작성해.

수정할 파일: src/lawbot/evaluate.py, tests/test_evaluate.py.
고치지 말 파일: pyproject.toml, uv.lock, src/lawbot/models.py, src/lawbot/config.py, src/lawbot/search.py, src/lawbot/answer.py. 바꿔야 하면 멈추고 이유를 보고해.

명령: uv run eval [--only search] [--contexts gold] [--limit N] [--save-baseline]
1. 검색 점수: search(question, config.TOP_K)의 id에 required가 모두 있으면 1, 아니면 0. 근거없음 문항은 검색 점수에서 뺀다.
2. --only search면 여기서 끝낸다. LLM을 호출하지 않는다.
3. 답변: 기본은 검색 결과로, --contexts gold면 get_chunks(required)로 answer를 호출한다.
4. 답변 점수: config.JUDGE_MODEL로 채점한다. 질문, 유형, key_points, 제공된 청크, 답변을 주고 key_point별 충족 여부와 이유, 제공된 조문에 없는 내용을 지어냈는지, 인용이 내용을 뒷받침하는지를 구조화된 출력으로 받아. 모두 충족하고 지어내지 않았고 인용이 맞으면 1점이야. 근거없음과 해석필요 유형은 eval/README.md의 정답 행동으로 채점해.
5. 채점 결과는 (채점 모델, 채점 기준 버전, 질문, 답변, 청크 id)의 해시로 eval/results/에 캐시해서 같은 답변은 다시 채점하지 마.
6. 실행마다 eval/results/에 문항별 결과를 JSON으로 저장하고, 전체와 유형별 점수를 출력해. eval/baseline.json이 있으면 기준선 대비 증감과 새로 맞힌 문항, 새로 틀린 문항을 출력해. --save-baseline이면 이번 결과를 eval/baseline.json에 저장해.
7. Ollama 호출은 GPU 하나를 쓰니 문항을 순서대로 처리해. 채팅 모델 이름과 Ollama 응답 시간도 결과에 남겨.

search와 answer는 다른 브랜치에서 개발 중이라 지금은 NotImplementedError를 낸다. 테스트는 가짜 search, answer, 채점기로 네트워크 없이 돌게 해. 실제 Claude API 호출은 직접 쓴 답변 하나로 한 번만 해서 채점이 동작하는지 확인해.

완료 보고에 포함해:
- 바뀐 파일과 핵심 코드 위치(파일:줄)
- 사용법과 결과 파일 형식
- 가짜 구성 요소로 돌린 실행 출력
- 실제 채점 호출 1회의 결과와 토큰 사용량
- 테스트 결과

키를 출력하지 마. feat/evaluate 브랜치에 커밋까지만 하고 push와 병합은 하지 마.
```
