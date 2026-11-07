# 채점기 모순 줄이기

채점기(Haiku)가 핵심 내용 판정의 `reason`에는 충족이라고 쓰고 `met`은 false로 내는 경우가 있다. 그러면 맞게 답한 문항이 틀림으로 세어진다. 이 작업은 그 모순을 세고, 줄이고, 줄었는지 잰다. 배경은 [progress.md](../progress.md)의 "검색 개선"에 있다.

**모델은 Sonnet으로 한다.** 고칠 파일이 `evaluate.py` 하나이고 범위가 정해진 작업이다. 검색 개선 B에서 Sonnet이 수정 지시 0회로 끝냈다. 이번에도 같은 방식으로 검증해 [agent-log.md](../agent-log.md)에 적는다.

## 준비

`lawbot` 폴더에서 실행한다. `.env`와 채점 캐시는 git에 없으므로 복사한다.

```bash
cd <작업 폴더>\lawbot
git worktree add ../lawbot-judge -b feat/judge-reason-first
mkdir ..\lawbot-judge\eval\results
copy .env ..\lawbot-judge\.env
xcopy /E /I eval\results\judge-cache ..\lawbot-judge\eval\results\judge-cache
cd ..\lawbot-judge
claude --model sonnet
```

## 지시문

```text
lawbot 답변 채점기의 모순을 줄여줘. 먼저 CLAUDE.md, docs/progress.md("검색 개선" 항목), eval/README.md, .claude/skills/verify/SKILL.md, src/lawbot/evaluate.py, tests/test_evaluate.py를 읽어.

지금 폴더(../lawbot-judge, 브랜치 feat/judge-reason-first)에서만 작업해. 커밋까지만 하고 push와 병합은 하지 마.
수정할 파일: src/lawbot/evaluate.py의 채점 부분(JUDGE_SYSTEM, KeyPointVerdict, Verdict, judge_prompt, RUBRIC_VERSION, 그리고 모순을 세는 함수를 넣는다면 그 함수), tests/test_evaluate.py.
고치지 말 파일: src/lawbot/answer.py, search.py, retrieve.py, expand.py, index.py, config.py, models.py, cli.py, scripts/, eval/questions.jsonl, eval/baseline.json, pyproject.toml, uv.lock. 바꿔야 하면 멈추고 이유를 보고해.

배경:
- 채점은 claude-haiku-5-5가 Verdict 스키마(messages.parse)로 한다. 핵심 내용마다 KeyPointVerdict(index, met, reason)를 낸다. 필드 순서가 met 다음 reason이라, 판정을 먼저 내고 사유를 나중에 쓴다.
- 문항은 핵심 내용이 모두 met이고, fabricated가 false이고, citations_supported가 true여야 맞음이다(answer_score). met 하나만 틀려도 문항이 틀림이 된다.
- eval/control-k8.json(k=8 실행)에서 q002, q013, q032가 사유는 충족인데 met은 false였다. 기준선(eval/baseline.json)에는 이런 모순이 0건이었다.
- 채점 결과는 eval/results/judge-cache/*.json에 있다(약 300개). 각 파일의 verdict가 판정 전체다.
- 답변(Gemma)은 GPU를 다른 프로그램이 쓰지 않으면 같은 순서에서 기준선과 글자까지 같게 나온다. 평가 전에 nvidia-smi로 GPU가 비었는지 본다.

할 일:
1. 모순을 센다. judge-cache 전체와 control-k8.json에서 reason과 met이 어긋난 판정을 찾는다. 낱말 규칙(예: "충족" 포함인데 "충족하지", "미충족", "누락"은 없음)으로 후보를 뽑고, 후보는 직접 읽고 판단해. 양쪽 방향(사유는 충족인데 met false, 사유는 미충족인데 met true)을 다 본다. fabricated, citations_supported, expected_behavior_met의 사유와 판정도 같은 방식으로 본다. 결과를 표로 남겨: 파일 또는 문항 id, 항목, 사유 요약, met, 어느 쪽이 맞는지.
2. 고친다. 먼저 사유를 판정보다 앞에 쓰게 한다: KeyPointVerdict와 Verdict의 필드 순서를 reason이 앞에 오게 바꾸고, JUDGE_SYSTEM에 사유를 먼저 쓰고 그 사유에 맞게 판정하라고 적는다. 그것으로 부족할 때만 지시문의 기준을 더 분명하게 고친다. 채점 지시나 스키마를 바꾸면 RUBRIC_VERSION을 올린다.
3. 잰다. 다시 채점할 대상은 두 묶음이다.
   a. 모순이 있던 판정의 답변들(control-k8.json의 q002, q013, q032와 1번에서 찾은 것). 이 답변은 Gemma를 다시 돌리지 말고, 결과 파일에 남은 답변 문장과 context_ids로 judge_prompt와 claude_judge를 직접 불러 다시 채점한다. 스크립트는 저장소 밖 임시 폴더에 둔다.
   b. 기준선 전체: GPU가 빈 것을 확인하고 uv run eval을 한 번 돌린다. 답변 문장이 기준선과 같은지 먼저 확인한다(다르면 그 문항은 따로 표시한다).
   두 묶음 모두 모순이 몇 건으로 줄었는지, 맞음과 틀림이 바뀐 문항이 무엇인지 본다.
4. 고친 방법이 하나로 부족해 다른 방법을 시도하면 3b의 전체 채점은 최종안에서 한 번만 돌린다. 3a는 시도마다 돌려도 된다.
5. tests/test_evaluate.py: 바뀐 스키마 순서, RUBRIC_VERSION이 캐시 키를 바꾸는지, 모순 세는 함수를 넣었다면 그 함수. Claude API 없이 돌아야 한다. 기존 테스트도 모두 통과해야 한다.
6. 마지막에 /verify를 한 번 돌린다. 채점 기준이 바뀌었으므로 답변 점수가 기준선과 달라도 FAIL 자체는 실패로 보지 않는다. 대신 바뀐 문항마다 새 채점이 맞는지 사유를 읽고 판단해 보고한다.

지킬 것:
- 채점 모델(JUDGE_MODEL)은 바꾸지 않는다.
- 문항 id나 질문 문구를 코드나 채점 지시에 넣지 마. 특정 문항에 맞춘 지시는 과적합이다.
- --save-baseline은 쓰지 않는다. 채점 기준이 바뀌면 기준선을 다시 저장해야 하지만 그건 사람이 정한다.
- Claude API 호출은 3a(시도마다 수십 회 이하), 3b 한 번(약 41회), /verify 한 번(3b와 답이 같으면 0회)으로 제한한다. 그 밖에 전체 채점을 더 돌려야 하면 멈추고 보고해.
- 기존 judge-cache 파일은 지우거나 고치지 마. RUBRIC_VERSION을 올리면 새 키로 따로 쌓인다.
- 인증키를 출력하거나 파일에 쓰지 않는다. .env를 cat하지 않는다.
- Claude 데스크톱 앱 안에서는 UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.local\share\uv\python이 필요하다.

완료 보고에 포함해:
- 1번 표와 모순 건수(항목별, 방향별)
- 바뀐 파일과 핵심 위치(파일:줄)
- 3a, 3b 결과: 모순 건수 전후, 맞음과 틀림이 바뀐 문항과 그 이유
- /verify 출력 요약: 검색과 답변 점수, 새로 맞힌 문항과 새로 틀린 문항, API 호출 수
- 새 채점이 오히려 틀렸다고 보이는 판정
- 기준선을 다시 저장해도 되는지에 대한 판단과 근거
```

## 검증할 것

보고를 받으면 메인 세션에서 확인한다.

- `git diff main...feat/judge-reason-first`로 범위 밖 변경이 없는지 본다. `evaluate.py`는 채점 부분만 바뀌어야 한다.
- 채점 지시에 문항 id나 질문 문구가 없는지 본다.
- 모순이 있던 판정 몇 개를 새 채점 결과와 나란히 직접 읽는다.
- 기본값으로 직접 `/verify`를 돌린다. 답이 같으면 채점 호출은 0회여야 한다.
- 바뀐 문항의 새 채점 사유를 읽고, 기준선을 다시 저장할지 정한다.
- [agent-log.md](../agent-log.md)에 적는다: 사람 입력, 수정 지시, 범위 밖 변경, 출력 토큰, 결과.
