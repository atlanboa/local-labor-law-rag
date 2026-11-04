# lawbot

근로기준법 중심 노동법 질문에 근거 조문과 함께 답하는 로컬 RAG 상담봇. 법률 자문이 아니다.

## 설정

Ollama와 uv가 필요하다. 인증키는 `.env`에만 넣는다.

```bash
cp .env.example .env
```

## 수집

`.env`에 `LAW_API_OC`를 넣고 실행한다. 응답 원본과 `manifest.json`이 `data/raw/`에 저장된다.

```bash
uv run python -m lawbot.collect
```

법령 본문은 오늘 시행 중인 판을 `target=eflaw`로 받는다. 근로기준법 시행령은 `thdCmp`를 받지 않는다. 시행 전 조문은 `manifest.json`의 `article_effective_dates`에 법령별로 남는다.

테스트는 네트워크 없이 돈다.

```bash
uv run pytest
```

## 실행

```bash
uv run index
```

```bash
uv run ask "5인 미만 사업장도 연차가 있나요?"
```

```bash
uv run eval
```

`index`는 `data/raw`에서 청크를 만들어 Chroma에 저장하고, `ask`는 질문 하나에 답하고, `eval`은 `eval/questions.jsonl`로 점수를 낸다.

## 구조

| 파일 | 역할 |
| --- | --- |
| `src/lawbot/models.py` | `Chunk`, `Answer` 형식 |
| `src/lawbot/config.py` | 경로, 모델 이름, 검색 개수 등 공유 설정 |
| `src/lawbot/collect.py` | 법령 API 수집 |
| `src/lawbot/index.py` | 청킹, 임베딩, Chroma 저장 |
| `src/lawbot/search.py` | `search(question, k) -> list[Chunk]` |
| `src/lawbot/answer.py` | `answer(question, chunks) -> Answer` |
| `src/lawbot/cli.py` | `ask` 명령 |
| `src/lawbot/evaluate.py` | `eval` 명령 |
| `data/raw/` | API 응답 원본. 커밋한다 |
| `data/chroma/` | `index`가 만드는 벡터 DB. 커밋하지 않는다 |
| `eval/` | 평가 질문, 기준선 `baseline.json`. 실행별 결과 `results/`는 커밋하지 않는다 |

채팅 모델은 `LAWBOT_CHAT_MODEL` 환경 변수로 바꾼다. 기본값은 `gemma4:12b-it-q4_K_M`이다.
