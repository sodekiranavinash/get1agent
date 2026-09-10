import { useCallback, useMemo } from 'react'
import { useApi } from './api'

export type ThemePreference = 'light' | 'dark'

export type UserSettings = {
  id: string
  email: string
  emailVerified: boolean
  fullName: string | null
  pictureUrl: string | null
  preferredTheme: ThemePreference
  timezone: string
  emailOnWorkflowFailure: boolean
  creditThresholdAlerts: boolean
}

export type UserSettingsUpdate = Partial<
  Pick<
    UserSettings,
    | 'fullName'
    | 'preferredTheme'
    | 'timezone'
    | 'emailOnWorkflowFailure'
    | 'creditThresholdAlerts'
  >
>

export function useUserSettings() {
  const api = useApi()

  const getSettings = useCallback(
    () => api<UserSettings>('/v1/user/settings'),
    [api],
  )

  const updateSettings = useCallback(
    (payload: UserSettingsUpdate) =>
      api<UserSettings>('/v1/user/settings', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    [api],
  )

  return useMemo(
    () => ({ getSettings, updateSettings }),
    [getSettings, updateSettings],
  )
}
