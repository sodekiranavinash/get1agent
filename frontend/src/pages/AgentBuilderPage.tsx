import { Bot, Plus, Sparkles, Wrench } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

const models = ['Claude Sonnet 4', 'GPT-4o', 'Gemini 2.0 Pro', 'DeepSeek R1']
const reasoningLevels = ['Low', 'Medium', 'High']
const defaultTools = [
  { name: 'Web Search', icon: Sparkles },
  { name: 'Code Interpreter', icon: Wrench },
]

export function AgentBuilderPage() {
  return (
    <PageShell>
      <PageHeader
        title="Agent Builder"
        description="Design custom agents with prompts, models, reasoning effort, and default tools."
        badge="Build"
        action={{ label: 'Save Agent', icon: <Plus className="h-4 w-4" /> }}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Card padding="lg" className="gradient-border">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
              <Bot className="h-5 w-5" strokeWidth={1.75} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">Agent Configuration</h2>
              <p className="text-xs text-muted">Define behavior, model, and capabilities</p>
            </div>
          </div>

          <div className="space-y-5">
            <div>
              <label className="mb-2 block text-xs font-semibold tracking-wide text-muted uppercase">
                Agent Name
              </label>
              <div className="h-11 animate-shimmer rounded-xl border border-border" />
            </div>

            <div>
              <label className="mb-2 block text-xs font-semibold tracking-wide text-muted uppercase">
                System Prompt
              </label>
              <div className="h-32 animate-shimmer rounded-xl border border-border" />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-2 block text-xs font-semibold tracking-wide text-muted uppercase">
                  Model
                </label>
                <div className="flex flex-wrap gap-2">
                  {models.map((model, i) => (
                    <Badge key={model} variant={i === 0 ? 'accent' : 'default'}>
                      {model}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-2 block text-xs font-semibold tracking-wide text-muted uppercase">
                  Reasoning Effort
                </label>
                <div className="flex gap-2">
                  {reasoningLevels.map((level, i) => (
                    <Badge key={level} variant={i === 1 ? 'accent' : 'default'}>
                      {level}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          <Card padding="md">
            <h3 className="text-sm font-semibold text-foreground">Default Tools</h3>
            <p className="mt-1 text-xs text-muted">Attach tools available on every run</p>
            <div className="mt-4 space-y-2">
              {defaultTools.map(({ name, icon: Icon }) => (
                <div
                  key={name}
                  className="flex items-center justify-between rounded-xl border border-border bg-raised/50 px-3 py-2.5"
                >
                  <div className="flex items-center gap-2.5">
                    <Icon className="h-4 w-4 text-accent" strokeWidth={1.75} />
                    <span className="text-sm text-foreground">{name}</span>
                  </div>
                  <Badge variant="success" dot>
                    attached
                  </Badge>
                </div>
              ))}
            </div>
            <Button variant="outline" size="sm" className="mt-4 w-full">
              Add Tool
            </Button>
          </Card>

          <Card padding="md" glow>
            <Badge variant="accent" className="mb-3">
              Preview
            </Badge>
            <p className="text-sm leading-relaxed text-muted">
              Full agent builder with live preview, tool picker, and prompt templates is coming soon.
            </p>
          </Card>
        </div>
      </div>
    </PageShell>
  )
}
