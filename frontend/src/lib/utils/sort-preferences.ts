const SORT_STORAGE_KEY = 'iot-support-device-sort'

export interface SortPreference {
  column: 'key' | 'deviceName' | 'deviceEntityId' | 'enableOta' | 'modelName' | 'rotationState' | 'lastCoredumpAt' | 'active'
  direction: 'asc' | 'desc'
}

const DEFAULT_SORT: SortPreference = {
  column: 'key',
  direction: 'asc'
}

export function getSortPreference(): SortPreference {
  try {
    const stored = localStorage.getItem(SORT_STORAGE_KEY)
    if (!stored) return DEFAULT_SORT

    const parsed = JSON.parse(stored) as SortPreference

    // Validate the parsed data
    const validColumns = ['key', 'deviceName', 'deviceEntityId', 'enableOta', 'modelName', 'rotationState', 'lastCoredumpAt', 'active']
    const validDirections = ['asc', 'desc']

    if (
      validColumns.includes(parsed.column) &&
      validDirections.includes(parsed.direction)
    ) {
      return parsed
    }

    // Migration: if user has old 'macAddress' preference, convert to 'key'
    const parsedUnknown = parsed as unknown as { column?: string; direction: SortPreference['direction'] }
    if (parsedUnknown.column === 'macAddress') {
      return { column: 'key', direction: parsed.direction }
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
