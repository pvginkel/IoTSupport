import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'
import { getDeviceTabPreference } from '@/lib/utils/device-tab-preference'

export const Route = createFileRoute('/devices/$deviceId/')({
  component: RedirectToPreferredTab,
})

// Pure redirect: reads the user's last-used tab from localStorage and
// navigates there with replace. This route never renders visible content.
function RedirectToPreferredTab() {
  const { deviceId } = Route.useParams()
  const navigate = useNavigate()
  const tab = getDeviceTabPreference()

  useEffect(() => {
    navigate({
      to: `/devices/$deviceId/${tab}`,
      params: { deviceId },
      replace: true,
    })
  }, [navigate, deviceId, tab])

  return null
}
