/**
 * StageIndicator component.
 * Shows the deployment stage (LOCAL-DEV, DEV, UAT, ...) in the top bar.
 * Hidden on `prd`, and while the UI setup is loading or unavailable.
 */

import { useUiSetup } from '@/hooks/use-ui-setup'

export function StageIndicator() {
  const uiSetup = useUiSetup()

  if (!uiSetup?.stage || uiSetup.stage === 'prd') {
    return null
  }

  return (
    <span
      className="mr-3 text-xs font-semibold"
      style={{ color: 'hsl(var(--stage-indicator))' }}
      data-testid="app-shell.topbar.stage-indicator"
    >
      {uiSetup.stage.toUpperCase()}
    </span>
  )
}
