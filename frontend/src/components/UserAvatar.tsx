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
  className = 'h-8 w-8',
}: UserAvatarProps) {
  const [imageFailed, setImageFailed] = useState(false)
  const showImage = Boolean(picture) && !imageFailed

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[10px] bg-gradient-to-br from-accent via-[#ff8575] to-[#ea580c] p-[2px] ${className}`}
    >
      <span className="flex h-full w-full items-center justify-center overflow-hidden rounded-[8px] bg-raised text-xs font-bold tracking-wide text-accent">
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
    </span>
  )
}
