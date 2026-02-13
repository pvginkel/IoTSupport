// Shared badge helpers for device status display

/** Get rotation state badge styling using semantic and status colors */
export function getRotationStateBadge(state: string): { bgColor: string; textColor: string } {
  switch (state.toUpperCase()) {
    case 'OK':
      return { bgColor: 'bg-green-900/30', textColor: 'text-green-400' }
    case 'QUEUED':
      return { bgColor: 'bg-yellow-900/30', textColor: 'text-yellow-400' }
    case 'PENDING':
      return { bgColor: 'bg-primary/20', textColor: 'text-primary' }
    case 'TIMEOUT':
      return { bgColor: 'bg-red-900/30', textColor: 'text-red-400' }
    default:
      return { bgColor: 'bg-muted', textColor: 'text-muted-foreground' }
  }
}
