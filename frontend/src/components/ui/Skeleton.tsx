import type { CSSProperties } from 'react'

type SkeletonProps = {
  className?: string
  style?: CSSProperties
}

/** Neutral shimmer block. Compose these into page-shaped skeletons. */
export function Skeleton({ className = '', style }: SkeletonProps) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />
}
