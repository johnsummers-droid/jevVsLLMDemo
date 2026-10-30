// The live event stream (plan1.txt T22, decisions Q2-Q4, Q9). One reconnecting WebSocket per
// signed-in role. It authenticates with its first message (never a token in the URL), pings every
// PING_MS and treats SILENCE_MS without any message as a dead connection: Render's proxy swallows
// close frames, so a server restart can leave a socket open with nothing behind it. For the same
// reason the server announces every close with a `closing` event; the client closes on that.
import type { ServerEvent } from '../types'

export const PING_MS = 25_000
export const SILENCE_MS = 40_000
export const CHECK_MS = 5000
export const RECONNECT_BASE_MS = 1000
export const RECONNECT_MAX_MS = 15_000

/** Close codes after which reconnecting cannot help: the token is bad or was replaced. */
export const AUTH_CLOSE_CODES: ReadonlySet<number> = new Set([4401, 4403])

export type LiveStatus = 'connecting' | 'live' | 'offline'

export interface LiveOptions {
  token: string
  onEvent: (event: ServerEvent) => void
  onStatus?: (status: LiveStatus) => void
  /** The server refused the token (4401) or another sign-in replaced it (4403). No reconnect. */
  onAuthRejected?: (code: number) => void
  url?: string
  WebSocketImpl?: typeof WebSocket
}

/** Q9: derived from VITE_API_BASE_URL (https -> wss); same origin, through the Vite proxy, when unset. */
export function liveUrl(
  baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? '',
  location: Pick<Location, 'protocol' | 'host'> = window.location,
): string {
  if (baseUrl) return `${baseUrl.replace(/\/+$/, '').replace(/^http/, 'ws')}/api/ws`
  return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws`
}

/** Opens the stream and keeps it open until the returned function is called. */
export function openLive(options: LiveOptions): () => void {
  const { token, onEvent, onStatus = () => {}, onAuthRejected = () => {} } = options
  const url = options.url ?? liveUrl()
  const Impl = options.WebSocketImpl ?? WebSocket
  let socket: WebSocket | null = null
  let stopped = false
  let delay = 0
  let lastHeard = 0
  let lastPing = 0
  let heartbeat: ReturnType<typeof setInterval> | undefined
  let retry: ReturnType<typeof setTimeout> | undefined

  const drop = () => {
    clearInterval(heartbeat)
    heartbeat = undefined
    if (!socket) return
    const old = socket
    socket = null
    old.onopen = old.onmessage = old.onclose = old.onerror = null
    try {
      old.close()
    } catch {
      // already closed
    }
  }

  const reconnect = () => {
    drop()
    if (stopped) return
    onStatus('offline')
    delay = Math.min(Math.max(delay * 2, RECONNECT_BASE_MS), RECONNECT_MAX_MS)
    retry = setTimeout(connect, delay)
  }

  const send = (message: object) => {
    if (socket?.readyState === Impl.OPEN) socket.send(JSON.stringify(message))
  }

  function connect() {
    retry = undefined
    if (stopped) return
    onStatus('connecting')
    const ws = new Impl(url)
    socket = ws
    ws.onopen = () => {
      lastHeard = lastPing = Date.now()
      send({ type: 'auth', token })
      heartbeat = setInterval(() => {
        const now = Date.now()
        if (now - lastHeard > SILENCE_MS) return reconnect()
        if (now - lastPing >= PING_MS) {
          lastPing = now
          send({ type: 'ping' })
        }
      }, CHECK_MS)
    }
    ws.onmessage = (message: MessageEvent) => {
      lastHeard = Date.now()
      let event: ServerEvent
      try {
        event = JSON.parse(String(message.data)) as ServerEvent
      } catch {
        return
      }
      if (event.type === 'closing') {
        if (AUTH_CLOSE_CODES.has(event.code)) {
          stopped = true
          drop()
          onStatus('offline')
          onAuthRejected(event.code)
        } else {
          reconnect()
        }
        return
      }
      if (event.type === 'pong') return
      if (event.type === 'state_sync') {
        delay = 0 // a working connection: the next drop retries quickly again
        onStatus('live')
      }
      onEvent(event)
    }
    ws.onclose = reconnect
    ws.onerror = reconnect
  }

  connect()
  return () => {
    stopped = true
    clearTimeout(retry)
    drop()
    onStatus('offline')
  }
}
