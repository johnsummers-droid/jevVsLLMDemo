// /join: a team enters the session code from the screen and its team name. Joining with a name
// that already exists rejoins that team (decision P3). ?code=ABC123 prefills the code.
import { type FormEvent, useState } from 'react'
import { ApiError, api } from '../api/client'
import { navigate, PATHS } from '../lib/navigation'
import { useSessionStore } from '../store/sessionStore'
import { Logo } from '../components/Logo'
import { Link } from './Link'

const MAX_NAME = 30

function joinError(error: unknown, sessionCode: string): string {
  if (!(error instanceof ApiError)) return 'Could not reach the server. Check your connection and try again.'
  switch (error.status) {
    case 404:
      return `There is no session with code ${sessionCode}. Check the code on the screen.`
    case 409:
      return 'This session is full. Ask the facilitator.'
    case 422:
      return `Team names are 1–${MAX_NAME} characters.`
    case 503:
      return 'The server is not set up for workshops yet. Ask the facilitator.'
    default:
      return `Joining failed (${error.status}). Try again.`
  }
}

export function JoinPage() {
  const team = useSessionStore((s) => s.team)
  const setTeam = useSessionStore((s) => s.setTeam)
  const [sessionCode, setSessionCode] = useState(
    () => new URLSearchParams(window.location.search).get('code')?.toUpperCase() ?? '',
  )
  const [teamName, setTeamName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const code = sessionCode.trim().toUpperCase()
  const name = teamName.trim()
  const canSubmit = code !== '' && name !== '' && name.length <= MAX_NAME && !busy

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const joined = await api.joinTeam(code, name)
      setTeam({ sessionCode: code, teamId: joined.teamId, teamName: joined.teamName, token: joined.token })
      navigate(PATHS.team)
    } catch (e) {
      setError(joinError(e, code))
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <Logo className="page__logo" />
      <form className="page__card" onSubmit={submit}>
        <h1>Join the workshop</h1>
        {team && (
          <p className="page__hint">
            You are signed in as <strong>{team.teamName}</strong> (session {team.sessionCode}).{' '}
            <Link to={PATHS.team}>Back to your pipeline</Link>
          </p>
        )}
        <label className="field">
          <span>Session code</span>
          <input
            className="field__input field__input--code"
            value={sessionCode}
            onChange={(e) => setSessionCode(e.target.value.toUpperCase())}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={6}
            placeholder="ABC234"
          />
        </label>
        <label className="field">
          <span>Team name</span>
          <input
            className="field__input"
            value={teamName}
            onChange={(e) => setTeamName(e.target.value)}
            maxLength={MAX_NAME}
            placeholder="e.g. Red Team"
          />
          <small className="page__hint">Lost your browser? Join again with the same name to get back in.</small>
        </label>
        {error && (
          <p className="page__error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="button button--primary" disabled={!canSubmit}>
          {busy ? 'Joining…' : 'Join'}
        </button>
        <p className="page__footer">
          Running the workshop?{' '}
          <Link to={PATHS.facilitator}>Facilitator page</Link>
        </p>
      </form>
    </div>
  )
}
