export const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  capturer: 'Captor',
  viewer: 'Visor',
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role
}
