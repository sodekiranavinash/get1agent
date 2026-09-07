import type { ReactNode } from 'react'
import { Auth0Provider, type AppState } from '@auth0/auth0-react'
import { useNavigate } from 'react-router-dom'
import { AUTH_PATHS, authAbsoluteUrl } from './authUrls'

type Auth0ProviderWithNavigateProps = {
  children: ReactNode
}

export function Auth0ProviderWithNavigate({
  children,
}: Auth0ProviderWithNavigateProps) {
  const navigate = useNavigate()

  const onRedirectCallback = (appState?: AppState) => {
    navigate(appState?.returnTo || '/dashboard', { replace: true })
  }

  return (
    <Auth0Provider
      domain="get1agent.us.auth0.com"
      clientId="dObQEtFUZ1fL4vO9FLOdQEDCmFpt0sjM"
      authorizationParams={{
        redirect_uri: authAbsoluteUrl(AUTH_PATHS.callback),
      }}
      onRedirectCallback={onRedirectCallback}
      skipRedirectCallback={window.location.pathname !== AUTH_PATHS.callback}
    >
      {children}
    </Auth0Provider>
  )
}
