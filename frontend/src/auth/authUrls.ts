export const AUTH_PATHS = {
  login: '/login',
  callback: '/authorization/callback',
  logout: '/logout',
} as const

export const appOrigin = () => window.location.origin

export const authAbsoluteUrl = (path: (typeof AUTH_PATHS)[keyof typeof AUTH_PATHS]) =>
  `${appOrigin()}${path}`
