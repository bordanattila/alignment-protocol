import type { LobbyState } from './types';
import { RoleBadge } from './RoleBadge';

export function CrisisBriefing({ mission }: { mission: LobbyState }) {
  const crisis = mission.crisis;
  if (!crisis) return null;
  return <section className="crisis-stack" aria-label="Current crisis">
    <div className="panel">
      <p className="eyebrow">Crisis 01 · Public briefing</p>
      <h2>{crisis.title}</h2><p>{crisis.briefing}</p>
      <p className="eyebrow">AI recommendation</p>
      <p className="recommendation">{crisis.choices.find(choice => choice.id === crisis.ai_recommendation_choice_id)?.description}</p>
    </div>
    <div className="panel private-panel">
      <p className="eyebrow">Private intelligence · Your assigned domains</p>
      <h2>Your intelligence</h2>
      <p>Only you receive these intelligence cards. Share what matters with your team.</p>
      {mission.roles.map(role => <article key={role}>
        <h3><RoleBadge role={role} /></h3><p>{mission.private_intelligence[role]}</p>
      </article>)}
    </div>
  </section>;
}
