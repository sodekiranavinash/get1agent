import { useTheme } from '../../theme/ThemeProvider'

/**
 * Avi's mark.
 *
 * The product's own logo device rather than a decorative glyph: Avi is part of
 * the platform, and a generic sparkle in a coloured circle said nothing about
 * which assistant you were talking to. Two SVGs ship already — a light tile with a
 * dark glyph and the inverse — so this follows the active theme exactly as the
 * favicon does, instead of hand-mixing colours that only suit one of them.
 *
 * Inline `<svg>` (not `<img>`) so the caller controls size and radius with classes
 * and the mark inherits the surrounding layout without a request.
 */
const TILE = {
  light: { background: '#F5F5F7', glyph: '#1D1D1F' },
  dark: { background: '#0A0A0A', glyph: '#FAFAFA' },
} as const

export function AviMark({ className = '' }: { className?: string }) {
  const { theme } = useTheme()
  const { background, glyph } = TILE[theme]

  return (
    <svg
      viewBox="0 0 64 64"
      role="img"
      aria-label="Avi"
      className={`shrink-0 ${className}`}
    >
      <rect width="64" height="64" rx="14" fill={background} />
      <path
        fill={glyph}
        d="M22.4 17.2 36.2 8.6h7.4V55H28.2V22.4l-5.8 3.6V17.2Z"
      />
    </svg>
  )
}
