import { createFileRoute } from '@tanstack/react-router'
import { useRestoreTab } from '@/components/primitives'
import { DEVICE_TAB_STORAGE_KEY, DEVICE_TAB_VALUES } from '@/components/devices/device-detail-header'

export const Route = createFileRoute('/devices/$deviceId/')({
  component: RedirectToPreferredTab,
})

// Pure redirect: reads the user's last-used tab from localStorage and
// navigates there with replace. This route never renders visible content.
function RedirectToPreferredTab() {
  const { deviceId } = Route.useParams()

  useRestoreTab({
    storageKey: DEVICE_TAB_STORAGE_KEY,
    validValues: [...DEVICE_TAB_VALUES],
    defaultValue: 'edit',
    toPath: (tab) => ({
      to: `/devices/$deviceId/${tab}`,
      params: { deviceId },
    }),
  })

  return null
}
