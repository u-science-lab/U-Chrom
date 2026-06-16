import { useAppStore } from './store'

type Handler = (msg: Record<string, unknown>) => void

const SESSION_KEY = 'uchrom_session_id'
const CONVERSATION_KEY = 'uchrom_conversation_id'

function makeSessionId(): string {
  try {
    if (crypto?.randomUUID) return crypto.randomUUID()
  } catch { /* fall through */ }
  return `s_${Date.now()}_${Math.random().toString(36).slice(2)}`
}

function ensureSessionId(): string {
  let sid: string | null = null
  try { sid = localStorage.getItem(SESSION_KEY) } catch { /* ignore */ }
  if (!sid) {
    sid = makeSessionId()
    try { localStorage.setItem(SESSION_KEY, sid) } catch { /* ignore */ }
  }
  return sid
}

export function getSessionId(): string {
  return ensureSessionId()
}

export function sessionApiUrl(path: string): string {
  const url = new URL(path, window.location.origin)
  url.searchParams.set('session_id', getSessionId())
  try {
    const cid = localStorage.getItem(CONVERSATION_KEY)
    if (cid) url.searchParams.set('conversation_id', cid)
  } catch { /* ignore */ }
  return `${url.pathname}${url.search}`
}

class WSClient {
  private socket: WebSocket | null = null
  private handlers = new Map<string, Set<Handler>>()
  private statusHandlers = new Set<(connected: boolean) => void>()
  private delay = 1000
  private readonly maxDelay = 30000
  private readonly baseUrl: string
  private sessionId: string
  private conversationId: string | null = null

  constructor() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    this.baseUrl = `${protocol}//${window.location.host}/ws/main`
    // The client owns its session id: generate once, persist, and always
    // reconnect with it so the backend resumes our conversation + view state.
    this.sessionId = ensureSessionId()
    try { this.conversationId = localStorage.getItem(CONVERSATION_KEY) } catch { /* ignore */ }
    if (!this.conversationId) this.conversationId = this.sessionId
    this.connect()
  }

  private connect() {
    const params = new URLSearchParams({ session_id: this.sessionId })
    if (this.conversationId) params.set('conversation_id', this.conversationId)
    const url = `${this.baseUrl}?${params.toString()}`
    this.socket = new WebSocket(url)
    this.socket.onopen = () => {
      this.delay = 1000
      this.statusHandlers.forEach((h) => h(true))
      this.send('conversation.request_snapshot', {})
      this.send('conversation.list', {})
      // Ask the backend for any view state under this session id. Returns an
      // empty snapshot for a fresh session, or the views to rebuild on resume.
      this.send('view.request_snapshot', {})
    }
    this.socket.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as Record<string, unknown>
        const type = msg.type as string | undefined
        if (!type) return
        if (type === 'conversation.snapshot') {
          const id = (msg.conversation as { id?: string } | undefined)?.id
          if (id) {
            this.conversationId = id
            try { localStorage.setItem(CONVERSATION_KEY, id) } catch { /* ignore */ }
          }
        }
        if (type === 'a2ui.protocol') {
          const protocolVersion = String(msg.protocol_version ?? msg.version ?? '')
          const capabilities = Array.isArray(msg.capabilities) ? msg.capabilities.map(String) : []
          const tools = Array.isArray(msg.tools) ? msg.tools.map(String) : []
          useAppStore.getState().setProtocol({
            protocol_version: protocolVersion,
            capabilities,
            tools,
          })
          this.send('protocol.hello', {
            protocol_version: protocolVersion,
            capabilities: [
              'json_patch',
              'view_snapshot',
              'interaction_wait',
              'snapshot_capture',
              'component_tree',
              'component_actions',
              'analysis_projection',
              'session_scoped_rest',
              'conversation_resume',
            ],
          })
        }
        // Incoming server events are flat: { type, ...fields }.
        // Dispatch the whole message object to handlers registered for `type`.
        this.handlers.get(type)?.forEach((h) => h(msg))
      } catch { /* ignore malformed */ }
    }
    this.socket.onclose = () => {
      this.statusHandlers.forEach((h) => h(false))
      setTimeout(() => this.connect(), this.delay)
      this.delay = Math.min(this.delay * 2, this.maxDelay)
    }
    this.socket.onerror = () => {
      this.statusHandlers.forEach((h) => h(false))
    }
  }

  get connected() {
    return this.socket?.readyState === WebSocket.OPEN
  }

  /** Send a command. Backend handlers read `payload`, so commands are wrapped. */
  send(type: string, payload: unknown) {
    if (type === 'conversation.load') {
      const id = (payload as { conversation_id?: string })?.conversation_id
      if (id) {
        this.conversationId = id
        try { localStorage.setItem(CONVERSATION_KEY, id) } catch { /* ignore */ }
      }
    }
    if (this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(JSON.stringify({ type, payload }))
  }

  /** Subscribe to a server message `type`. Returns an unsubscribe fn. */
  onMessage(type: string, handler: Handler) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set())
    this.handlers.get(type)!.add(handler)
    return () => this.handlers.get(type)?.delete(handler)
  }

  /** Subscribe to connection status changes. Returns an unsubscribe fn. */
  onStatus(handler: (connected: boolean) => void) {
    this.statusHandlers.add(handler)
    // Emit current status immediately
    handler(this.connected)
    return () => this.statusHandlers.delete(handler)
  }
}

export const ws = new WSClient()
