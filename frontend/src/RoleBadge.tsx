import type { Role } from './types';

export function RoleBadge({ role }: { role: Role }) {
  return <span className={`role-badge role-${role}`}>
    {role.charAt(0).toUpperCase() + role.slice(1)}
  </span>;
}
