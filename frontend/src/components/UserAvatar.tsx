import { useState } from 'react'

type UserAvatarProps = {
  picture?: string
  initial: string
  alt?: string
  className?: string
}

export function UserAvatar({
  picture,
  initial,
  alt = 'Account',
  className = 'h-9 w-9',
}: UserAvatarProps) {
  const [imageFailed, setImageFailed] = useState(false)
  const showImage = Boolean(picture) && !imageFailed

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-accent/15 text-sm font-semibold text-accent ${className}`}
    >
      {showImage ? (
        <img
          src={picture}
          alt={alt}
          referrerPolicy="no-referrer"
          className="block h-full w-full object-cover"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <span aria-hidden="true">{initial}</span>
      )}
    </span>
  )
}
