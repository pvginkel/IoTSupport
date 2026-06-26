/**
 * Application-specific sidebar navigation items.
 * App-owned — the sidebar shell imports this array to render navigation links.
 */

import { Box, Settings, RefreshCw } from 'lucide-react'
import type { SidebarItem } from './sidebar'

export const navigationItems: SidebarItem[] = [
  { to: '/device-models', label: 'Device Models', icon: Box, testId: 'device-models' },
  { to: '/devices', label: 'Devices', icon: Settings, testId: 'devices' },
  { to: '/rotation', label: 'Rotation Dashboard', icon: RefreshCw, testId: 'rotation' },
]
