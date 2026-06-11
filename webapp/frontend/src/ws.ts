type Handler = (msg: Record<string, unknown>) => void

const SESSION_KEY = 'uchrom_session_id'

function makeSessionId(): string {
  try {
    if (crypto?.randomUUID) return crypto.randomUUID()
  } catch { /* fall through */ }
  return `s_${Date.now()}_${Math.random().toString(36).slice(2)}`
}

class WSClient {
  private socket: WebSocket | null = null
  private handlers = new Map<string, Set<Handler>>()
  private statusHandlers = new Set<(connected: boolean) => void>()
  private delay = 1000
  private readonly maxDelay = 30000
  private readonly baseUrl: string
  private sessionId: string

  constructor() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    this.baseUrl = `${protocol}//${window.location.host}/ws/main`
    // The client owns its session id: generate once, persist, and always
    // reconnect with it so the backend resumes our conversation + view state.
    let sid: string | null = null
    try { sid = localStorage.getItem(SESSION_KEY) } catch { /* ignore */ }
    if (!sid) {
      sid = makeSessionId()
      try { localStorage.setItem(SESSION_KEY, sid) } catch { /* ignore */ }
    }
    this.sessionId = sid
    this.connect()
  }

  private connect() {
    const url = `${this.baseUrl}?session_id=${encodeURIComponent(this.sessionId)}`
    this.socket = new WebSocket(url)
    this.socket.onopen = () => {
      this.delay = 1000
      this.statusHandlers.forEach((h) => h(true))
      // Ask the backend for any view state under this session id. Returns an
      // empty snapshot for a fresh session, or the views to rebuild on resume.
      this.send('view.request_snapshot', {})
    }
    this.socket.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as Record<string, unknown>
        const type = msg.type as string | undefined
        if (!type) return
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
