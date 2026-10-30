// A WebSocket stand-in for tests: records what the client sends and lets the test open, feed and
// drop the connection. src/test/setup.ts installs it globally before every test.
export class FakeWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: FakeWebSocket[] = []

  readonly url: string
  readyState = FakeWebSocket.CONNECTING
  sent: unknown[] = []
  closed = false
  onopen: ((event: unknown) => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: unknown) => void) | null = null
  onerror: ((event: unknown) => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  static latest(): FakeWebSocket {
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    if (!socket) throw new Error('no WebSocket was opened')
    return socket
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data))
  }

  close(): void {
    this.closed = true
    this.readyState = FakeWebSocket.CLOSED
  }

  // Test controls
  open(): void {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.({})
  }

  receive(event: object): void {
    this.onmessage?.({ data: JSON.stringify(event) })
  }

  drop(): void {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({})
  }
}
