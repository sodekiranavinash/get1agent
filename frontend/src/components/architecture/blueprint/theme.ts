import {
  Activity,
  Boxes,
  Database,
  Fingerprint,
  Globe,
  MonitorSmartphone,
  Network,
  Orbit,
  Server,
  ShieldCheck,
  Sparkles,
  SquareFunction,
  Zap,
  type LucideIcon,
} from 'lucide-react'

/** The visual category of a node — drives its icon tile, strip and default icon. */
export type ArchNodeKind =
  | 'client'
  | 'identity'
  | 'edge'
  | 'lambda'
  | 'runtime'
  | 'container'
  | 'data'
  | 'vector'
  | 'cache'
  | 'ai'
  | 'external'
  | 'security'
  | 'observability'

export type KindMeta = {
  icon: LucideIcon
  /** Icon tile fill + icon colour + inset ring. */
  tile: string
  /** Accent strip / dot colour. */
  dot: string
}

export const KIND_META: Record<ArchNodeKind, KindMeta> = {
  client: {
    icon: MonitorSmartphone,
    tile: 'bg-info-soft text-info ring-info/25',
    dot: 'bg-info',
  },
  identity: {
    icon: Fingerprint,
    tile: 'bg-rose-soft text-rose ring-rose/25',
    dot: 'bg-rose',
  },
  edge: {
    icon: Network,
    tile: 'bg-accent-soft text-accent ring-accent/30',
    dot: 'bg-accent',
  },
  lambda: {
    icon: SquareFunction,
    tile: 'bg-warning-soft text-warning ring-warning/25',
    dot: 'bg-warning',
  },
  runtime: {
    icon: Server,
    tile: 'bg-violet-soft text-violet ring-violet/25',
    dot: 'bg-violet',
  },
  container: {
    icon: Boxes,
    tile: 'bg-violet-soft text-violet ring-violet/25',
    dot: 'bg-violet',
  },
  data: {
    icon: Database,
    tile: 'bg-info-soft text-info ring-info/25',
    dot: 'bg-info',
  },
  vector: {
    icon: Orbit,
    tile: 'bg-teal-soft text-teal ring-teal/25',
    dot: 'bg-teal',
  },
  cache: {
    icon: Zap,
    tile: 'bg-teal-soft text-teal ring-teal/25',
    dot: 'bg-teal',
  },
  ai: {
    icon: Sparkles,
    tile: 'bg-violet-soft text-violet ring-violet/25',
    dot: 'bg-violet',
  },
  external: {
    icon: Globe,
    tile: 'bg-elevated text-muted ring-border',
    dot: 'bg-muted',
  },
  security: {
    icon: ShieldCheck,
    tile: 'bg-success-soft text-success ring-success/25',
    dot: 'bg-success',
  },
  observability: {
    icon: Activity,
    tile: 'bg-success-soft text-success ring-success/25',
    dot: 'bg-success',
  },
}

export type ArchEdgeTone =
  | 'request'
  | 'data'
  | 'ai'
  | 'security'
  | 'async'
  | 'cache'
  | 'neutral'

/**
 * Connector / boundary palette. Two needs collide here: the diagram sits on
 * both a dark and a light surface, and SVG markers cannot resolve CSS custom
 * properties, so the tones are fixed hex values chosen to hold up on either
 * background.
 */
export const ARCH_TONES: Record<
  ArchEdgeTone,
  { color: string; label: string }
> = {
  request: { color: '#ff6d5a', label: 'Request / response' },
  data: { color: '#5c9df5', label: 'Data access' },
  ai: { color: '#a78bfa', label: 'AI & inference' },
  security: { color: '#2fbf71', label: 'Identity & security' },
  async: { color: '#e6a23c', label: 'Async / event' },
  cache: { color: '#2dd4bf', label: 'Cache' },
  neutral: { color: '#6b7280', label: 'Infrastructure' },
}

/**
 * AWS-category colours for the service symbol tiles. They mirror the AWS
 * Architecture Icon palette (compute orange, storage green, database magenta,
 * networking purple, security red, ML teal, integration pink) so the diagram
 * reads like an AWS reference architecture without shipping the icon assets.
 */
export const SYMBOL_COLORS: Record<ArchNodeKind, string> = {
  client: '#5C9DF5',
  edge: '#8C4FFF',
  lambda: '#ED7100',
  runtime: '#ED7100',
  container: '#ED7100',
  data: '#C925D1',
  vector: '#7AA116',
  cache: '#E7157B',
  ai: '#01A88D',
  external: '#7A8B99',
  identity: '#DD344C',
  security: '#DD344C',
  observability: '#E7157B',
}

/** Six-char hex → rgba with the given alpha (tones are always #rrggbb). */
export function toneAlpha(tone: ArchEdgeTone, alpha: number): string {
  const hex = ARCH_TONES[tone].color
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
