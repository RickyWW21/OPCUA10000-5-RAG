import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type Citation = { label: string; title: string; id: string }
type RetrievedRecord = {
  id: string
  type: string
  title: string
  snippet: string
  section?: string | null
  label: string
}
type Answer = {
  answer: string
  mode: 'generated' | 'offline'
  retrieval_mode: string
  citations: Citation[]
  retrieved: RetrievedRecord[]
  error: string | null
}
type ConversationSummary = { id: string; title: string; updated_at: number }
type StoredMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  mode: 'generated' | 'offline' | null
  retrieval_mode: string | null
  error: string | null
  citations: Citation[]
  retrieved: RetrievedRecord[]
}
type Message = { role: 'user' | 'assistant'; text: string; answer?: Answer }

const apiBase = import.meta.env.VITE_API_BASE_URL ?? ''

async function loadConversation(id: string): Promise<{ id: string; messages: StoredMessage[] }> {
  const response = await fetch(`${apiBase}/api/v1/conversations/${id}`, { credentials: 'include' })
  if (!response.ok) throw new Error('Unable to load conversation')
  return response.json() as Promise<{ id: string; messages: StoredMessage[] }>
}

function storedMessagesToUi(messages: StoredMessage[]): Message[] {
  return messages.map((message) => ({
    role: message.role,
    text: message.content,
    answer: message.role === 'assistant' ? {
      answer: message.content,
      mode: message.mode ?? 'offline',
      retrieval_mode: message.retrieval_mode ?? 'fts',
      citations: message.citations,
      retrieved: message.retrieved,
      error: message.error,
    } : undefined,
  }))
}

function App() {
  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState<'auto' | 'hybrid' | 'fts'>('auto')
  const [topK, setTopK] = useState(6)
  const [depth, setDepth] = useState(0)
  const [online, setOnline] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const bootstrapped = useRef(false)

  useEffect(() => {
    fetch(`${apiBase}/api/v1/health`)
      .then((response) => {
        if (!response.ok) throw new Error('health check failed')
        setApiStatus('online')
      })
      .catch(() => setApiStatus('offline'))
  }, [])

  async function selectConversation(id: string) {
    const conversation = await loadConversation(id)
    setConversationId(conversation.id)
    setMessages(storedMessagesToUi(conversation.messages))
    setError('')
  }

  useEffect(() => {
    if (bootstrapped.current) return
    bootstrapped.current = true
    let cancelled = false
    async function bootstrap() {
      try {
        const response = await fetch(`${apiBase}/api/v1/conversations`, { credentials: 'include' })
        if (!response.ok) throw new Error('Unable to load conversations')
        let summaries = (await response.json() as { conversations: ConversationSummary[] }).conversations
        if (summaries.length === 0) {
          const created = await fetch(`${apiBase}/api/v1/conversations`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'New Part 5 conversation' }),
          })
          if (!created.ok) throw new Error('Unable to create conversation')
          summaries = [await created.json() as ConversationSummary]
        }
        if (cancelled) return
        setConversations(summaries)
        await selectConversation(summaries[0].id)
      } catch (bootstrapError) {
        if (!cancelled) setError(bootstrapError instanceof Error ? bootstrapError.message : 'Unable to load session')
      }
    }
    void bootstrap()
    return () => { cancelled = true }
  }, [])

  const statusLabel = useMemo(() => {
    if (apiStatus === 'online') return 'API connected'
    if (apiStatus === 'offline') return 'API unavailable'
    return 'Checking API'
  }, [apiStatus])

  async function createConversation() {
    try {
      const response = await fetch(`${apiBase}/api/v1/conversations`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New Part 5 conversation' }),
      })
      if (!response.ok) throw new Error('Unable to create conversation')
      const created = await response.json() as ConversationSummary
      setConversations((current) => [created, ...current])
      await selectConversation(created.id)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to create conversation')
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || loading || !conversationId) return
    setQuestion('')
    setError('')
    setMessages((current) => [...current, { role: 'user', text: trimmed }])
    setLoading(true)
    try {
      const response = await fetch(`${apiBase}/api/v1/conversations/${conversationId}/messages`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: trimmed,
          retrieval_mode: mode,
          top_k: topK,
          relationship_depth: depth,
          online,
        }),
      })
      if (!response.ok) throw new Error(await response.text())
      const answer = await response.json() as Answer
      setMessages((current) => [...current, { role: 'assistant', text: answer.answer, answer }])
      setConversations((current) => current.map((conversation) => conversation.id === conversationId
        ? { ...conversation, updated_at: Date.now() / 1000 }
        : conversation))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to query the API')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">OPC UA KNOWLEDGE WORKBENCH</p>
          <h1>Part 5 RAG Console</h1>
        </div>
        <div className={`status-pill ${apiStatus}`}><span />{statusLabel}</div>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <div className="section-heading">
            <span className="section-kicker">01</span>
            <h2>Retrieval controls</h2>
          </div>
          <button className="new-conversation" type="button" onClick={() => void createConversation()}>+ New conversation</button>
          <div className="conversation-list">
            {conversations.map((conversation) => (
              <button
                className={conversation.id === conversationId ? 'conversation-item active' : 'conversation-item'}
                key={conversation.id}
                type="button"
                onClick={() => void selectConversation(conversation.id)}
              >
                {conversation.title}
              </button>
            ))}
          </div>
          <label>
            Retrieval mode
            <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
              <option value="auto">Auto</option>
              <option value="hybrid">Hybrid</option>
              <option value="fts">FTS5 only</option>
            </select>
          </label>
          <label>
            Evidence count
            <input type="range" min="1" max="20" value={topK} onChange={(event) => setTopK(Number(event.target.value))} />
            <span className="range-value">{topK}</span>
          </label>
          <label>
            Relationship depth
            <input type="range" min="0" max="3" value={depth} onChange={(event) => setDepth(Number(event.target.value))} />
            <span className="range-value">{depth}</span>
          </label>
          <label className="switch-row">
            <span>Online generation</span>
            <input type="checkbox" checked={online} onChange={(event) => setOnline(event.target.checked)} />
            <span className="switch" />
          </label>
          <div className="sidebar-note">
            <strong>Anonymous session</strong>
            <p>This browser keeps its own server-side conversation history without requiring an account.</p>
          </div>
        </aside>

        <section className="conversation">
          <div className="section-heading">
            <span className="section-kicker">02</span>
            <h2>Ask the knowledge base</h2>
          </div>
          {messages.length === 0 && (
            <div className="empty-state">
              <div className="empty-mark">⌁</div>
              <h3>Start with a Part 5 question</h3>
              <p>Try “What components does ServerType contain?” or ask about a table, chapter, or relationship.</p>
            </div>
          )}
          <div className="messages">
            {messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <span className="message-label">{message.role === 'user' ? 'YOU' : 'RAG ANSWER'}</span>
                <div className="message-body">{message.text}</div>
                {message.answer && (
                  <div className="answer-meta">
                    <span>{message.answer.mode === 'generated' ? 'Generated' : 'Offline'}</span>
                    <span>{message.answer.retrieval_mode}</span>
                    <span>{message.answer.citations.length} citations</span>
                  </div>
                )}
              </article>
            ))}
            {loading && <article className="message assistant"><span className="message-label">RAG ANSWER</span><div className="loading-line">Retrieving evidence and composing answer…</div></article>}
          </div>
          {error && <div className="error-banner">{error}</div>}
          <form className="composer" onSubmit={handleSubmit}>
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about OPC UA 10000-5 Part 5…" rows={3} />
            <div className="composer-footer">
              <span>Enter a question to retrieve grounded evidence</span>
              <button type="submit" disabled={loading || !conversationId || !question.trim()}>Ask <span aria-hidden="true">↗</span></button>
            </div>
          </form>
        </section>

        <aside className="evidence">
          <div className="section-heading">
            <span className="section-kicker">03</span>
            <h2>Evidence</h2>
          </div>
          {messages.filter((message) => message.answer).length === 0 && <p className="muted">Citations and retrieved records will appear here after your first query.</p>}
          {[...messages].reverse().find((message) => message.answer)?.answer && (
            <EvidencePanel answer={[...messages].reverse().find((message) => message.answer)!.answer!} />
          )}
        </aside>
      </div>
    </main>
  )
}

function EvidencePanel({ answer }: { answer: Answer }) {
  return (
    <div className="evidence-list">
      <div className="evidence-summary"><strong>{answer.citations.length}</strong><span>citations</span><strong>{answer.retrieved.length}</strong><span>records</span></div>
      {answer.citations.map((citation) => (
        <div className="citation" key={citation.id}>
          <span>{citation.label}</span>
          <div><strong>{citation.title}</strong><small>{citation.id}</small></div>
        </div>
      ))}
      <details>
        <summary>Retrieved records</summary>
        {answer.retrieved.map((record) => (
          <div className="record" key={record.id}>
            <div className="record-title"><span>{record.label}</span><strong>{record.title}</strong></div>
            <small>{record.type}{record.section ? ` · §${record.section}` : ''}</small>
            <p>{record.snippet}</p>
          </div>
        ))}
      </details>
    </div>
  )
}

export default App
