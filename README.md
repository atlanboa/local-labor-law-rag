# lawbot

근로기준법 중심 노동법 질문에 근거 조문과 함께 답하는 로컬 RAG 상담봇. 법률 자문이 아니다.

## 설정

Ollama와 uv가 필요하다. 인증키는 `.env`에만 넣는다.

```bash
cp .env.example .env
```

## 구조

- `src/lawbot/models.py`: 청크와 답변 형식
- `src/lawbot/search.py`: 질문으로 청크 검색
- `src/lawbot/answer.py`: 질문과 청크로 답변 생성
- `data/raw/`: API 응답 원본. 커밋한다. 청크와 Chroma 데이터는 여기서 다시 만든다.
