import type { LucideIcon } from 'lucide-react'
import type { ArchEdgeTone, ArchNodeKind } from './theme'
import type { AwsIconId } from './awsIcons'
import type { DiagramSpec, NodeSpec } from './engine'

export type PipeEnv = {
  id: string
  label: string
  hint?: string
  tone: ArchEdgeTone
}

export type PipeStep = {
  kind: ArchNodeKind
  title: string
  subtitle?: string
  code?: string
  icon?: LucideIcon
  env: string
  /** Overrides the connector colour leaving toward the next step. */
  tone?: ArchEdgeTone
  /** Use the official AWS service icon instead of the neutral symbol. */
  aws?: AwsIconId
}

export type PipelineSpec = {
  id: string
  envs: PipeEnv[]
  steps: PipeStep[]
}

/**
 * Adapts a journey to the layered diagram the map tabs use, so every tab reads
 * as the same top-to-bottom flow: one dotted band per consecutive run of steps
 * sharing an environment, the steps in a row inside it, and a numbered
 * connector from each step to the next.
 */
export function pipelineToDiagram(spec: PipelineSpec): DiagramSpec {
  const envById = new Map(spec.envs.map((env) => [env.id, env]))

  type Group = { envId: string; steps: { step: PipeStep; index: number }[] }
  const groups: Group[] = []
  spec.steps.forEach((step, index) => {
    const last = groups[groups.length - 1]
    if (last && last.envId === step.env) last.steps.push({ step, index })
    else groups.push({ envId: step.env, steps: [{ step, index }] })
  })

  const bands: DiagramSpec['bands'] = groups.map((group, groupIndex) => {
    const env = envById.get(group.envId)
    const row: NodeSpec[] = group.steps.map(({ step, index }) => ({
      id: `${spec.id}-s${index}`,
      kind: step.kind,
      title: step.title,
      subtitle: step.subtitle,
      code: step.code,
      icon: step.icon,
      aws: step.aws,
      badge: index + 1,
    }))
    return {
      id: `${spec.id}-env-${groupIndex}`,
      title: env?.label ?? group.envId,
      hint: env?.hint,
      tone: env?.tone ?? 'neutral',
      rows: [row],
    }
  })

  const edges: DiagramSpec['edges'] = spec.steps.slice(0, -1).map((step, i) => {
    const next = spec.steps[i + 1]
    const env = envById.get(step.env)
    return {
      from: `${spec.id}-s${i}`,
      to: `${spec.id}-s${i + 1}`,
      tone: next.tone ?? step.tone ?? env?.tone ?? 'request',
    }
  })

  return { id: spec.id, bands, edges }
}
