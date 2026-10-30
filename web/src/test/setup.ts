// Runs before every test file (vite.config.ts test.setupFiles).
import { beforeEach, vi } from 'vitest'
import { FakeWebSocket } from './fakeSocket'

// No test opens a real socket; pages that go live get the fake (re-stubbed after unstubAllGlobals).
beforeEach(() => {
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
})
