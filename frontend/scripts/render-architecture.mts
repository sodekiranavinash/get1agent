/**
 * Render the Architecture page diagrams to standalone SVG + PNG for the GitHub
 * README — from the *same* source the app renders.
 *
 * There is deliberately no second drawing here: this script imports the exact
 * `FlowSpec` objects the app renders (`diagrams.ts`, `sheets.ts`, `journeys.ts`)
 * and runs the exact same layout engine (`layoutFlow`) the React page uses, then
 * serialises the result to a self-contained dark-theme SVG. Change the app's
 * diagram and re-run `npm run gen:architecture` — the README follows.
 *
 * Run from `frontend/`:  npm run gen:architecture
 */
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Resvg } from '@resvg/resvg-js'

import {
  layoutFlow,
  type FlowLayout,
  type LaidFlowEdge,
  type LaidFlowSection,
} from '../src/components/architecture/blueprint/flow.ts'
import {
  ARCHITECTURE_FLOW,
  ARCHITECTURE_FLOW_LEGEND,
} from '../src/components/architecture/blueprint/diagrams.ts'
import {
  KNOWLEDGE_JOURNEYS,
  RUNTIME_JOURNEYS,
  journeyTones,
} from '../src/components/architecture/blueprint/journeys.ts'
import {
  DATA_FLOW,
  DATA_FLOW_LEGEND,
  DEPLOYMENT_FLOW,
  DEPLOYMENT_FLOW_LEGEND,
  LAYERS_FLOW,
  LAYERS_FLOW_LEGEND,
  SECURITY_FLOW,
  SECURITY_FLOW_LEGEND,
} from '../src/components/architecture/blueprint/sheets.ts'
import {
  ARCH_TONES,
  KIND_META,
  SYMBOL_COLORS,
  toneAlpha,
  type ArchEdgeTone,
} from '../src/components/architecture/blueprint/theme.ts'
import { AWS_ICONS } from '../src/components/architecture/blueprint/awsIcons.ts'

/* -------------------------------------------------------------------------- */
/* Theme — mirrors the app's dark palette (frontend/src/index.css).            */
/* -------------------------------------------------------------------------- */

const C = {
  canvas: '#101216',
  raised: '#1e2127',
  foreground: '#e8eaed',
  muted: '#9aa2ad',
  subtle: '#6b7280',
  border: '#2a2e36',
  borderStrong: '#3a3f49',
}

const FONT = "'Inter Variable', 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
const MONO = "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, monospace"

const PAD = 30
const LEGEND_H = 30
const GAP = 18

/* -------------------------------------------------------------------------- */
/* Small helpers                                                               */
/* -------------------------------------------------------------------------- */

const esc = (s: unknown): string =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/** Rough advance width of one character, good enough to wrap diagram copy. */
function charWidth(ch: string, size: number): number {
  if (ch === ' ') return size * 0.27
  if ("iljItf1.,:;'|![]()".includes(ch)) return size * 0.32
  if ('mwMW'.includes(ch)) return size * 0.86
  if (ch >= 'A' && ch <= 'Z') return size * 0.63
  if (ch >= '0' && ch <= '9') return size * 0.56
  return size * 0.53
}

function textWidth(s: string, size: number, bold = false, spacing = 0): number {
  let w = 0
  for (const ch of s) w += charWidth(ch, size)
  return w * (bold ? 1.04 : 1) + s.length * spacing
}

function wrapText(s: string, maxWidth: number, size: number, bold: boolean, maxLines: number, spacing = 0): string[] {
  const words = String(s).split(/\s+/).filter(Boolean)
  const lines: string[] = []
  let cur = ''
  for (const word of words) {
    const next = cur ? `${cur} ${word}` : word
    if (!cur || textWidth(next, size, bold, spacing) <= maxWidth) {
      cur = next
    } else {
      lines.push(cur)
      cur = word
      if (lines.length === maxLines) break
    }
  }
  if (cur && lines.length < maxLines) lines.push(cur)
  return lines.length ? lines : [String(s)]
}

type TextOpts = {
  size?: number
  fill?: string
  weight?: number
  anchor?: 'start' | 'middle' | 'end'
  mono?: boolean
  spacing?: number
  opacity?: number
}

function text(x: number, y: number, s: string, o: TextOpts = {}): string {
  const attrs = [
    `x="${round(x)}"`,
    `y="${round(y)}"`,
    `font-size="${o.size ?? 12}"`,
    `fill="${o.fill ?? C.foreground}"`,
    `font-weight="${o.weight ?? 400}"`,
  ]
  if (o.anchor && o.anchor !== 'start') attrs.push(`text-anchor="${o.anchor}"`)
  if (o.mono) attrs.push(`font-family="${MONO}"`)
  if (o.spacing != null) attrs.push(`letter-spacing="${o.spacing}"`)
  if (o.opacity != null) attrs.push(`opacity="${o.opacity}"`)
  return `<text ${attrs.join(' ')}>${esc(s)}</text>`
}

const round = (n: number): number => Math.round(n * 10) / 10

/** Wrap a rendered icon component and place it at (x, y) at the given size. */
function placeIcon(Comp: unknown, x: number, y: number, size: number): string {
  const markup = renderToStaticMarkup(
    createElement(Comp as never, {
      width: size,
      height: size,
      strokeWidth: 1.9,
      color: '#fff',
      fill: 'none',
    }),
  )
  const vb = markup.match(/viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"/)
  const vw = vb ? Number(vb[1]) : 24
  const inner = markup.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '')
  const scale = round(size / vw)
  return `<g transform="translate(${round(x)} ${round(y)}) scale(${scale})">${inner}</g>`
}

/* -------------------------------------------------------------------------- */
/* Shared pieces                                                               */
/* -------------------------------------------------------------------------- */

/** The dotted, gradient-washed boundary used by bands and pipeline envs. */
function boundary(x: number, y: number, w: number, h: number, tone: ArchEdgeTone): string {
  return (
    `<rect x="${round(x)}" y="${round(y)}" width="${round(w)}" height="${round(h)}" rx="16" ` +
    `fill="url(#wash-${tone})" stroke="${toneAlpha(tone, 0.5)}" stroke-width="1.5" ` +
    `stroke-dasharray="2 4"/>`
  )
}

/** Trim to `maxW`, with an ellipsis, so a label never overflows its column. */
function truncate(s: string, maxW: number, size: number, bold = false): string {
  if (textWidth(s, size, bold) <= maxW) return s
  let out = s
  while (out.length > 1 && textWidth(`${out}…`, size, bold) > maxW) out = out.slice(0, -1)
  return `${out.trimEnd()}…`
}

/** Place an icon at (x, y) at the given size, clipped to a rounded tile. */
function tileIcon(aws: unknown, icon: unknown, kind: string, x: number, y: number, size: number, radius: number): string {
  const out: string[] = []
  if (aws) {
    out.push(
      `<g transform="translate(${round(x)} ${round(y)})">` +
        `<g clip-path="url(#tileClipSmall)">${placeIcon(aws, 0, 0, size)}</g>` +
        `</g>`,
    )
  } else {
    out.push(
      `<rect x="${round(x)}" y="${round(y)}" width="${size}" height="${size}" rx="${radius}" ` +
        `fill="${SYMBOL_COLORS[kind as keyof typeof SYMBOL_COLORS]}"/>`,
    )
    const inner = round(size * 0.44)
    out.push(placeIcon(icon, x + (size - inner) / 2, y + (size - inner) / 2, inner))
  }
  out.push(
    `<rect x="${round(x)}" y="${round(y)}" width="${size}" height="${size}" rx="${radius}" ` +
      `fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="1"/>`,
  )
  return out.join('')
}

/**
 * One service in the composed map: a 46px tile with its name and one micro
 * line under it — the same shape `FlowTile` renders.
 */
function flowTile(n: any): string {
  const size = 40
  const tileX = n.x + (n.w - size) / 2
  const aws = n.aws ? AWS_ICONS[n.aws as keyof typeof AWS_ICONS] : undefined
  const Icon = n.icon ?? KIND_META[n.kind as keyof typeof KIND_META].icon
  const out: string[] = [tileIcon(aws, Icon, n.kind, tileX, n.y, size, 13)]
  let ty = n.y + size + 12
  for (const line of wrapText(n.title, n.w + 6, 10, true, 2)) {
    out.push(text(n.cx, ty, line, { size: 10, weight: 600, anchor: 'middle' }))
    ty += 11
  }
  if (n.code) out.push(text(n.cx, ty + 1, n.code, { size: 8.5, fill: C.subtle, anchor: 'middle', mono: true }))
  return out.join('')
}

function legend(tones: ArchEdgeTone[], note: string | undefined, width: number, top: number): string {
  const cy = top + LEGEND_H / 2
  const out: string[] = []
  let x = 0

  out.push(
    `<rect x="${round(x)}" y="${round(cy - 6)}" width="12" height="12" rx="3" fill="none" ` +
      `stroke="${C.borderStrong}" stroke-width="1.5" stroke-dasharray="2 3"/>`,
  )
  out.push(text(x + 18, cy + 3.5, 'Isolated boundary', { size: 10.5, weight: 500, fill: C.muted }))
  x += 18 + textWidth('Isolated boundary', 10.5, true) + 16

  out.push(`<line x1="${round(x)}" y1="${round(cy - 7)}" x2="${round(x)}" y2="${round(cy + 7)}" stroke="${C.border}"/>`)
  x += 16

  for (const tone of tones) {
    const label = ARCH_TONES[tone].label
    out.push(`<line x1="${round(x)}" y1="${round(cy)}" x2="${round(x + 20)}" y2="${round(cy)}" stroke="${ARCH_TONES[tone].color}" stroke-width="2" stroke-linecap="round"/>`)
    out.push(text(x + 26, cy + 3.5, label, { size: 10.5, weight: 500, fill: C.muted }))
    x += 26 + textWidth(label, 10.5, true) + 16
  }

  if (note) out.push(text(width, cy + 3.5, note, { size: 10.5, fill: C.subtle, anchor: 'end' }))
  return out.join('')
}

function defs(tones: ArchEdgeTone[]): string {
  const markers = tones
    .map(
      (tone) =>
        `<marker id="arrow-${tone}" viewBox="0 0 10 10" refX="7.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">` +
        `<path d="M1.5,1.5 L8,5 L1.5,8.5" fill="none" stroke="${ARCH_TONES[tone].color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker>`,
    )
    .join('')
  const washes = tones
    .map(
      (tone) =>
        `<linearGradient id="wash-${tone}" x1="0" y1="0" x2="0" y2="1">` +
        `<stop offset="0" stop-color="${toneAlpha(tone, 0.07)}"/>` +
        `<stop offset="0.42" stop-color="${toneAlpha(tone, 0)}"/></linearGradient>`,
    )
    .join('')
  return (
    `<defs>${markers}${washes}` +
    `<clipPath id="tileClip"><rect x="0" y="0" width="52" height="52" rx="16"/></clipPath>` +
    `<clipPath id="tileClipSmall"><rect x="0" y="0" width="26" height="26" rx="8"/></clipPath>` +
    `</defs>`
  )
}

function frame(width: number, height: number, body: string): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" ` +
    `viewBox="0 0 ${width} ${height}" font-family="${FONT}" role="img">` +
    `<rect width="${width}" height="${height}" fill="${C.canvas}"/>` +
    body +
    `</svg>`
  )
}

/* -------------------------------------------------------------------------- */
/* FlowSpec (horizontal request map)                                           */
/* -------------------------------------------------------------------------- */

/**
 * A group of services: the dotted box with its number, title and hint along the
 * top — the same shape `GroupBox` renders.
 */
function flowGroup(section: LaidFlowSection): string {
  const color = ARCH_TONES[section.tone].color
  const out: string[] = [
    boundary(section.x, section.y, section.w, section.h, section.tone),
  ]
  const x = section.x + 12
  const y = section.y + 8
  const index = String(section.index + 1).padStart(2, '0')
  out.push(text(x, y + 8, index, { size: 10, fill: C.subtle, mono: true }))
  const dotX = x + textWidth(index, 10) + 10
  out.push(`<circle cx="${round(dotX)}" cy="${round(y + 4.5)}" r="3" fill="${color}"/>`)
  out.push(
    text(dotX + 9, y + 8, section.title.toUpperCase(), {
      size: 11,
      weight: 600,
      fill: color,
      spacing: 1.3,
    }),
  )
  if (section.hint) {
    out.push(
      text(x, y + 24, truncate(section.hint, section.w - 24, 10), {
        size: 10,
        fill: C.subtle,
      }),
    )
  }
  return out.join('')
}

/** Connectors: a solid line, an arrow at the target and a dot at the source. */
function flowEdges(edges: LaidFlowEdge[]): string {
  const out: string[] = []
  for (const e of edges) {
    const color = ARCH_TONES[e.tone].color
    out.push(
      `<path d="${e.d}" fill="none" stroke="${color}" stroke-width="1.7" ` +
        `stroke-opacity="${e.still ? 1 : 0.6}" stroke-linecap="round" ` +
        `stroke-linejoin="round"${e.still ? ' stroke-dasharray="2 5"' : ''} ` +
        `marker-end="url(#arrow-${e.tone})"/>`,
    )
    if (!e.still) out.push(`<circle cx="${round(e.sx)}" cy="${round(e.sy)}" r="2.8" fill="${color}"/>`)
    if (e.label && e.labelX != null && e.labelY != null) {
      const w = textWidth(e.label, 9, true) + 12
      out.push(
        `<rect x="${round(e.labelX - w / 2)}" y="${round(e.labelY - 7)}" width="${round(w)}" height="14" rx="7" ` +
          `fill="${C.canvas}" fill-opacity="0.92" stroke="${toneAlpha(e.tone, 0.4)}" stroke-width="1"/>`,
      )
      out.push(
        text(e.labelX, e.labelY + 3, e.label, {
          size: 9,
          fill: color,
          anchor: 'middle',
          mono: true,
        }),
      )
    }
  }
  return out.join('')
}

function renderFlow(layout: FlowLayout, tones: ArchEdgeTone[], note?: string): string {
  const tonesUsed = Array.from(new Set<ArchEdgeTone>([...tones, ...layout.edges.map((e) => e.tone)]))
  const width = layout.width + 2 * PAD
  const canvasTop = PAD + LEGEND_H + GAP
  const height = canvasTop + layout.height + PAD
  const out: string[] = [defs(tonesUsed)]

  out.push(`<g transform="translate(${PAD} 0)">${legend(tones, note, layout.width, PAD)}</g>`)
  out.push(`<g transform="translate(${PAD} ${canvasTop})">`)
  for (const section of layout.sections) out.push(flowGroup(section))
  out.push(flowEdges(layout.edges))
  for (const n of layout.nodes) out.push(flowTile(n))
  out.push('</g>')

  return frame(width, height, out.join(''))
}

/* -------------------------------------------------------------------------- */
/* Registry — one entry per README image                                       */
/* -------------------------------------------------------------------------- */

const __dirname = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(__dirname, '../../docs/assets')

const images: { file: string; svg: string }[] = []

images.push({
  file: 'architecture',
  svg: renderFlow(layoutFlow(ARCHITECTURE_FLOW), ARCHITECTURE_FLOW_LEGEND, '9 groups · 36 services · AWS-native'),
})
images.push({
  file: 'architecture-layers',
  svg: renderFlow(layoutFlow(LAYERS_FLOW), LAYERS_FLOW_LEGEND, '12 tiers · read left to right'),
})
images.push({
  file: 'architecture-deployment',
  svg: renderFlow(layoutFlow(DEPLOYMENT_FLOW), DEPLOYMENT_FLOW_LEGEND, 'one codebase · local and prod'),
})
images.push({
  file: 'architecture-data',
  svg: renderFlow(layoutFlow(DATA_FLOW), DATA_FLOW_LEGEND, 'write → store → read'),
})
images.push({
  file: 'architecture-security',
  svg: renderFlow(layoutFlow(SECURITY_FLOW), SECURITY_FLOW_LEGEND, 'defense in depth'),
})

const runtime = RUNTIME_JOURNEYS[0]
images.push({
  file: 'architecture-agent-runtime',
  svg: renderFlow(layoutFlow(runtime.spec), journeyTones(runtime), 'one run · end to end'),
})

const retrieval = KNOWLEDGE_JOURNEYS.find((j) => j.id === 'retrieval') ?? KNOWLEDGE_JOURNEYS[0]
images.push({
  file: 'architecture-knowledge',
  svg: renderFlow(layoutFlow(retrieval.spec), journeyTones(retrieval), 'question → answer'),
})

const graphIngestion =
  KNOWLEDGE_JOURNEYS.find((j) => j.id === 'graph-ingestion') ?? KNOWLEDGE_JOURNEYS[0]
images.push({
  file: 'architecture-graph-ingestion',
  svg: renderFlow(
    layoutFlow(graphIngestion.spec),
    journeyTones(graphIngestion),
    'one gated stage · hybrid KBs skip',
  ),
})

const graphRetrieval =
  KNOWLEDGE_JOURNEYS.find((j) => j.id === 'graph-retrieval') ?? KNOWLEDGE_JOURNEYS[0]
images.push({
  file: 'architecture-graph-retrieval',
  svg: renderFlow(
    layoutFlow(graphRetrieval.spec),
    journeyTones(graphRetrieval),
    'additive on the hybrid legs',
  ),
})

/* -------------------------------------------------------------------------- */
/* Write SVG + PNG                                                             */
/* -------------------------------------------------------------------------- */

mkdirSync(outDir, { recursive: true })
for (const { file, svg } of images) {
  writeFileSync(resolve(outDir, `${file}.svg`), svg)
  const w = Number(svg.match(/width="(\d+)"/)?.[1] ?? 1600)
  const resvg = new Resvg(svg, {
    fitTo: { mode: 'width', value: w * 2 },
    font: { loadSystemFonts: true, defaultFontFamily: 'Helvetica' },
  })
  writeFileSync(resolve(outDir, `${file}.png`), resvg.render().asPng())
  console.log(`  ✓ ${file}.svg + ${file}.png  (${w}×…)`)
}
console.log(`Wrote ${images.length} diagram(s) to docs/assets/`)
