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
    expect(body[0]).toBe('1Strong+82640 ms$91273%0%')
    expect(body[1]).toContain('Weak')
    expect(body[2]).toBe('–Laterunning…') // no metrics yet: one status cell
    expect(body[3]).toContain('graph has errors')
    expect(body[1]).toContain('−12')
    expect(screen.getByText('10%').className).toContain('leaderboard__unsafe')
    expect(screen.getByText('−12').className).toContain('leaderboard__score--negative')
    expect(screen.getByText('Strong').closest('tr')!.className).toContain('leaderboard__row--first')
  })

  it.each([
    [-0.127, '−0.13', true],
    [0.5, '+0.50', false],
    [-0.001, '0.00', false],
    [0, '0.00', false],
    [-0.999, '−1.00', true],
    [1, '+1', false],
    [-40.9, '−41', true],
  ])('shows a score of %s as %s', (score, shown, negative) => {
    const row: LeaderboardRow = { teamId: 'a', teamName: 'A', runId: '1', status: 'completed', rank: 1, metrics: metrics(score) }
    render(<Leaderboard rows={[row]} />)
    expect(screen.getByText(shown).className.includes('leaderboard__score--negative')).toBe(negative)
  })

  it('says when there is no official run yet', () => {
    render(<Leaderboard rows={[]} />)
    expect(screen.getByText('No official run yet.')).toBeTruthy()
  })
})
