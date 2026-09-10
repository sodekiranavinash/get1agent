import { CreditCard, Eye, EyeOff, Key, TrendingUp, Zap } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardDescription, CardHeader, CardTitle } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { StatCard } from '../components/ui/StatCard'

export function UsagePage() {
  return (
    <PageShell>
      <PageHeader
        title="Usage"
        description="Manage API keys, monitor token usage, and review billing information."
        badge="Manage"
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Tokens This Month"
          value="842K"
          change="+12% vs last month"
          trend="up"
          icon={Zap}
          iconColor="text-warning"
        />
        <StatCard
          label="Credits Spent"
          value="$28.40"
          change="of $50 budget"
          trend="neutral"
          icon={TrendingUp}
          iconColor="text-info"
        />
        <StatCard
          label="Balance"
          value="$21.60"
          change="Renews Oct 1"
          trend="neutral"
          icon={CreditCard}
          iconColor="text-success"
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card padding="lg">
          <CardHeader>
            <div>
              <CardTitle>API Keys</CardTitle>
              <CardDescription>OpenRouter and other provider keys</CardDescription>
            </div>
            <Button variant="secondary" size="sm" icon={<Key className="h-4 w-4" />}>
              Add Key
            </Button>
          </CardHeader>

          <div className="space-y-3">
            <div className="rounded-xl border border-border bg-raised/50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-foreground">OpenRouter</p>
                  <p className="mt-1 font-mono text-xs text-muted">sk-or-••••••••••••4f2a</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="success" dot>
                    Active
                  </Badge>
                  <Button variant="ghost" size="sm" aria-label="Toggle key visibility">
                    <EyeOff className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-dashed border-border bg-raised/30 p-4 text-center">
              <Eye className="mx-auto h-5 w-5 text-subtle" strokeWidth={1.75} />
              <p className="mt-2 text-xs text-muted">Add additional provider keys as needed</p>
            </div>
          </div>
        </Card>

        <Card padding="lg">
          <CardHeader>
            <div>
              <CardTitle>Usage Breakdown</CardTitle>
              <CardDescription>Token consumption by model</CardDescription>
            </div>
          </CardHeader>

          <div className="space-y-4">
            {[
              { model: 'Claude Sonnet', pct: 45, tokens: '378K' },
              { model: 'GPT-4o', pct: 30, tokens: '252K' },
              { model: 'Gemini Pro', pct: 25, tokens: '212K' },
            ].map((item) => (
              <div key={item.model}>
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="font-medium text-foreground">{item.model}</span>
                  <span className="text-muted">{item.tokens}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-raised">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-accent to-info transition-all duration-500"
                    style={{ width: `${item.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          <Button variant="outline" size="sm" className="mt-6 w-full">
            View Billing History
          </Button>
        </Card>
      </div>
    </PageShell>
  )
}
