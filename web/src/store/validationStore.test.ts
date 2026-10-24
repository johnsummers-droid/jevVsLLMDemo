import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { catalogByType, catalogNodes, defaultGraphFixture } from '../test/fixtures'
import type { ValidationReport } from '../types'
import { useCatalogStore } from './catalogStore'
import { useGraphStore } from './graphStore'
import { startAutoValidation, useValidationStore, VALIDATE_DEBOUNCE_MS } from './validationStore'

const initialGraph = useGraphStore.getState()
const initialValidation = useValidationStore.getState()
const report: ValidationReport = {
  ok: true,
  issues: [{ code: 'NO_HUMAN_FALLBACK', severity: 'warning', message: 'm', nodeId: null, edgeId: null, portId: null }],
}

let stop: () => void = () => {}
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.useFakeTimers()
  useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
  useGraphStore.setState(initialGraph, true)
  useValidationStore.setState(initialValidation, true)
  fetchMock = vi.fn(async () => new Response(JSON.stringify(report)))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  stop()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const posted = (call: number) => JSON.parse(fetchMock.mock.calls[call][1].body)

describe('auto validation', () => {
  it('waits for the graph, then validates once after the debounce', async () => {
    stop = startAutoValidation()
    await vi.advanceTimersByTimeAsync(VALIDATE_DEBOUNCE_MS * 2)
    expect(fetchMock).not.toHaveBeenCalled()

    useGraphStore.getState().setGraph(defaultGraphFixture)
    expect(useValidationStore.getState().status).toBe('pending')
    await vi.advanceTimersByTimeAsync(VALIDATE_DEBOUNCE_MS - 1)
    expect(fetchMock).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/graphs/validate')
    expect(posted(0)).toEqual(defaultGraphFixture)
    expect(useValidationStore.getState()).toMatchObject({ status: 'done', report })
    expect(useValidationStore.getState().index.graph).toEqual(report.issues)
  })

  it('collapses a burst of changes into one request with the latest graph', async () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    stop = startAutoValidation()
    await vi.advanceTimersByTimeAsync(VALIDATE_DEBOUNCE_MS)
    fetchMock.mockClear()

    for (const threshold of [0.6, 0.7, 0.8]) {
      useGraphStore.getState().updateParam('router', 'threshold', threshold)
      await vi.advanceTimersByTimeAsync(100)
    }
    await vi.advanceTimersByTimeAsync(VALIDATE_DEBOUNCE_MS)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(posted(0).nodes.find((n: { id: string }) => n.id === 'router').params.threshold).toBe(0.8)
  })

  it('does not revalidate when a node only moves or is selected', async () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    stop = startAutoValidation()
    await vi.advanceTimersByTimeAsync(VALIDATE_DEBOUNCE_MS)
    fetchMock.mockClear()

    useGraphStore.getState().moveNode('router', { x: 999, y: 999 })
    useGraphStore.getState().onNodesChange([{ type: 'select', id: 'router', selected: true }])
    await vi.advanceTimersByTimeAsync(VALIDATE_DEBOUNCE_MS * 2)
    expect(fetchMock).not.toHaveBeenCalled()

    useGraphStore.getState().deleteEdge(defaultGraphFixture.edges[0].id)
    await vi.advanceTimersByTimeAsync(VALIDATE_DEBOUNCE_MS)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('stops when asked', async () => {
    stop = startAutoValidation()
    stop()
    useGraphStore.getState().setGraph(defaultGraphFixture)
    await vi.advanceTimersByTimeAsync(VALIDATE_DEBOUNCE_MS * 2)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('validate', () => {
  it('ignores a response that arrives after a newer request started', async () => {
    vi.useRealTimers()
    let releaseFirst: (r: Response) => void = () => {}
    const stale: ValidationReport = { ok: false, issues: [] }
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => (releaseFirst = resolve)))
    const first = useValidationStore.getState().validate(defaultGraphFixture)
    await useValidationStore.getState().validate(defaultGraphFixture)
    releaseFirst(new Response(JSON.stringify(stale)))
    await first
    expect(useValidationStore.getState().report).toEqual(report)
  })

  it('records a failure', async () => {
    fetchMock.mockImplementationOnce(async () => new Response('', { status: 502 }))
    await useValidationStore.getState().validate(defaultGraphFixture)
    expect(useValidationStore.getState()).toMatchObject({ status: 'error' })
    expect(useValidationStore.getState().error).toMatch(/502/)
  })
})
