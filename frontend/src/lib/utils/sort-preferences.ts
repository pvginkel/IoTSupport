const SORT_STORAGE_KEY = 'iot-support-device-sort'

export interface SortPreference {
  column: 'macAddress' | 'deviceName' | 'deviceEntityId' | 'enableOta'
  direction: 'asc' | 'desc'
}

const DEFAULT_SORT: SortPreference = {
  column: 'macAddress',
  direction: 'asc'
}

export function getSortPreference(): SortPreference {
  try {
    const stored = localStorage.getItem(SORT_STORAGE_KEY)
    if (!stored) return DEFAULT_SORT

    const parsed = JSON.parse(stored) as SortPreference

    // Validate the parsed data
    const validColumns = ['macAddress', 'deviceName', 'deviceEntityId', 'enableOta']
    const validDirections = ['asc', 'desc']

    if (
      validColumns.includes(parsed.column) &&
      validDirections.includes(parsed.direction)
    ) {
      return parsed
    }

    return DEFAULT_SORT
  } catch {
    return DEFAULT_SORT
  }
}

export function setSortPreference(pref: SortPreference): void {
  try {
    localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify(pref))
  } catch {
    // Silently fail if localStorage is unavailable
  }
}
