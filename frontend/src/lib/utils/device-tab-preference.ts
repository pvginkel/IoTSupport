const STORAGE_KEY = 'iot-support-device-tab'

export type DeviceTab = 'configuration' | 'logs' | 'coredumps'

const VALID_TABS: DeviceTab[] = ['configuration', 'logs', 'coredumps']

export function getDeviceTabPreference(): DeviceTab {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && VALID_TABS.includes(stored as DeviceTab)) {
      return stored as DeviceTab
    }
    return 'configuration'
  } catch {
    return 'configuration'
  }
}

export function setDeviceTabPreference(tab: DeviceTab): void {
  try {
    localStorage.setItem(STORAGE_KEY, tab)
  } catch {
    // Silently fail if localStorage is unavailable
  }
}
