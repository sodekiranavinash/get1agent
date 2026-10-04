/**
 * Render the Architecture page diagrams to standalone SVG + PNG for the GitHub
 * README — from the *same* source the app renders.
 *
 * There is deliberately no second drawing here: this script imports the exact
 * `DiagramSpec`/`PipelineSpec` objects (`diagrams.ts`) and runs the exact same
 * layout engines (`layoutDiagram` / `layoutPipeline`) the React page uses, then
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

import { layoutDiagram, type Layout } from '../src/components/architecture/blueprint/engine.ts'
import { pipelineToDiagram } from '../src/components/architecture/blueprint/pipeline.ts'
import {
  ARCHITECTURE,
  ARCHITECTURE_LEGEND,
  DEPLOYMENT,
  DEPLOYMENT_LEGEND,
  DATA_STORAGE,
  DATA_LEGEND,
  SECURITY,
  SECURITY_LEGEND,
  AGENT_LIFECYCLE,
  KNOWLEDGE_TAB_FLOWS,
} from '../src/components/architecture/blueprint/diagrams.ts'
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

/** A service symbol: a 52px AWS tile with the name and subtitle beneath it. */
function node(node: any, numbered?: number): string {
  const tileX = node.cx - 26
  const tileY = node.y
  const out: string[] = []
  const aws = node.aws ? AWS_ICONS[node.aws as keyof typeof AWS_ICONS] : undefined

  if (aws) {
    out.push(
      `<g transform="translate(${round(tileX)} ${round(tileY)})">` +
        `<g clip-path="url(#tileClip)">${placeIcon(aws, 0, 0, 52)}</g>` +
        `</g>`,
    )
  } else {
    const Icon = node.icon ?? KIND_META[node.kind as keyof typeof KIND_META].icon
    out.push(
      `<rect x="${round(tileX)}" y="${round(tileY)}" width="52" height="52" rx="16" ` +
        `fill="${SYMBOL_COLORS[node.kind as keyof typeof SYMBOL_COLORS]}"/>`,
    )
    out.push(placeIcon(Icon, tileX + 14, tileY + 14, 24))
  }
  out.push(
    `<rect x="${round(tileX)}" y="${round(tileY)}" width="52" height="52" rx="16" ` +
      `fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="1"/>`,
  )

  if (numbered != null) {
    out.push(
      `<circle cx="${round(tileX + 10)}" cy="${round(tileY + 10)}" r="10" ` +
        `fill="${C.canvas}" stroke="${C.border}" stroke-width="1"/>`,
    )
    out.push(text(tileX + 10, tileY + 13.5, String(numbered), { size: 9, weight: 600, anchor: 'middle', mono: true }))
  }

  const maxW = node.w - 6
  let ty = tileY + 52 + 18
  const titleLines = wrapText(node.title, maxW, 12, true, 2)
  for (const line of titleLines) {
    out.push(text(node.cx, ty, line, { size: 12, weight: 600, anchor: 'middle' }))
    ty += 13.5
  }
  if (node.subtitle) {
    ty += 1
    for (const line of wrapText(node.subtitle, maxW, 10.5, false, 2)) {
      out.push(text(node.cx, ty, line, { size: 10.5, fill: C.muted, anchor: 'middle' }))
      ty += 12.6
    }
  }
  if (node.code) {
    ty += 1.5
    out.push(text(node.cx, ty, node.code, { size: 9.5, fill: C.subtle, anchor: 'middle', mono: true }))
  }
  return out.join('')
}

function edgeLayer(edges: Layout['edges']): string {
  const out: string[] = []
  for (const e of edges) {
    const color = ARCH_TONES[e.tone].color
    out.push(
      `<path d="${e.d}" fill="none" stroke="${color}" stroke-width="1.5" ` +
        `stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="1 6" ` +
        `marker-end="url(#arrow-${e.tone})"/>`,
    )
    out.push(`<circle cx="${round(e.sx)}" cy="${round(e.sy)}" r="2.6" fill="${color}"/>`)
    if (e.label && e.labelX != null && e.labelY != null) {
      const w = textWidth(e.label, 9, true) + 12
      out.push(
        `<rect x="${round(e.labelX - w / 2)}" y="${round(e.labelY - 7)}" width="${round(w)}" height="14" rx="7" ` +
          `fill="${C.canvas}" fill-opacity="0.9" stroke="${toneAlpha(e.tone, 0.4)}" stroke-width="1"/>`,
      )
      out.push(text(e.labelX, e.labelY + 3, e.label, { size: 9, fill: color, anchor: 'middle', mono: true }))
    }
  }
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
/* DiagramSpec (layered map)                                                   */
/* -------------------------------------------------------------------------- */

function renderDiagram(layout: Layout, tones: ArchEdgeTone[], note?: string): string {
  const tonesUsed = Array.from(new Set<ArchEdgeTone>([...tones, ...layout.edges.map((e) => e.tone)]))
  const width = layout.width + 2 * PAD
  const canvasTop = PAD + LEGEND_H + GAP
  const height = canvasTop + layout.height + PAD
  const out: string[] = [defs(tonesUsed)]

  out.push(`<g transform="translate(${PAD} 0)">${legend(tones, note, layout.width, PAD)}</g>`)
  out.push(`<g transform="translate(${PAD} ${canvasTop})">`)

  for (const band of layout.bands) {
    out.push(boundary(band.x, band.y, band.w, band.h, band.tone))
    // Gutter label: index + dot, uppercase title, wrapped hint — right aligned.
    const gx = band.x - 20
    const titleLines = wrapText(band.title.toUpperCase(), 148, 12, true, 3, 1.4)
    const hintLines = band.hint ? wrapText(band.hint, 148, 10.5, false, 3) : []
    const blockH = 15 + titleLines.length * 14 + (hintLines.length ? 4 + hintLines.length * 12.5 : 0)
    let cy = band.y + band.h / 2 - blockH / 2
    const rowCy = cy + 6
    const index = String(band.index + 1).padStart(2, '0')
    out.push(text(gx - 11, rowCy + 3.5, index, { size: 10, fill: C.subtle, anchor: 'end', mono: true }))
    out.push(`<circle cx="${round(gx - 3.5)}" cy="${round(rowCy)}" r="3" fill="${ARCH_TONES[band.tone].color}"/>`)
    cy += 15
    for (const line of titleLines) {
      out.push(text(gx, cy + 10, line, { size: 12, weight: 600, anchor: 'end', fill: ARCH_TONES[band.tone].color, spacing: 1.4 }))
      cy += 14
    }
    if (hintLines.length) {
      cy += 4
      for (const line of hintLines) {
        out.push(text(gx, cy + 9, line, { size: 10.5, fill: C.subtle, anchor: 'end' }))
        cy += 12.5
      }
    }
  }

  for (const cap of layout.captions) {
    const cy = cap.y + 11
    const cx = cap.x + cap.w / 2
    const label = cap.text.toUpperCase()
    const tw = textWidth(label, 10.5, true, 1.5)
    const left = cx - (tw + 16) / 2
    out.push(`<line x1="${round(cap.x)}" y1="${round(cy)}" x2="${round(left - 10)}" y2="${round(cy)}" stroke="${toneAlpha(cap.tone, 0.35)}"/>`)
    out.push(`<line x1="${round(left + tw + 10)}" y1="${round(cy)}" x2="${round(cap.x + cap.w)}" y2="${round(cy)}" stroke="${toneAlpha(cap.tone, 0.35)}"/>`)
    out.push(`<circle cx="${round(left + 3)}" cy="${round(cy)}" r="3" fill="${ARCH_TONES[cap.tone].color}"/>`)
    out.push(text(left + 10, cy + 3.5, label, { size: 10.5, weight: 600, fill: C.subtle, spacing: 1.5 }))
  }

  out.push(edgeLayer(layout.edges))
  for (const n of layout.nodes) out.push(node(n, n.badge))
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
  svg: renderDiagram(layoutDiagram(ARCHITECTURE), ARCHITECTURE_LEGEND, '9 stages · application flow · 10+ AWS services'),
})
images.push({
  file: 'architecture-deployment',
  svg: renderDiagram(layoutDiagram(DEPLOYMENT), DEPLOYMENT_LEGEND, 'one codebase · local and prod'),
})
images.push({
  file: 'architecture-data',
  svg: renderDiagram(layoutDiagram(DATA_STORAGE), DATA_LEGEND, 'write → store → read'),
})
images.push({
  file: 'architecture-security',
  svg: renderDiagram(layoutDiagram(SECURITY), SECURITY_LEGEND, 'defense in depth'),
})

const runtimeTones = Array.from(new Set(AGENT_LIFECYCLE.spec.envs.map((e) => e.tone)))
images.push({ file: 'architecture-agent-runtime', svg: renderDiagram(layoutDiagram(pipelineToDiagram(AGENT_LIFECYCLE.spec)), runtimeTones) })

const retrieval = KNOWLEDGE_TAB_FLOWS.find((f) => f.id === 'retrieval') ?? KNOWLEDGE_TAB_FLOWS[0]
const knowledgeTones = Array.from(new Set(retrieval.spec.envs.map((e) => e.tone)))
images.push({ file: 'architecture-knowledge', svg: renderDiagram(layoutDiagram(pipelineToDiagram(retrieval.spec)), knowledgeTones) })

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
