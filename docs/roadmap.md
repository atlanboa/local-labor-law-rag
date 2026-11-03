# 로컬 LLM 노동법 상담봇 개발 로드맵 & pstack 가이드

Oct 30, 2026

## 프로젝트 개요

내 PC(RTX 5070 Ti 16GB)에서 도는 로컬 LLM으로 **근로기준법 상담봇**을 만들고, 개발은 pstack 워크플로와 여러 Claude 에이전트의 병렬 작업으로 진행한다. 토이 프로젝트이며, 개발 방식 자체를 익히는 것이 두 번째 목표다.

| 항목 | 내용 |
| --- | --- |
| 상담 분야 | 근로기준법 중심 노동법 (해고, 임금, 주휴수당, 연차, 퇴직금) |
| 데이터 | 국가법령정보센터 Open API (법령, 시행령, 판례). 무료, 법령 원문은 저작권 보호 대상 아님 |
| 하드웨어 | RTX 5070 Ti (VRAM 16GB), RAM 32GB |
| 방식 | RAG 먼저, 필요할 때만 LoRA 파인튜닝 |
| 개발 도구 | Claude Code + pstack (Claude Code 포팅판) |

**성공 기준**

- 평가 세트 질문의 80% 이상에서 올바른 조문을 찾아 인용한다.
- 답변마다 근거 조문이나 판례를 출처로 보여준다.
- 모든 답변 하단에 "법률 자문이 아니며, 실제 사안은 노무사나 고용노동부(1350)에 문의" 안내를 붙인다.

80%는 시작점으로 잡은 임시 목표이며, 1단계 기준선 점수를 본 뒤 조정한다.

## pstack 이해하기

pstack은 Lauren Tan(@poteto)이 만든 Cursor 플러그인으로, AI 에이전트에게 "팀의 일하는 방식"을 가르치는 스킬 묶음이다. 에이전트를 신입 엔지니어처럼 온보딩해서, 반복되던 실수를 명시적인 플레이북으로 막는다. [출처](https://flaviocopes.com/pstack.md)

### 핵심 철학

- **넓히기 전에 깊게:** 에이전트 하나가 문제 하나를 끝까지 믿을 만하게 해내게 만든 뒤에 여러 개로 늘린다.
- **적게, 더 좋게:** 목표는 코드를 많이 쓰는 게 아니라, 검증된 코드를 여러 에이전트가 저장소를 어지럽히지 않고 만드는 것이다.
- **검증은 필수:** "빌드가 통과했다"는 증거가 아니다. 변경이 영향을 주는 실제 결과물을 돌려서 확인한다.

### 구성 요소

| 구분 | 이름 | 하는 일 |
| --- | --- | --- |
| 진입점 | `/poteto-mode` | 목표를 말하면 맞는 플레이북을 골라 단계를 할 일 목록으로 만들고, 전문 스킬과 모델을 불러 실행한 뒤 검증한다 |
| 플레이북 | Feature, Bug fix, Refactoring, Hillclimb 등 | 작업 종류별 절차. 예: Bug fix는 재현부터, Hillclimb는 가설 → 측정 → 유지/폐기 반복 |
| 이해 | `/how`, `/why`, `/teach` | 코드가 어떻게 도는지, 왜 그렇게 만들었는지 조사해 설명 |
| 설계 | `/architect` | 호출하는 쪽 사용법부터 설계를 잡고 구현. "with checkpoint"를 붙이면 설계 승인 후 진행 |
| 멀티 모델 | `/arena` | 같은 과제를 여러 모델에게 따로운 worktree에서 맡기고, 다른 모델이 채점해 최선안을 고름 |
| 멀티 에이전트 | `/swarm` | 서로 독립적인 작업 조각을 여러 워커에게 나눠주고 PASS / ISSUES / BLOCKED 보고 하나로 모음 |
| 리뷰 | `/interrogate` | 같은 diff를 여러 모델이 리뷰. 지적을 분류만 하고 직접 고치지는 않음 |
| 검증 | `/create-verification-skill` | 앱을 띄우고 동작을 확인하는 프로젝트 전용 `verify-<app>` 스킬 생성 |
| 원칙 | 23개 원칙 스킬 | Laziness Protocol(최소 변경), Prove It Works, Fix Root Causes, 병렬 작업자는 worktree 분리 등 |
| 설정 | `/setup-pstack` | 구현, 조사, 판단, 리뷰 역할별로 어떤 모델을 쓸지 지정 |

poteto-mode는 한 번 켜면 유지되어 "continue" 같은 후속 요청도 같은 플레이북 안에서 처리한다. 다른 일로 넘어갈 때는 "new task"라고 말한다.

### Claude Code에서 쓰려면

원본은 Cursor용이라, Claude Code에서는 커뮤니티 포팅판을 쓴다. 아래는 [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude) 기준이며, Claude Code 2.1.292 이상이 필요하다.

```
/plugin marketplace add michael-denyer/pstack-claude
/plugin install pstack@pstack-claude
/pstack:setup-pstack
```

- 포팅판은 세션 시작 시 작업을 poteto-mode로 보내는 훅을 추가한다.
- 서드파티 마켓플레이스는 자동 업데이트가 꺼져 있다. `/plugin` → Marketplaces에서 켜거나, `claude plugin update pstack@pstack-claude`로 수동 업데이트한다.
- Cursor 전용 기능(`/loop`, Cursor의 서브에이전트별 모델 지정 등)은 그대로 쓸 수 없다.
- Orchestrate나 배포 플레이북은 GitHub과 Graphite를 전제로 한다. 이 프로젝트에는 필요 없다.
- 여러 에이전트가 동시에 도는 플레이북은 토큰 비용이 크다. 평소 작업은 가벼운 모델에, 어려운 부분만 고성능 모델에 맡기는 것이 좋다.

## 기술 스택

모두 무료이고 로컬에서 돈다. 모델은 하나로 정해두지 않고, 1단계 평가 세트로 후보를 비교해서 고른다.

| 계층 | 선택 | 비고 |
| --- | --- | --- |
| LLM 실행 | [Ollama](https://ollama.com) | OpenAI 호환 API 제공. Windows에서도 설치만 하면 됨 |
| 모델 후보 | Qwen 3.5 9B (Q8), Gemma 4 12B (Q4\_K\_M, 약 7GB) | 둘 다 16GB VRAM에 여유 있게 들어감. 시작 시점에 최신 추천을 한 번 더 확인 ([16GB 벤치마크](https://www.glukhov.org/post/2026/01/choosing-best-llm-for-ollama-on-16gb-vram-gpu/), [16GB 모델 목록](https://bestllmfor.com/guide/quel-llm-16-go-vram/)) |
| 임베딩 | bge-m3 (다국어) | 한국어 검색에 적합. Ollama로도 실행 가능 |
| 벡터 DB | Chroma | 파일 하나로 도는 임베디드 DB. 규모가 커지면 Qdrant로 교체 |
| 언어 | Python + uv | 수집, RAG, 평가 스크립트 모두 Python |
| 데이터 소스 | [국가법령정보 공동활용 Open API](https://open.law.go.kr/LSO/openApi/guideList.do) | 회원가입 후 활용신청하면 인증키(OC) 발급. 보통 즉시 승인 |
| UI (2단계) | Gradio 또는 Streamlit | 채팅 화면을 몇 줄로 만들 수 있음 |
| 파인튜닝 (3단계) | Unsloth + QLoRA | 7\~9B 모델은 16GB에서 학습 가능 |

**수집 대상 법령 (1단계):** 근로기준법, 근로기준법 시행령, 최저임금법, 근로자퇴직급여 보장법, 남녀고용평등과 일·가정 양립 지원에 관한 법률. 판례는 2단계에서 추가한다.

## 1단계: 에이전트 하나로 RAG MVP 만들기

목표는 평가 스크립트를 실행하면 점수가 나오는 상태다. pstack의 "넓히기 전에 깊게" 원칙에 따라, 이 단계는 Claude Code 세션 하나와 `/poteto-mode`만으로 진행한다.

1. **환경 준비:** Ollama 설치, 모델 후보 2개와 bge-m3 받기. 법령 API 인증키 발급.
2. **데이터 수집:** 법령 API로 수집 대상 법령 5개를 받아 JSON으로 저장하는 스크립트.
   - poteto-mode 플레이북: Feature
3. **청킹과 임베딩:** 조문 단위로 자르고, 법령명·조번호·조문 제목을 메타데이터로 붙여 Chroma에 저장.
4. **평가 세트 작성 (제일 중요):** 질문 30\~50개와 각 질문의 정답 조문, 모범 답변 요지. 예: "5인 미만 사업장도 연차가 있나요?"
   - 질문 초안은 Claude가 만들고, 정답 조문은 사람이 원문을 보고 확인한다.
5. **상담 파이프라인:** 질문 → 관련 조문 검색(상위 5개) → 프롬프트에 넣고 Ollama 호출 → 출처 포함 답변. CLI로 실행.
6. **평가 스크립트:** 두 가지 점수를 낸다.
   - 검색 점수: 정답 조문이 검색 상위 5개 안에 들었는가 (자동 채점)
   - 답변 점수: 답변이 모범 답변과 맞는가 (Claude가 채점자 역할)
7. **모델 선택:** 후보 2개를 같은 평가 세트로 돌려 점수가 높은 쪽을 기본 모델로 정한다.
8. **검증 스킬 만들기:** `/create-verification-skill`로 "Ollama가 떠 있는지 확인 → 평가 실행 → 점수 기록"을 하는 프로젝트 스킬을 만든다. 2단계의 모든 에이전트가 이 스킬로 자기 작업을 검증한다.

**완료 조건:** `uv run eval` 한 줄로 검색 점수와 답변 점수가 출력되고, 그 값이 기준선으로 파일에 기록된다.

## 2단계: 여러 Claude 에이전트로 병렬 개발

1단계 기준선이 생긴 뒤에야 작업을 나눈다. 각 에이전트는 자기 git worktree에서 일하고, 평가 점수가 기준선 이상인 PR만 main에 합친다.

&#91;embedded content: 멀티 에이전트 구성 · worktree 4개, 병합 관문 1개\]

평가 점수가 네 에이전트의 공통 기준이다. 누가 무엇을 바꿨든 같은 스크립트로 좋아졌는지 판단한다.

### 운영 방식

1. 에이전트마다 worktree를 만든다. 예: `git worktree add ../lawbot-search -b feat/search`
2. worktree마다 Claude Code를 따로 실행하고, `/poteto-mode`에 목표와 검증 방법(1단계에서 만든 검증 스킬)을 준다.
3. 또는 메인 세션 하나에서 `/swarm`으로 독립적인 작업을 서브에이전트에게 나눠 맡긴다.
4. 같은 문제에 접근법이 여럿이면 `/arena`로 경쟁시킨다. 예: 청킹 전략 3가지를 각각 구현하고 검색 점수로 비교.
5. PR마다 `/interrogate`로 여러 모델의 리뷰를 받고, 평가 점수를 PR 설명에 붙인다.
6. 평가 세트와 공통 스키마처럼 여러 에이전트가 쓰는 파일은 평가 에이전트만 고친다. 동시에 같은 파일을 고치면 충돌한다.

**첫 병렬 실험:** 데이터와 검색 에이전트 둘만 동시에 돌려보고, 충돌과 비용을 확인한 뒤 늘린다.

## 3단계 (선택): LoRA 파인튜닝

RAG로 지식은 해결되므로, 파인튜닝은 **말투와 답변 형식**이 아쉬울 때만 한다. 2단계 평가에서 "조문은 맞게 찾는데 답변이 딱딱하거나 형식이 들쭉날쭉하다"는 결과가 나오면 진행한다.

1. 2단계에서 점수가 높았던 답변과 직접 다듬은 답변으로 학습 데이터 300\~1,000쌍을 만든다.
2. Unsloth로 기본 모델에 QLoRA 학습을 한다. 9B급 모델은 16GB VRAM에서 가능하다.
3. 학습한 모델을 GGUF로 변환해 Ollama에 올린다.
4. 같은 평가 세트로 학습 전후를 비교한다. 검색 점수는 그대로이고 답변 점수가 올라야 채택한다.

pstack에서는 이 단계를 Hillclimb 플레이북(가설 → 측정 → 유지/폐기)으로 돌리기 좋다.

## 시작 체크리스트와 주의사항

- [ ] PC OS 확인 (Windows라면 WSL2를 쓸지 결정)
- [ ] Claude Code를 2.1.292 이상으로 업데이트
- [ ] pstack 포팅판 설치 후 `/pstack:setup-pstack` 실행
- [ ] Ollama 설치, 모델 후보 2개와 bge-m3 받기
- [ ] 국가법령정보 Open API 회원가입 및 인증키 발급
- [ ] GitHub에 빈 저장소 만들기 (worktree와 PR 리뷰에 필요)
- [ ] 첨 세션: `/poteto-mode`에 "법령 수집 스크립트 + 검증 방법"을 목표로 주기

**주의사항**

- pstack 포팅판은 비공식 저장소다. 설치 전에 README와 훅 코드를 한 번 읽어본다.
- 인증키는 `.env`에만 두고 `.gitignore`에 넣는다. 에이전트가 커밋하지 않게 한다.
- 로컬 LLM 실행 중에는 GPU를 독점한다. 여러 에이전트가 동시에 평가를 돌리면 느려지므로, 평가 실행은 한 번에 하나씩 한다.
- 멀티 에이전트 작업은 Claude 사용량을 빠르게 쓴다. 처음에는 2개만 병렬로 돌려본다.
- 법령은 개정된다. 수집 시점을 메타데이터로 남기고 답변에 "기준일"을 표시한다.

## 참고 자료

- [pstack 원본 (cursor/plugins)](https://github.com/cursor/plugins/tree/main/pstack)
- [A deep dive into pstack – Flavio Copes](https://flaviocopes.com/pstack.md)
- [pstack-claude (Claude Code 포팅판)](https://github.com/michael-denyer/pstack-claude)
- [국가법령정보 공동활용 Open API 가이드](https://open.law.go.kr/LSO/openApi/guideList.do)
- [korean-law-mcp (API 키 발급 절차 참고)](https://github.com/SeoNaRu/korean-law-mcp)
- [Ollama 16GB VRAM 모델 벤치마크](https://www.glukhov.org/post/2026/01/choosing-best-llm-for-ollama-on-16gb-vram-gpu/)
- [16GB VRAM용 모델 목록](https://bestllmfor.com/guide/quel-llm-16-go-vram/)
