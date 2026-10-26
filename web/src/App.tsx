import '@xyflow/react/dist/style.css'
import { useEffect } from 'react'
import './App.css'
import { navigate, pageFromPath, PATHS, usePathname } from './lib/navigation'
import { FacilitatorPage } from './pages/FacilitatorPage'
import { JoinPage } from './pages/JoinPage'
import { TeamPage } from './pages/TeamPage'
import { useSessionStore } from './store/sessionStore'

export default function App() {
  const page = pageFromPath(usePathname())
  const team = useSessionStore((s) => s.team)

  // "/" and unknown paths go to the team's workbench or the join page; /team needs a team.
  const redirect = page === null || (page === 'team' && !team) ? (team ? PATHS.team : PATHS.join) : null
  useEffect(() => {
    if (redirect) navigate(redirect, { replace: true })
  }, [redirect])

  if (redirect) return null
  if (page === 'facilitator') return <FacilitatorPage />
  if (page === 'team' && team) return <TeamPage team={team} />
  return <JoinPage />
}
