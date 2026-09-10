import { useCallback, useMemo, type ReactNode } from 'react'
import { Auth0Provider, type AppState } from '@auth0/auth0-react'
import { useNavigate } from 'react-router-dom'
import { AUTH_PATHS, authAbsoluteUrl } from './authUrls'

const AUTH0_DOMAIN =
  import.meta.env.VITE_AUTH0_DOMAIN ?? 'get1agent.us.auth0.com'
const AUTH0_CLIENT_ID =
  import.meta.env.VITE_AUTH0_CLIENT_ID ?? 'dObQEtFUZ1fL4vO9FLOdQEDCmFpt0sjM'
const AUTH0_AUDIENCE =
  import.meta.env.VITE_AUTH0_AUDIENCE ?? 'https://api.get1agent.com'

type Auth0ProviderWithNavigateProps = {
  children: ReactNode
}

export function Auth0ProviderWithNavigate({
  children,
}: Auth0ProviderWithNavigateProps) {
  const navigate = useNavigate()

  const onRedirectCallback = useCallback(
    (appState?: AppState) => {
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
    >
      {children}
    </Auth0Provider>
  )
}
