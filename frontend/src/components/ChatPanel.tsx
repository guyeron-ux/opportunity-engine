import { useState, useRef, useEffect } from 'react'
import type { Opportunity } from '../api'
import { api } from '../api'

interface Props {
  opp: Opportunity
  onOppUpdated: () => void
}

interface Action {
  type: 'rerate' | 'edit'
  data?: Record<string, unknown>
}

interface DisplayMessage {
  role: 'user' | 'assistant'
  content: string
  created_at?: string
  actions?: Action[]
}

function formatTime(iso?: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

export function ChatPanel({ opp, onOppUpdated }: Props) {
  const [open, setOpen] = useState(true)
  const [messages, setMessages] = useState<DisplayMessage[]>(() =>
    (opp.user.chat ?? []).map(m => ({ role: m.role, content: m.content, created_at: m.created_at }))
  )
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [reratingId, setReratingId] = useState<string | null>(null)
  const [reratingPending, setReratingPending] = useState(false)
  const [confirmRerateIdx, setConfirmRerateIdx] = useState<number | null>(null)
  const [applyingEdit, setApplyingEdit] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const accRef = useRef('')
  const lastUpdatedAtRef = useRef(opp.updated_at)

  // Sync messages when opp chat history changes externally
  useEffect(() => {
    setMessages(
      (opp.user.chat ?? []).map(m => ({ role: m.role, content: m.content, created_at: m.created_at }))
    )
  }, [opp.id, opp.user.chat?.length])

  // Clear reratingPending once the opportunity is refreshed with new data
  useEffect(() => {
    if (reratingPending && opp.updated_at !== lastUpdatedAtRef.current) {
      setReratingPending(false)
    }
    lastUpdatedAtRef.current = opp.updated_at
  }, [opp.updated_at, reratingPending])

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, open])

  async function send() {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    setStreaming(true)
    setStreamingContent('')
    accRef.current = ''

    setMessages(prev => [...prev, { role: 'user', content: text }])

    try {
      const actions = await api.chat(opp.id, text, chunk => {
        accRef.current += chunk
        setStreamingContent(accRef.current)
      })

      const finalContent = accRef.current
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: finalContent, actions: actions as Action[] },
      ])
      setStreamingContent('')
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error: ${(e as Error).message}` },
      ])
      setStreamingContent('')
    } finally {
      setStreaming(false)
    }
  }

  async function confirmRerate() {
    if (confirmRerateIdx === null) return
    const idx = confirmRerateIdx
    setConfirmRerateIdx(null)
    setReratingId(String(idx))
    try {
      const chatContext = messages.map(m => ({ role: m.role, content: m.content }))
      await api.rerateWithContext(opp.id, chatContext as import('../api').ChatMessage[])
      setReratingPending(true)
    } finally {
      setReratingId(null)
    }
  }

  async function manualRerate() {
    if (reratingPending) return
    setReratingPending(true)
    try {
      const chatContext = messages.map(m => ({ role: m.role, content: m.content }))
      await api.rerateWithContext(opp.id, chatContext as import('../api').ChatMessage[])
    } catch {
      setReratingPending(false)
    }
  }

  async function handleApplyEdit(msgIndex: number, data: Record<string, unknown>) {
    setApplyingEdit(String(msgIndex))
    try {
      await api.patchOpportunity(opp.id, data as { title?: string; notes?: string })
      onOppUpdated()
    } finally {
      setApplyingEdit(null)
    }
  }

  async function handleClearChat() {
    await api.clearChat(opp.id)
    setMessages([])
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={() => setOpen(v => !v)}
          className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 uppercase tracking-wider hover:text-gray-300 transition-colors"
        >
          <span>{open ? '▾' : '▸'}</span>
          <span>Chat with Analyst</span>
        </button>
        {open && messages.length > 0 && (
          <div className="flex items-center gap-3">
            <button
              onClick={manualRerate}
              disabled={reratingPending || streaming}
              className={`text-xs transition-colors disabled:opacity-50 ${
                reratingPending
                  ? 'text-violet-400 animate-pulse cursor-default'
                  : 'text-violet-500 hover:text-violet-300'
              }`}
              title="Rescore this opportunity using the full conversation as context"
            >
              {reratingPending ? '↻ Rescoring…' : '↻ Rerate with chat'}
            </button>
            <button
              onClick={handleClearChat}
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {open && (
        <div className="flex flex-col gap-2">
          {/* Message list */}
          <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
            {messages.length === 0 && !streaming && (
              <p className="text-xs text-gray-600 italic py-2">
                Ask anything about this opportunity…
              </p>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                <div
                  className={`group relative max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-violet-900/60 text-violet-100'
                      : 'bg-gray-800 text-gray-200'
                  }`}
                >
                  <span className="whitespace-pre-wrap">{msg.content}</span>
                  {msg.created_at && (
                    <span className="absolute -bottom-4 right-1 text-xs text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                      {formatTime(msg.created_at)}
                    </span>
                  )}
                </div>

                {/* Action buttons */}
                {msg.role === 'assistant' && msg.actions && msg.actions.length > 0 && (
                  <div className="flex flex-col gap-1.5 mt-1.5">
                    <div className="flex gap-2 flex-wrap">
                      {msg.actions.map((action, ai) =>
                        action.type === 'rerate' ? (
                          reratingId === String(i) ? (
                            <span key={ai} className="text-xs text-gray-500 px-2.5 py-1">↻ Rerating…</span>
                          ) : (
                            <button
                              key={ai}
                              onClick={() => setConfirmRerateIdx(i)}
                              disabled={reratingId !== null || confirmRerateIdx !== null}
                              className="text-xs bg-gray-700 hover:bg-violet-800 text-gray-300 hover:text-white px-2.5 py-1 rounded-lg transition-colors disabled:opacity-50"
                            >
                              ↻ Rerate with these insights
                            </button>
                          )
                        ) : action.type === 'edit' && action.data ? (
                          <button
                            key={ai}
                            onClick={() => handleApplyEdit(i, action.data!)}
                            disabled={applyingEdit !== null}
                            className="text-xs bg-gray-700 hover:bg-cyan-800 text-gray-300 hover:text-white px-2.5 py-1 rounded-lg transition-colors disabled:opacity-50"
                          >
                            {applyingEdit === String(i) ? 'Applying…' : '✎ Apply suggested edit'}
                          </button>
                        ) : null
                      )}
                    </div>
                    {/* Inline confirmation dialog */}
                    {confirmRerateIdx === i && (
                      <div className="bg-gray-900 border border-violet-700/50 rounded-lg px-3 py-2 text-xs text-gray-300 flex flex-col gap-1.5">
                        <p>This will rescore using insights from this conversation. Scores may change.</p>
                        <div className="flex gap-2">
                          <button
                            onClick={() => confirmRerate()}
                            className="bg-violet-700 hover:bg-violet-600 text-white px-2.5 py-1 rounded-md transition-colors"
                          >
                            Confirm rerate
                          </button>
                          <button
                            onClick={() => setConfirmRerateIdx(null)}
                            className="text-gray-500 hover:text-gray-300 px-2.5 py-1 transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* Streaming indicator */}
            {streaming && (
              <div className="flex flex-col items-start">
                <div className="max-w-[85%] rounded-xl px-3 py-2 bg-gray-800 text-sm text-gray-200 leading-relaxed">
                  {streamingContent ? (
                    <span className="whitespace-pre-wrap">{streamingContent}</span>
                  ) : (
                    <span className="text-gray-500 animate-pulse">● ● ●</span>
                  )}
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Rerate-pending indicator */}
          {reratingPending && (
            <div className="flex items-center gap-2 text-xs text-violet-400 animate-pulse px-1 py-1">
              <span className="inline-block animate-spin">↻</span>
              Rescoring with conversation insights — scores will update when complete…
            </div>
          )}

          {/* Input */}
          <div className="flex gap-2 mt-1">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={2}
              disabled={streaming}
              placeholder="Ask anything… (Enter to send, Shift+Enter for newline)"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none focus:border-violet-500 disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={streaming || !input.trim()}
              className="self-end text-xs bg-violet-700 hover:bg-violet-600 disabled:opacity-40 text-white px-3 py-2 rounded-lg transition-colors whitespace-nowrap"
            >
              {streaming ? '…' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
