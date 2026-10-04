/**
 * Google sign-in helpers.
 *
 * The provider-first flow pins the Auth0 Google social connection so Auth0's
 * Universal Login page is skipped and the Google account chooser is shown
 * directly. No extra Google client id is needed on the frontend — Google OAuth
 * is configured on the Auth0 connection.
 *
 * Override the connection id with `VITE_AUTH_CONNECTION` if it differs.
 */
export const AUTH_GOOGLE_CONNECTION =
  (import.meta.env.VITE_AUTH_CONNECTION as string | undefined)?.trim() ||
  'google-oauth2'

export function googleLoginOptions(returnTo = '/dashboard') {
  return {
    authorizationParams: {
      connection: AUTH_GOOGLE_CONNECTION,
    },
    appState: { returnTo },
  }
}
