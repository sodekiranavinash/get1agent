import type { User } from '@auth0/auth0-react'

export type UserProfile = {
  firstName: string
  lastName: string
  email: string
  picture: string | undefined
  initial: string
}

export function getUserProfile(user: User | undefined): UserProfile {
  const nameParts = user?.name?.trim().split(/\s+/) ?? []
  const firstName = user?.given_name?.trim() || nameParts[0] || ''
  const lastName =
    user?.family_name?.trim() ||
    (nameParts.length > 1 ? nameParts.slice(1).join(' ') : '')
  const email = user?.email?.trim() || ''
  const initial = (firstName || email || '?').charAt(0).toUpperCase()

  return {
    firstName,
    lastName,
    email,
    picture: user?.picture,
    initial,
  }
}
