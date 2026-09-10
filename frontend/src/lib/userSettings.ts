import { useCallback } from 'react'
import { usePageQuery } from '../hooks/usePageQuery'
import { useApiClient } from './api'
import { setQueryData } from './query'

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

const SETTINGS_QUERY_KEY = 'user-settings'

export function useUserSettings() {
  const api = useApiClient()

  const query = usePageQuery(SETTINGS_QUERY_KEY, () =>
    api.get<UserSettings>('/v1/user/settings'),
  )

  const updateSettings = useCallback(
    async (payload: UserSettingsUpdate) => {
      const updated = await api.post<UserSettings>(
        '/v1/user/settings',
        payload,
      )
      setQueryData(SETTINGS_QUERY_KEY, updated)
      return updated
    },
    [api],
  )

  return { ...query, updateSettings }
}
