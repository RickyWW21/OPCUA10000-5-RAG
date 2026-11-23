import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type SourceLocation = {
  section?: string | null
  table?: string | null
  start_line: number
  end_line: number
}
type EvidenceSource = {
  kind: 'spec'
  path: string
  version: string
  locations: SourceLocation[]
  url?: string
}
type Citation = {
  label: string
  title: string
  id: string
  provenance?: Record<string, unknown>
  source?: EvidenceSource
}
type RetrievedRecord = {
  id: string
  type: string
  title: string
  snippet: string
  section?: string | null
  table_number?: string | null
  label: string
  doc?: string
  provenance?: Record<string, unknown>
  source?: EvidenceSource
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
type ContentResponse = {
  kind: 'spec'
  path: string
  title: string
  version: string
  start_line: number
  end_line: number
  content: string
  locations: SourceLocation[]
}
type OpenTarget = { path: string; startLine?: number; endLine?: number }

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

function contentRequestUrl(target: OpenTarget): string {
  const params = new URLSearchParams({ path: target.path })
  if (target.startLine !== undefined) params.set('start_line', String(target.startLine))
  if (target.endLine !== undefined) params.set('end_line', String(target.endLine))
  return `${apiBase}/api/v1/content?${params.toString()}`
}

function versionLabel(version: string | null | undefined): string {
  const value = version?.trim()
  if (!value || value.toLowerCase() === 'unavailable') return '版本不可用'
  return value.toLowerCase().startsWith('v') ? value : `v${value}`
}

function sourceKindLabel(): string {
  return '规范原文'
}

function sourceStatusLabel(): string {
  return 'OPC UA Part 5'
}

function locationLabel(location: SourceLocation): string {
  const parts: string[] = []
  parts.push(location.section ? `§${location.section}` : '章节不可用')
  if (location.table) parts.push(`Table ${location.table}`)
  if (Number.isInteger(location.start_line) && Number.isInteger(location.end_line)) {
    parts.push(`L${location.start_line}-L${location.end_line}`)
  } else {
    parts.push('行号不可用')
  }
  return parts.join(' · ')
}

function citationSource(citation: Citation, answer: Answer): EvidenceSource | undefined {
  return citation.source ?? answer.retrieved.find((record) => record.label === citation.label)?.source
}

async function responseError(response: Response): Promise<string> {
  let detail = ''
  try {
    const body = await response.json() as { detail?: unknown }
    if (typeof body.detail === 'string') detail = body.detail
    else if (body.detail !== undefined) {
      const serialized = JSON.stringify(body.detail)
      detail = typeof serialized === 'string' ? serialized : ''
    }
  } catch {
    // The status code is still useful when the body is not JSON.
  }
  return detail || `来源请求失败（HTTP ${response.status}）`
}

function App() {
  const [question, setQuestion] = useState('')
  const [topK, setTopK] = useState(6)
  const [depth, setDepth] = useState(0)
  const [online, setOnline] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [activeCitation, setActiveCitation] = useState('')
  const [openTarget, setOpenTarget] = useState<OpenTarget | null>(null)
  const conversationRequest = useRef(0)
  const queryAbort = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${apiBase}/api/v1/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('health check failed')
        setApiStatus('online')
      })
      .catch(() => {
        if (!controller.signal.aborted) setApiStatus('offline')
      })
    return () => controller.abort()
  }, [])

  useEffect(() => () => {
    queryAbort.current?.abort()
  }, [])

  async function selectConversation(id: string) {
    const requestId = ++conversationRequest.current
    try {
      const conversation = await loadConversation(id)
      if (requestId !== conversationRequest.current) return
      setConversationId(conversation.id)
      setMessages(storedMessagesToUi(conversation.messages))
      setActiveCitation('')
      setError('')
    } catch (conversationError) {
      if (requestId !== conversationRequest.current) return
      setError(conversationError instanceof Error ? conversationError.message : 'Unable to load conversation')
    }
  }

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        const response = await fetch(`${apiBase}/api/v1/conversations`, { credentials: 'include' })
        if (!response.ok) throw new Error('Unable to load conversations')
        let summaries = (await response.json() as { conversations: ConversationSummary[] }).conversations
        if (cancelled) return
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

  const latestAnswer = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].answer) return messages[index].answer
    }
    return undefined
  }, [messages])

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
    setActiveCitation('')
    setMessages((current) => [...current, { role: 'user', text: trimmed }])
    setLoading(true)
    queryAbort.current?.abort()
    const controller = new AbortController()
    queryAbort.current = controller
    try {
      const response = await fetch(`${apiBase}/api/v1/conversations/${conversationId}/messages`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          question: trimmed,
          top_k: topK,
          relationship_depth: depth,
          online,
        }),
      })
      if (!response.ok) throw new Error(await response.text())
      const answer = await response.json() as Answer
      if (controller.signal.aborted) return
      setMessages((current) => [...current, { role: 'assistant', text: answer.answer, answer }])
      setConversations((current) => current.map((conversation) => conversation.id === conversationId
        ? { ...conversation, updated_at: Date.now() / 1000 }
        : conversation))
    } catch (requestError) {
      if (controller.signal.aborted) return
      setError(requestError instanceof Error ? requestError.message : 'Unable to query the API')
    } finally {
      if (queryAbort.current === controller) {
        queryAbort.current = null
        setLoading(false)
      }
    }
  }

  function openSource(source: EvidenceSource, location?: SourceLocation) {
    const selected = location ?? source.locations[0]
    if (!selected) {
      setError('该来源没有可验证的行号，无法打开规范原文。')
      return
    }
    setOpenTarget({
      path: source.path,
      startLine: selected.start_line,
      endLine: selected.end_line,
    })
  }

  function openCitation(answer: Answer, label: string) {
    const citation = answer.citations.find((item) => item.label === label)
    const source = citation?.source ?? answer.retrieved.find((record) => record.label === label)?.source
    setActiveCitation(label)
    if (!source) {
      setError('该引用缺少可验证的来源元数据。')
      return
    }
    openSource(source)
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
                <div className="message-body">
                  <AnswerText
                    text={message.text}
                    citations={message.answer?.citations ?? []}
                    activeCitation={activeCitation}
                    onCitationClick={(label) => {
                      if (message.answer) openCitation(message.answer, label)
                    }}
                  />
                </div>
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
          {!latestAnswer && <p className="muted">Citations and retrieved records will appear here after your first query.</p>}
          {latestAnswer && (
            <EvidencePanel
              answer={latestAnswer}
              activeCitation={activeCitation}
              onActivate={setActiveCitation}
              onOpenSource={openSource}
            />
          )}
        </aside>
      </div>

      <ContentViewer
        target={openTarget}
        onClose={() => setOpenTarget(null)}
      />
    </main>
  )
}

function AnswerText({
  text,
  citations,
  activeCitation,
  onCitationClick,
}: {
  text: string
  citations: Citation[]
  activeCitation: string
  onCitationClick: (label: string) => void
}) {
  const labels = useMemo(() => new Set(citations.map((citation) => citation.label)), [citations])
  const parts = text.split(/(\[[ETCR]\d+\])/g)
  return (
    <>
      {parts.map((part, index) => labels.has(part) ? (
        <button
          className={part === activeCitation ? 'answer-citation active' : 'answer-citation'}
          key={`${part}-${index}`}
          type="button"
          onClick={() => onCitationClick(part)}
          title={`打开 ${part} 对应来源`}
        >
          {part}
        </button>
      ) : <span key={`text-${index}`}>{part}</span>)}
    </>
  )
}

function EvidencePanel({
  answer,
  activeCitation,
  onActivate,
  onOpenSource,
}: {
  answer: Answer
  activeCitation: string
  onActivate: (label: string) => void
  onOpenSource: (source: EvidenceSource, location?: SourceLocation) => void
}) {
  const groups = answer.citations.reduce<{ spec: Citation[]; unknown: Citation[] }>(
    (result, citation) => {
      const source = citationSource(citation, answer)
      if (!source || source.kind !== 'spec') result.unknown.push(citation)
      else result.spec.push(citation)
      return result
    },
    { spec: [], unknown: [] },
  )

  return (
    <div className="evidence-list">
      <div className="evidence-summary"><strong>{answer.citations.length}</strong><span>citations</span><strong>{answer.retrieved.length}</strong><span>records</span></div>
      {groups.spec.length > 0 && (
        <section className="evidence-group spec-group" aria-labelledby="spec-evidence-heading">
          <h3 className="evidence-group-title" id="spec-evidence-heading">规范原文 <small>Part 5 source</small></h3>
          {groups.spec.map((citation) => (
            <CitationCard
              key={`${citation.label}-${citation.id}`}
              citation={citation}
              source={citationSource(citation, answer)}
              active={citation.label === activeCitation}
              onActivate={onActivate}
              onOpenSource={onOpenSource}
            />
          ))}
        </section>
      )}
      {groups.unknown.length > 0 && (
        <section className="evidence-group" aria-labelledby="unknown-evidence-heading">
          <h3 className="evidence-group-title" id="unknown-evidence-heading">来源元数据待补充</h3>
          {groups.unknown.map((citation) => (
            <CitationCard
              key={`${citation.label}-${citation.id}`}
              citation={citation}
              source={undefined}
              active={citation.label === activeCitation}
              onActivate={onActivate}
              onOpenSource={onOpenSource}
            />
          ))}
        </section>
      )}
      <details className="retrieved-details">
        <summary>Retrieved records</summary>
        {answer.retrieved.map((record) => (
          <div className="record" key={`${record.label}-${record.id}`}>
            <div className="record-title"><span>{record.label}</span><strong>{record.title}</strong></div>
            <small>{record.type}{record.section ? ` · §${record.section}` : ''}{record.table_number ? ` · Table ${record.table_number}` : ''}</small>
            {record.source && <SourceMeta source={record.source} onOpenSource={onOpenSource} compact />}
            <EvidenceSnippet text={record.snippet} />
          </div>
        ))}
      </details>
    </div>
  )
}

function CitationCard({
  citation,
  source,
  active,
  onActivate,
  onOpenSource,
}: {
  citation: Citation
  source: EvidenceSource | undefined
  active: boolean
  onActivate: (label: string) => void
  onOpenSource: (source: EvidenceSource, location?: SourceLocation) => void
}) {
  return (
    <article className={`citation-card ${source?.kind ?? 'unknown'} ${active ? 'active' : ''}`}>
      <div className="citation-card-head">
        <button
          className="citation-label-button"
          type="button"
          onClick={() => onActivate(citation.label)}
          title={`选中 ${citation.label}`}
        >
          {citation.label}
        </button>
        {source && <span className={`source-badge ${source.kind}`}>{sourceKindLabel()}</span>}
      </div>
      <strong className="citation-title">{citation.title}</strong>
      <code className="citation-id">{citation.id}</code>
      {source ? (
        <SourceMeta source={source} onOpenSource={onOpenSource} />
      ) : (
        <p className="source-unavailable">来源元数据不可用；旧记录若无 KB 标识则无法定位原文。</p>
      )}
    </article>
  )
}

function SourceMeta({
  source,
  onOpenSource,
  compact = false,
}: {
  source: EvidenceSource
  onOpenSource: (source: EvidenceSource, location?: SourceLocation) => void
  compact?: boolean
}) {
  const locations = source.locations
  return (
    <div className={compact ? 'source-meta compact' : 'source-meta'}>
      <div className="source-meta-row">
        <span className={`source-badge ${source.kind}`}>{sourceKindLabel()}</span>
        <span className="source-version">{versionLabel(source.version)}</span>
        <span className="source-status">
          {sourceStatusLabel()}
        </span>
      </div>
      <code className="source-path">{source.path}</code>
      {locations.length > 0 ? (
        <div className="source-locations" aria-label="规范原文来源位置">
          {locations.map((location, index) => (
            <button
              className="location-button"
              key={`${location.section ?? 'section'}-${location.table ?? 'table'}-${location.start_line}-${location.end_line}-${index}`}
              type="button"
              onClick={() => onOpenSource(source, location)}
              title="打开规范原文对应行范围"
            >
              {locationLabel(location)}
            </button>
          ))}
        </div>
      ) : (
        <span className="source-unavailable">行号不可用</span>
      )}
    </div>
  )
}

function EvidenceSnippet({ text }: { text: string }) {
  if (!text) return null
  if (text.length <= 320) return <p className="record-snippet">{text}</p>
  return (
    <details className="snippet-details">
      <summary>展开证据片段（{text.length} 字符）</summary>
      <pre className="record-snippet">{text}</pre>
    </details>
  )
}

function ContentViewer({
  target,
  onClose,
}: {
  target: OpenTarget | null
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const closingOnUnmount = useRef(false)
  const [retry, setRetry] = useState(0)
  const requestKey = target ? `${contentRequestUrl(target)}:${retry}` : ''
  const [responseState, setViewerState] = useState<{ requestKey: string } & (
    | { status: 'idle' }
    | { status: 'loading' }
    | { status: 'ready'; data: ContentResponse }
    | { status: 'error'; message: string }
  )>({ requestKey: '', status: 'idle' })
  const viewerState = responseState.requestKey === requestKey
    ? responseState
    : { status: 'loading' as const }

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (target) {
      if (!dialog.open) dialog.showModal()
    } else if (dialog.open) {
      dialog.close()
    }
  }, [target])

  useEffect(() => {
    closingOnUnmount.current = false
    const dialog = dialogRef.current
    return () => {
      closingOnUnmount.current = true
      if (dialog?.open) dialog.close()
    }
  }, [])

  useEffect(() => {
    if (!target) return
    const controller = new AbortController()
    let active = true
    fetch(contentRequestUrl(target), { credentials: 'include', signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response))
        return response.json() as Promise<ContentResponse>
      })
      .then((data) => {
        if (active) setViewerState({ requestKey, status: 'ready', data })
      })
      .catch((requestError) => {
        if (!active || controller.signal.aborted) return
        setViewerState({
          requestKey,
          status: 'error',
          message: requestError instanceof Error ? requestError.message : '无法加载来源',
        })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [target, retry, requestKey])

  function handleClose() {
    if (closingOnUnmount.current) return
    onClose()
  }

  return (
    <dialog
      className="content-dialog"
      ref={dialogRef}
      aria-labelledby="content-viewer-title"
      onClose={handleClose}
    >
      <div className="content-dialog-panel">
        <header className="content-dialog-header">
          <div>
            <p className="eyebrow">EVIDENCE VIEWER</p>
            <h2 id="content-viewer-title">
              {viewerState.status === 'ready' ? viewerState.data.title : '来源详情'}
            </h2>
          </div>
          <form method="dialog">
            <button className="dialog-close" type="submit" aria-label="关闭来源查看器" title="关闭">×</button>
          </form>
        </header>
        <div className="content-dialog-body">
          {viewerState.status === 'loading' && <p className="viewer-state" role="status">正在加载来源…</p>}
          {viewerState.status === 'error' && (
            <div className="viewer-state error" role="alert">
              <p>{viewerState.message}</p>
              <button className="retry-button" type="button" onClick={() => setRetry((value) => value + 1)}>重试</button>
            </div>
          )}
          {viewerState.status === 'ready' && (
            <ContentViewerBody data={viewerState.data} />
          )}
        </div>
      </div>
    </dialog>
  )
}

function ContentViewerBody({
  data,
}: {
  data: ContentResponse
}) {
  const locations = data.locations
  const sourceLines = data.content.split('\n')

  return (
    <>
      <div className="viewer-meta">
        <span className="source-badge spec">规范原文</span>
        <span className="source-version">{versionLabel(data.version)}</span>
        <code className="source-path">{data.path}</code>
      </div>
      {locations.length > 0 && (
        <div className="viewer-locations" aria-label="规范位置">
          {locations.map((location, index) => (
            <span className="location-chip" key={`${location.section ?? 'section'}-${location.start_line}-${location.end_line}-${index}`}>
              {locationLabel(location)}
            </span>
          ))}
        </div>
      )}
      <div className="numbered-source" aria-label="规范原文行">
        {sourceLines.map((line, index) => (
          <div className="numbered-line" key={data.start_line + index}>
            <span className="line-number" aria-hidden="true">{data.start_line + index}</span>
            <span className="line-text">{line || ' '}</span>
          </div>
        ))}
      </div>
    </>
  )
}

export default App
