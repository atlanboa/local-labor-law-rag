import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ask, type AskResponse } from './api'
import { Answer } from './Answer'

type Turn =
  | { question: string; status: 'pending' }
  | { question: string; status: 'done'; data: AskResponse }
  | { question: string; status: 'error'; message: string }

const EXAMPLES = ['5인 미만 사업장도 연차가 있나요?', '해고 예고는 언제까지 해야 하나요?', '퇴직금은 언제 받을 수 있나요?']

export default function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const bottom = useRef<HTMLDivElement>(null)
  const busy = turns.at(-1)?.status === 'pending'

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  async function submit(question: string) {
    question = question.trim()
    if (!question || busy) return
    setInput('')
    setTurns((t) => [...t, { question, status: 'pending' }])
    const finish = (turn: Turn) => setTurns((t) => [...t.slice(0, -1), turn])
    try {
      finish({ question, status: 'done', data: await ask(question) })
    } catch (error) {
      finish({ question, status: 'error', message: error instanceof Error ? error.message : String(error) })
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    submit(input)
  }

  return (
    <div className="app">
      <header>
        <h1>lawbot</h1>
        <p className="muted">근로기준법 중심 노동법 질문에 근거 조문과 함께 답합니다.</p>
      </header>

      <main>
        {turns.length === 0 && (
          <div className="examples">
            {EXAMPLES.map((q) => (
              <button key={q} onClick={() => submit(q)}>
                {q}
              </button>
            ))}
          </div>
        )}
        {turns.map((turn, i) => (
          <section key={i} className="turn">
            <p className="question">{turn.question}</p>
            {turn.status === 'pending' && <p className="muted">조문을 찾고 답을 쓰는 중…</p>}
            {turn.status === 'error' && <p className="error">{turn.message}</p>}
            {turn.status === 'done' && <Answer data={turn.data} />}
          </section>
        ))}
        <div ref={bottom} />
      </main>

      <form onSubmit={onSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="노동법 질문을 입력하세요"
          maxLength={1000}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          보내기
        </button>
      </form>
    </div>
  )
}
