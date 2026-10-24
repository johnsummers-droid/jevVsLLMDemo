import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import catalogFixture from '../../../shared/fixtures/catalog.json'
import { useCatalogStore } from './catalogStore'

const initialState = useCatalogStore.getState()

beforeEach(() => {
  useCatalogStore.setState(initialState, true)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('catalogStore', () => {
  it('loads the catalog once, even when asked twice at the same time', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(catalogFixture)))
    vi.stubGlobal('fetch', fetchMock)

    const { load } = useCatalogStore.getState()
    await Promise.all([load(), load()])
    await load()

    const state = useCatalogStore.getState()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(state.status).toBe('ready')
    expect(state.nodes).toHaveLength(catalogFixture.nodes.length)
    expect(Object.keys(state.byType)).toEqual(catalogFixture.nodes.map((n) => n.type))
    expect(state.byType.jev_intent_router.category).toBe('jev')
  })

  it('records an error and retries on the next load', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('down', { status: 503 })))
    await useCatalogStore.getState().load()
    expect(useCatalogStore.getState()).toMatchObject({ status: 'error', nodes: [] })
    expect(useCatalogStore.getState().error).toMatch(/503/)

    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(catalogFixture))))
    await useCatalogStore.getState().load()
    expect(useCatalogStore.getState()).toMatchObject({ status: 'ready', error: null })
  })
})
