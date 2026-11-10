# lawbot: 노동법 로컬 RAG 상담봇

근로기준법 중심의 노동법 질문에 **근거 조문과 함께** 답하는 챗봇입니다. 법령 원문을 검색해 로컬 생성형 모델(Ollama)에 넣고, 답변의 문장마다 어느 조문에서 왔는지 표시합니다. 모델과 데이터가 모두 내 PC에서 돌고, 외부 API는 법령 수집과 평가 채점에만 씁니다.

> 이 프로젝트의 답변은 법률 자문이 아닙니다. 실제 사안은 노무사나 고용노동부(국번 없이 1350)에 문의하세요.

RAG 챗봇이 어떤 단계를 거쳐 만들어지는지 직접 따라가 보려고 만든 학습용 프로젝트입니다. 데이터 수집부터 평가, 웹 화면까지 한 저장소에 있고, 단계마다 무엇을 왜 결정했는지 [docs/](docs/)에 기록했습니다.

## 무엇을 하나

질문을 하면 아래 순서로 답이 만들어집니다.

```mermaid
flowchart LR
    Q[질문] --> E[질문 임베딩<br/>bge-m3]
    E --> S[벡터 검색<br/>Chroma 상위 5개]
    S --> X[연결 조문 붙이기<br/>시행령, 별표]
    X --> P[프롬프트 구성<br/>번호 붙인 조문 + 질문]
    P --> L[답변 생성<br/>Gemma 4 12B, Ollama]
    L --> C[인용 번호 추출<br/>출처, 시행일, 면책 문구]
```

- **수집.** 국가법령정보 Open API로 법령 5개(근로기준법과 시행령, 최저임금법, 근로자퇴직급여 보장법, 남녀고용평등법)의 현행 본문을 받습니다. 받은 원본은 `data/raw/`에 그대로 커밋되어 있어서, 실행만 할 때는 인증키가 필요 없습니다.
- **청킹과 임베딩.** 조문 하나를 청크 하나로 잘라 394개를 만들고, bge-m3로 임베딩해 Chroma에 저장합니다. 청크마다 법령명, 조 번호, 제목, 시행일, 다른 조문과의 연결(refs)이 붙습니다.
- **검색.** 질문과 가까운 조문 5개를 찾고, 1위 조문이 위임하거나 인용하는 조문을 뒤에 붙여 최대 6개를 넘깁니다.
- **생성.** 모델은 받은 조문만 근거로 답하고, 문장 끝에 `[1]`처럼 조문 번호를 답니다. 조문으로 확정할 수 없으면 확정할 수 없다고 말하게 했습니다.
- **출처 표시.** 답변에서 실제로 인용한 번호만 골라 출처 목록을 만듭니다. 시행 예정 개정이 있는 조문은 따로 알려 줍니다.

웹 화면에서는 답변의 `[n]` 표시를 누르면 해당 조문 원문이 펼쳐집니다.

## 평가

질문 41개와 각 질문의 정답 조문, 모범 답변 요지를 [eval/questions.jsonl](eval/questions.jsonl)에 만들어 두고 두 가지 점수를 냅니다.

| 점수 | 방법 | 현재 기준선 |
| --- | --- | --- |
| 검색 | 정답 조문이 검색 결과 안에 들었는가. 자동 채점 | 0.722 (26/36) |
| 답변 | 핵심 내용을 맞게 말했고 지어낸 내용이 없는가. Claude Haiku가 채점 | 0.707 (29/41) |

질문은 단순 조문 1개, 여러 조문 복합, 근거 없음(수집한 법령에 답이 없는 질문), 해석 필요(조문만으로 답이 정해지지 않는 질문)의 네 유형입니다. 기준선은 [eval/baseline.json](eval/baseline.json)이고, 코드를 바꾸면 같은 평가를 다시 돌려 나빠지지 않았는지 봅니다. 문항 작성 규칙은 [eval/README.md](eval/README.md)에 있습니다.

## 기술 스택

| 계층 | 선택 |
| --- | --- |
| 생성 모델 | `gemma4:12b-it-q4_K_M` (Ollama, temperature 0) |
| 임베딩 | `bge-m3` (Ollama, 1024차원) |
| 벡터 DB | Chroma (파일로 저장, 서버 없음) |
| 백엔드 | Python 3.12, uv, FastAPI |
| 프런트엔드 | React 19, TypeScript, Vite, 일반 CSS |
| 평가 채점 | Claude Haiku (Anthropic API) |
| 데이터 | [국가법령정보 공동활용 Open API](https://open.law.go.kr/LSO/openApi/guideList.do) |

개발한 PC는 RTX 5070 Ti(VRAM 16GB)입니다. Gemma 4 12B Q4는 약 7GB를 쓰고, 평가 41문항의 답변 생성이 약 80초(문항당 약 2초) 걸렸습니다.

## 실행 가이드

### 1. 준비물

- [Ollama](https://ollama.com)
- [uv](https://docs.astral.sh/uv/) (Python 버전과 패키지를 함께 관리합니다)
- [Node.js](https://nodejs.org) 20.19 또는 22.12 이상 (웹 화면을 쓸 때만. Vite 8의 요구 사항입니다)
- 모델이 VRAM 약 7GB를 씁니다. 개발 PC 밖의 환경에서는 속도를 재 보지 않았습니다.

Windows, macOS, Linux에서 아래 명령은 같습니다.

### 2. 받기와 설치

```bash
git clone https://github.com/atlanboa/local-labor-law-rag.git
```

```bash
cd local-labor-law-rag
```

```bash
uv sync
```

### 3. 모델 받기

```bash
ollama pull bge-m3
```

```bash
ollama pull gemma4:12b-it-q4_K_M
```

다른 모델을 쓰려면 `LAWBOT_CHAT_MODEL` 환경 변수에 Ollama 모델 이름을 넣습니다.

### 4. 색인 만들기

`data/raw/`의 법령 원문으로 청크를 만들고 임베딩해 `data/chroma/`에 저장합니다. 처음 한 번만 하면 됩니다.

```bash
uv run index
```

### 5. 질문하기 (터미널)

```bash
uv run ask "5인 미만 사업장도 연차가 있나요?"
```

### 6. 웹 화면

터미널 두 개에서 API 서버와 화면 개발 서버를 각각 띄웁니다.

```bash
uv run serve
```

```bash
npm --prefix web install
```

```bash
npm --prefix web run dev
```

브라우저에서 http://localhost:5173 을 엽니다. 화면의 `/api` 요청은 Vite가 8000번 포트의 API 서버로 넘깁니다.

### 7. 평가 (선택)

검색 점수는 키 없이 나옵니다.

```bash
uv run eval --only search
```

답변 점수는 Claude가 채점하므로 Anthropic API 키가 필요합니다. `.env.example`을 `.env`로 복사하고 `ANTHROPIC_API_KEY`를 채운 뒤 실행합니다. 41문항 한 번에 Haiku 입력 약 24만, 출력 약 4만 토큰을 씁니다. 같은 답변은 다시 채점하지 않고 캐시를 씁니다.

```bash
uv run eval
```

### 8. 법령 다시 받기 (선택)

법령이 개정되면 원문을 다시 받습니다. [국가법령정보 공동활용](https://open.law.go.kr)에서 인증키(OC)를 발급받아 `.env`의 `LAW_API_OC`에 넣습니다. 인증키는 `.env`에만 두고 커밋하지 않습니다.

```bash
uv run python -m lawbot.collect
```

### 테스트

네트워크와 모델 없이 돕니다.

```bash
uv run pytest
```

## 구조

| 경로 | 역할 |
| --- | --- |
| `src/lawbot/collect.py` | 법령 API 수집 |
| `src/lawbot/index.py` | 청킹, 임베딩, Chroma 저장 (`uv run index`) |
| `src/lawbot/retrieve.py` | 벡터 검색 |
| `src/lawbot/expand.py` | 연결 조문 붙이기 |
| `src/lawbot/search.py` | 검색 결과와 연결 조문을 합쳐 상한까지 자르기 |
| `src/lawbot/answer.py` | 프롬프트, Ollama 호출, 인용 번호 추출, 출처 목록 |
| `src/lawbot/cli.py` | `uv run ask` |
| `src/lawbot/server.py` | `uv run serve`, `POST /api/ask` |
| `src/lawbot/evaluate.py` | `uv run eval`, 검색 채점과 Claude 채점 |
| `src/lawbot/config.py`, `models.py` | 공유 설정, `Chunk`와 `Answer` 형식 |
| `web/src/` | React 화면. `App.tsx`(대화와 입력), `Answer.tsx`(답변과 조문 카드), `api.ts`(요청과 응답 타입) |
| `data/raw/` | 법령 API 응답 원본 |
| `eval/` | 평가 질문, 기준선 |
| `docs/` | 개발 기록 |

## 개발 기록

이 프로젝트는 Claude Code 에이전트와 함께 만들었고, 여러 에이전트에게 작업을 나눠 맡기는 방법도 같이 실험했습니다.

- [docs/roadmap.md](docs/roadmap.md): 처음 세운 계획
- [docs/progress.md](docs/progress.md): 단계별 진행, 결정과 그 이유, 측정 결과
- [docs/law-api.md](docs/law-api.md): 법령 API의 실제 응답 형식과 주의할 점
- [docs/agent-log.md](docs/agent-log.md): 에이전트 세션별 작업과 사용량
- [docs/prompts/](docs/prompts/): 작업 에이전트에게 준 지시문

## 한계

- 수집한 법령은 5개뿐이고 판례와 행정해석은 없습니다. 판례로 정해지는 질문에는 "조문만으로 확정할 수 없다"고 답합니다.
- 질문 하나에 한 번 답합니다. 이전 대화를 반영하지 않고, 답은 다 만들어진 뒤 한 번에 나옵니다.
- 평가 질문 41개는 점수 1~2문항 차이를 구분하기에는 적습니다.
