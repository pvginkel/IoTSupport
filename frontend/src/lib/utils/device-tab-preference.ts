const STORAGE_KEY = 'iot-support-device-tab'

export type DeviceTab = 'edit' | 'logs' | 'coredumps'

const VALID_TABS: DeviceTab[] = ['edit', 'logs', 'coredumps']

export function getDeviceTabPreference(): DeviceTab {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && VALID_TABS.includes(stored as DeviceTab)) {
      return stored as DeviceTab
    }
    return 'edit'
  } catch {
    return 'edit'
  }
}

export function setDeviceTabPreference(tab: DeviceTab): void {
  try {
    localStorage.setItem(STORAGE_KEY, tab)
  } catch {
    // Silently fail if localStorage is unavailable
  }
}
