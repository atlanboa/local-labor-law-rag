# 검증 스킬 지시문

1단계 마지막 작업이다. 2단계 작업자가 자기 worktree에서 자기 변경을 검증할 때 쓸 프로젝트 스킬을 만든다. [roadmap.md](../roadmap.md) 1단계 8번에 해당한다.

새 CLI 세션 하나에서 진행한다. 다른 작업과 동시에 돌리지 않는다. 결과 확인은 [agent-log.md](../agent-log.md)의 교훈대로 보고와 따로 한다.

```bash
cd <작업 폴더>\lawbot
```

```text
/pstack:create-verification-skill
lawbot의 변경을 검증하는 프로젝트 스킬을 만들어줘. 먼저 CLAUDE.md, docs/progress.md, eval/README.md, README.md를 읽어.

작업 전에 main에서 feat/verify-skill 브랜치를 만들어. 커밋까지만 하고 push와 병합은 하지 마.
수정할 파일: .claude/skills/ 아래 스킬 파일, 스킬이 부르는 스크립트가 필요하면 scripts/ 아래 새 파일.
고치지 말 파일: src/, tests/, eval/questions.jsonl, eval/baseline.json, pyproject.toml, uv.lock. 바꿔야 하면 멈추고 이유를 보고해.

쓰는 사람: 2단계 작업자. 각자 ../lawbot-<작업명> worktree에서 이 스킬을 실행해 자기 변경이 기준선보다 나빠지지 않았는지 확인한다. 그래서 스킬은 실행한 폴더의 data/chroma, eval/results, .env를 써야 하고, 다른 worktree의 파일을 읽으면 안 된다.

스킬이 할 일, 순서대로:
1. 준비 확인. Ollama가 config.OLLAMA_URL에서 응답하는지, config.EMBED_MODEL과 config.CHAT_MODEL이 /api/tags에 있는지 본다. 모델 이름은 config에서 읽고 스킬에 적지 마. LAWBOT_CHAT_MODEL로 바뀔 수 있어. 실패하면 무엇이 없는지 말하고 멈춘다.
2. uv run pytest. 실패하면 멈춘다.
3. uv run index. 저장 개수가 data/chunks/chunks.jsonl 줄 수와 Chroma 컬렉션 개수가 같은지 본다.
4. uv run eval --only search. 검색 점수를 eval/baseline.json과 비교한다.
5. .env에 ANTHROPIC_API_KEY가 있을 때만 uv run eval. 없으면 답변 평가는 건너뛰었다고 분명히 적는다. 채점은 eval/results/judge-cache를 쓰므로 답변이 그대로면 API를 다시 부르지 않는다.
6. 판정. 검색 점수와 답변 점수가 모두 기준선 이상이면 PASS, 하나라도 낮으면 FAIL. 점수가 같아도 새로 틀린 문항이 있으면 그 id를 적는다. 유형별 점수 변화도 적는다.

지킬 것:
- --save-baseline은 절대 쓰지 않는다. 기준선 갱신은 사람이 정한다.
- 평가는 GPU 하나를 쓰므로 동시에 하나만 돌린다. 스킬 설명에 적어.
- 인증키를 출력하거나 파일에 쓰지 않는다. .env에 키가 있는지는 값 없이 있다, 없다만 본다.
- Claude 데스크톱 앱 안에서는 uv가 Python 설치에 실패한다. UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.local\share\uv\python이 필요하다는 것을 스킬에 적어. docs/progress.md 환경 메모에 있다.
- 결과 보고는 짧게: 단계별 통과 여부, 기준선 대비 점수, 새로 틀린 문항, 걸린 시간, 결과 파일 경로.

스킬이 잡아야 할 실패를 직접 만들어 보여줘. 각 시험 뒤에 git status가 깨끗한지 확인해.
- LAWBOT_OLLAMA_URL을 없는 포트로 주면 1단계에서 멈춘다.
- LAWBOT_CHAT_MODEL을 설치되지 않은 이름으로 주면 1단계에서 멈춘다.
- 검색 점수가 기준선보다 낮으면 FAIL이 나온다. 코드를 고치지 말고, 임시로 eval/baseline.json의 검색 점수를 높인 사본을 만들어 시험한 뒤 원래대로 되돌려. 되돌린 뒤 git diff eval/baseline.json이 비어 있어야 한다.
- 지금 main 상태로 실행하면 PASS가 나오고 점수가 기준선과 같다.

완료 보고에 포함해:
- 만든 파일과 핵심 위치(파일:줄)
- 스킬을 부르는 방법과 출력 예
- 위 실패 시험 4개의 실제 출력
- 지금 main에서 실행한 전체 결과와 걸린 시간, Claude API 호출 수
```
