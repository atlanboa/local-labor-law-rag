import { useState } from 'react'
import type { AskResponse } from './api'

const MARKER = /(\[\d+(?:\s*,\s*\d+)*\])/

function Reply({ text, onCite }: { text: string; onCite: (n: number) => void }) {
  return (
    <p className="reply">
      {text.split(MARKER).map((part, i) => {
        if (!MARKER.test(part)) return part
        const numbers = part.slice(1, -1).split(',').map((n) => Number(n.trim()))
        return numbers.map((n) => (
          <button key={`${i}-${n}`} className="marker" onClick={() => onCite(n)}>
            {n}
          </button>
        ))
      })}
    </p>
  )
}

export function Answer({ data }: { data: AskResponse }) {
  const [open, setOpen] = useState<number | null>(null)
  const toggle = (n: number) => setOpen((current) => (current === n ? null : n))

  return (
    <div className="answer">
      <Reply text={data.reply} onCite={toggle} />
      {data.citations.length > 0 ? (
        <ul className="citations">
          {data.citations.map((c) => (
            <li key={c.number} className={open === c.number ? 'open' : ''}>
              <button className="citation-head" onClick={() => toggle(c.number)}>
                <span className="marker">{c.number}</span>
                <span>{c.id}</span>
                <span className="muted">{c.effective_date} 시행</span>
              </button>
              {c.pending_effective_dates.map((day) => (
                <p key={day} className="pending">
                  {day} 시행 예정 개정이 있습니다.
                </p>
              ))}
              {open === c.number && <pre className="article">{c.text}</pre>}
            </li>
          ))}
        </ul>
      ) : (
        data.retrieved.length > 0 && (
          <p className="muted">답변이 인용한 조문이 없습니다. 검색된 조문: {data.retrieved.join(', ')}</p>
        )
      )}
      <p className="disclaimer">{data.disclaimer}</p>
      {data.seconds !== null && <p className="muted small">답변 생성 {data.seconds}초</p>}
    </div>
  )
}
