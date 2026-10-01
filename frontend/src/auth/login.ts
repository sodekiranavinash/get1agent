/**
 * Google-only sign-in.
 *
 * `loginWithRedirect` with an explicit `connection` skips the Auth0 Universal
 * Login screen entirely and goes straight to that provider. We force the Google
 * social connection so there is no Auth0 username/password signup or login.
 *
 * Override with `VITE_AUTH0_CONNECTION` if the Auth0 connection id differs.
 */
export const AUTH0_GOOGLE_CONNECTION =
  (import.meta.env.VITE_AUTH0_CONNECTION as string | undefined)?.trim() ||
  'google-oauth2'

export function googleLoginOptions(returnTo = '/') {
  return {
    authorizationParams: { connection: AUTH0_GOOGLE_CONNECTION },
    appState: { returnTo },
  }
}
