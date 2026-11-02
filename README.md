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

법률 본문은 오늘 시행 중인 판을 `target=eflaw`로 받는다. 근로기준법 시행령은 `target=law` 본문만 받고 `thdCmp`는 받지 않는다. 시행 전 조문은 `manifest.json`의 `article_effective_dates`에 법령별로 남는다.

테스트는 네트워크 없이 돈다.

```bash
uv run pytest
```

## 구조

- `src/lawbot/models.py`: 청크와 답변 형식
- `src/lawbot/search.py`: 질문으로 청크 검색
- `src/lawbot/answer.py`: 질문과 청크로 답변 생성
- `data/raw/`: API 응답 원본. 커밋한다. 청크와 Chroma 데이터는 여기서 다시 만든다.
