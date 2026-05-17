type Handler = (payload: unknown) => void

class WSClient {
  private socket: WebSocket | null = null
  private handlers = new Map<string, Set<Handler>>()
  private delay = 1000
  private readonly maxDelay = 30000
  private readonly url = 'ws://localhost:8000/ws/main'

  constructor() { this.connect() }

  private connect() {
    this.socket = new WebSocket(this.url)
    this.socket.onopen = () => { this.delay = 1000 }
    this.socket.onmessage = (e) => {
      try {
        const { type, payload } = JSON.parse(e.data)
        this.handlers.get(type)?.forEach((h) => h(payload))
      } catch { /* ignore malformed */ }
    }
    this.socket.onclose = () => {
      setTimeout(() => this.connect(), this.delay)
      this.delay = Math.min(this.delay * 2, this.maxDelay)
    }
  }

  send(type: string, payload: unknown) {
    if (this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(JSON.stringify({ type, payload }))
  }

  onMessage(type: string, handler: Handler) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set())
    this.handlers.get(type)!.add(handler)
    return () => this.handlers.get(type)?.delete(handler)
  }
}

export const ws = new WSClient()
