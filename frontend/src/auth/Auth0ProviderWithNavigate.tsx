import { useCallback, useMemo, type ReactNode } from 'react'
import { Auth0Provider, type AppState } from '@auth0/auth0-react'
import { useNavigate } from 'react-router-dom'
import { AUTH_PATHS, authAbsoluteUrl } from './authUrls'
import { clearStoredView } from './view'

const AUTH0_DOMAIN = import.meta.env.VITE_AUTH0_DOMAIN
const AUTH0_CLIENT_ID = import.meta.env.VITE_AUTH0_CLIENT_ID
const AUTH0_AUDIENCE = import.meta.env.VITE_AUTH0_AUDIENCE

type Auth0ProviderWithNavigateProps = {
  children: ReactNode
}

export function Auth0ProviderWithNavigate({
  children,
}: Auth0ProviderWithNavigateProps) {
  const navigate = useNavigate()

  const onRedirectCallback = useCallback(
    (appState?: AppState) => {
      // Fresh login: forget the previous view so the user chooses again.
      clearStoredView()
      navigate(appState?.returnTo || '/dashboard', { replace: true })
    },
    [navigate],
  )

  const authorizationParams = useMemo(
    () => ({
      redirect_uri: authAbsoluteUrl(AUTH_PATHS.callback),
      audience: AUTH0_AUDIENCE,
    }),
    [],
  )

  const skipRedirectCallback =
    window.location.pathname !== AUTH_PATHS.callback

  return (
    <Auth0Provider
      domain={AUTH0_DOMAIN}
      clientId={AUTH0_CLIENT_ID}
      authorizationParams={authorizationParams}
      onRedirectCallback={onRedirectCallback}
      skipRedirectCallback={skipRedirectCallback}
      // Persist tokens across full-page refreshes. The default in-memory
      // cache is wiped on every reload, forcing a ~1-2s silent-auth round
      // trip to Auth0 during which the app can only show a blank screen.
      // With localstorage the SDK restores the session synchronously and
      // the page mounts immediately (silent auth still runs automatically
      // once the access token expires).
      cacheLocation="localstorage"
    >
      {children}
    </Auth0Provider>
  )
}
