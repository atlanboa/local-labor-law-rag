export type Citation = {
  number: number
  id: string
  title: string
  effective_date: string
  pending_effective_dates: string[]
  text: string
}

export type AskResponse = {
  reply: string
  citations: Citation[]
  retrieved: string[]
  disclaimer: string
  seconds: number | null
}

export async function ask(question: string, signal?: AbortSignal): Promise<AskResponse> {
  const response = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `서버 오류 ${response.status}`)
  }
  return response.json()
}
