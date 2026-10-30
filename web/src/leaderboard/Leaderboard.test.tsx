import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { LeaderboardRow, RunMetrics } from '../types'
import { Leaderboard } from './Leaderboard'

const metrics = (score: number, unsafe = 0): RunMetrics => ({
  total: 30, completed: 30, automationRate: 0.73, escalationRate: 0.2, unsafeReleaseRate: unsafe, droppedRate: 0,
  p50LatencyMs: 300, p95LatencyMs: 640, costPer1KUsd: 912.4, decisionQuality: 0.9, score,
})

afterEach(cleanup)

describe('Leaderboard', () => {
  it('lists teams in rank order with their numbers', () => {
    const rows: LeaderboardRow[] = [
      { teamId: 's', teamName: 'Strong', runId: '1', status: 'completed', rank: 1, metrics: metrics(81.6) },
      { teamId: 'w', teamName: 'Weak', runId: '2', status: 'completed', rank: 2, metrics: metrics(-12, 0.1) },
      { teamId: 'r', teamName: 'Late', runId: '3', status: 'running', rank: 3 },
      { teamId: 'f', teamName: 'Broken', runId: '4', status: 'failed', rank: 4 },
    ]
    render(<Leaderboard rows={rows} />)
    const body = screen.getAllByRole('row').slice(1).map((r) => r.textContent)
    expect(body[0]).toBe('1Strong82640 ms$91273%0%')
    expect(body[1]).toContain('Weak')
    expect(body[2]).toBe('–Late running…—————') // no metrics yet: five dashes
    expect(body[3]).toContain('graph has errors')
    expect(screen.getByText('10%').className).toBe('leaderboard__unsafe')
  })

  it('says when there is no official run yet', () => {
    render(<Leaderboard rows={[]} />)
    expect(screen.getByText('No official run yet.')).toBeTruthy()
  })
})
