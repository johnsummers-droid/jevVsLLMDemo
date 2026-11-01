import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HelpPanel } from '../help/HelpPanel'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { useHelpStore } from '../store/helpStore'
import { usePackStore } from '../store/packStore'
import { EMPTY_RUN, useRunStore } from '../store/runStore'
import { useSessionStore } from '../store/sessionStore'
import { useValidationStore } from '../store/validationStore'
import { catalogByType, catalogNodes } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import type { RunMetrics, RunSummary, ValidationReport } from '../types'
import { MetricsBar } from './MetricsBar'
import { NodeStatsBadge } from './NodeStatsBadge'
import { RunControls } from './RunControls'

const run = (status: RunSummary['status'], mode: 'practice' | 'official' = 'practice'): RunSummary => ({
  runId: 'run-1',
  teamId: 't1',
  status,
  config: { mode, packId: mode, seed: 1 },
  graphVersion: 2,
})

const metrics = (over: Partial<RunMetrics> = {}): RunMetrics => ({
  total: 15,
  completed: 10,
  automationRate: 0.6,
  escalationRate: 0.2,
  unsafeReleaseRate: 0,
  droppedRate: 0,
  p50LatencyMs: 400,
  p95LatencyMs: 700,
  costPer1KUsd: 900,
  decisionQuality: 0.9,
  score: 87.4,
  ...over,
})

const errorReport: ValidationReport = {
  ok: false,
  issues: [{ code: 'CYCLE', severity: 'error', message: 'cycle' }],
}

beforeEach(() => {
  useRunStore.setState({ ...EMPTY_RUN, connection: 'live', leaderboard: null })
  useGraphStore.setState({ locked: false })
  useValidationStore.setState({ report: { ok: true, issues: [] } })
  useSessionStore.setState({ team: { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'tok' } })
  usePackStore.setState({ packs: {} })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useSessionStore.setState({ team: null, facilitator: null })
})

describe('RunControls', () => {
  const button = () => screen.getByRole('button', { name: /Run traffic|Starting/ }) as HTMLButtonElement

  it('starts a run while the help panel is open', async () => {
    useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
    useHelpStore.getState().open('llm_answer_generator')
    const fetchMock = mockApi({ 'POST /api/teams/t1/runs': { status: 201, body: { ...run('running'), startedAt: 'x' } } })
    render(
      <>
        <RunControls teamId="t1" />
        <HelpPanel />
      </>,
    )
    expect(screen.getByRole('complementary', { name: 'Help: LLM answer generator' })).toBeTruthy()
    fireEvent.click(button())
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    useHelpStore.getState().close()
  })

  it('starts a practice run', async () => {
    const fetchMock = mockApi({ 'POST /api/teams/t1/runs': { status: 201, body: { ...run('running'), startedAt: 'x' } } })
    render(<RunControls teamId="t1" />)
    expect(button().disabled).toBe(false)
    fireEvent.click(button())
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/teams/t1/runs')
  })

  it.each([
    ['locked', () => useGraphStore.setState({ locked: true }), 'Graphs are locked.'],
    ['not live', () => useRunStore.setState({ connection: 'connecting' }), 'Connecting to live updates…'],
    ['errors', () => useValidationStore.setState({ report: errorReport }), 'Fix 1 error first (see Pipeline check).'],
  ])('is disabled, with the reason shown, when %s', (_, arrange, reason) => {
    arrange()
    render(<RunControls teamId="t1" />)
    expect(button().disabled).toBe(true)
    expect(screen.getByText(reason)).toBeTruthy()
  })

  it('reports a graph the server refuses (422)', async () => {
    mockApi({ 'POST /api/teams/t1/runs': { status: 422, body: errorReport } })
    render(<RunControls teamId="t1" />)
    fireEvent.click(button())
    expect((await screen.findByRole('alert')).textContent).toBe('The saved graph has 1 error; fix them first.')
  })

  it('shows Stop and the progress while the run plays, and stops it', async () => {
    useRunStore.setState({ run: run('running'), requestsDone: 4, metrics: metrics({ completed: 4 }) })
    const fetchMock = mockApi({ 'POST /api/runs/run-1/stop': { body: { ...run('stopped'), startedAt: 'x' } } })
    render(<RunControls teamId="t1" />)
    expect(screen.getByRole('status').textContent).toBe('Running · 4 / 15 requests')
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/runs/run-1/stop')
  })

  it('says the run is preparing, and it can be stopped', async () => {
    const fetchMock = mockApi({ 'POST /api/runs/run-1/stop': { body: {} } })
    useRunStore.setState({ run: run('pending'), connection: 'live' })
    render(<RunControls teamId="t1" />)
    expect(screen.getByRole('status').textContent).toContain('Preparing…')
    expect(screen.getByRole('status').textContent).not.toContain('requests')
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url) === '/api/runs/run-1/stop')).toBe(true))
  })

  it("shows a run's warnings", () => {
    useRunStore.setState({ run: { ...run('running'), warnings: ['Some answers are simulated.'] }, connection: 'live' })
    render(<RunControls teamId="t1" />)
    expect(screen.getByRole('alert').textContent).toBe('Some answers are simulated.')
  })

  it('offers no Stop for an official run', () => {
    useRunStore.setState({ run: run('running', 'official') })
    render(<RunControls teamId="t1" />)
    expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull()
    expect(screen.getByRole('status').textContent).toContain('Official run')
  })
})

describe('MetricsBar', () => {
  const tile = (label: string) => screen.getByRole('group', { name: label })

  beforeEach(() => {
    mockApi({
      'GET /api/packs/practice': {
        body: { id: 'practice', version: 1, ticketCount: 15, categoryCounts: {}, scoring: { latencyBudgetMs: 800, costBudgetPer1KUsd: 1000 } },
      },
    })
  })

  it('shows nothing without a run', () => {
    const { container } = render(<MetricsBar />)
    expect(container.textContent).toBe('')
  })

  it('colours each metric against the pack targets', async () => {
    useRunStore.setState({ run: run('running'), metrics: metrics({ p95LatencyMs: 950, unsafeReleaseRate: 0.1 }) })
    render(<MetricsBar />)
    await screen.findByText('target ≤ 800 ms')
    expect(tile('p95 latency').className).toContain('metric--fail')
    expect(tile('Cost per 1,000').className).toContain('metric--pass')
    expect(tile('Unsafe releases').className).toContain('metric--fail')
    expect(tile('Automation').className).toContain('metric--neutral')
    expect(tile('p95 latency').textContent).toContain('950 ms')
    expect(screen.queryByRole('group', { name: 'Score' })).toBeNull() // still running
  })

  it('renders a run that has no metrics yet (just started) once the targets are loaded', async () => {
    useRunStore.setState({ run: run('running'), metrics: null })
    render(<MetricsBar />)
    await screen.findByText('target ≤ 800 ms')
    for (const label of ['p95 latency', 'Cost per 1,000', 'Automation', 'Unsafe releases']) {
      expect(tile(label).className).toContain('metric--neutral')
      expect(tile(label).textContent).toContain('—')
    }
  })

  it('stays neutral until requests have completed, and shows the score once finished', async () => {
    useRunStore.setState({ run: run('running'), metrics: metrics({ completed: 0 }) })
    const { rerender } = render(<MetricsBar />)
    await screen.findByText('target ≤ 800 ms')
    expect(tile('p95 latency').className).toContain('metric--neutral')
    expect(tile('p95 latency').textContent).toContain('—')
    useRunStore.setState({ run: run('completed'), metrics: metrics() })
    rerender(<MetricsBar />)
    expect(tile('Score').textContent).toContain('87')
  })
})

describe('NodeStatsBadge', () => {
  it('shows nothing until the team has a run', () => {
    const { container } = render(<NodeStatsBadge nodeId="router" />)
    expect(container.textContent).toBe('')
  })

  it("shows the node's numbers and what it did", () => {
    useRunStore.setState({
      run: run('running'),
      nodeStats: {
        router: {
          nodeId: 'router',
          requests: 12,
          skipped: 3,
          errors: 1,
          escalations: 2,
          avgLatencyMs: 41.6,
          totalCostUsd: 0.0123,
          tokensOut: 0,
          decisions: { 'route.billing': 7, 'route.bug_report': 4, 'route.feature_request': 1, 'route.low_confidence': 0 },
        },
      },
    })
    render(<NodeStatsBadge nodeId="router" />)
    const text = screen.getByLabelText('Run statistics').textContent
    for (const part of ['12 req', '42 ms', '$0.01', 'billing 7', 'bug_report 4', 'feature_request 1', '2 escalated', '1 failed', '3 skipped']) {
      expect(text).toContain(part)
    }
    expect(text).not.toContain('low_confidence') // top three decisions only
  })

  it("shows a provider's safety blocks as blocked, not failed", () => {
    useRunStore.setState({
      run: run('completed'),
      nodeStats: {
        llm: {
          nodeId: 'llm',
          requests: 3,
          skipped: 0,
          errors: 0,
          providerBlocks: 2,
          escalations: 0,
          avgLatencyMs: 5000,
          totalCostUsd: 0,
          tokensOut: 0,
          decisions: {},
        },
      },
    })
    render(<NodeStatsBadge nodeId="llm" />)
    const text = screen.getByLabelText('Run statistics').textContent
    expect(text).toContain('2 blocked')
    expect(text).not.toContain('failed')
  })

  it('says so when a node has had no traffic yet', () => {
    useRunStore.setState({ run: run('running'), nodeStats: {} })
    render(<NodeStatsBadge nodeId="llm" />)
    expect(screen.getByLabelText('Run statistics').textContent).toBe('no traffic yet')
  })
})
