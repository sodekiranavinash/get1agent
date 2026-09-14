import { motion } from 'framer-motion'
import { CreditCard, Eye, EyeOff, Key, TrendingUp, Zap } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Progress } from '../components/ui/progress'
import { StatCard } from '../components/ui/StatCard'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { fadeUp, stagger } from '../lib/motion'

const kpis = [
  {
    label: 'Tokens this month',
    value: '842K',
    change: '+12% vs last month',
    trend: 'up' as const,
    icon: Zap,
    iconColor: 'text-warning',
    spark: [520, 560, 600, 640, 700, 780, 842],
  },
  {
    label: 'Credits spent',
    value: '$28.40',
    change: 'of $50 budget',
    trend: 'neutral' as const,
    icon: TrendingUp,
    iconColor: 'text-info',
    spark: [8, 12, 15, 19, 22, 25, 28],
  },
  {
    label: 'Balance',
    value: '$21.60',
    change: 'Renews Oct 1',
    trend: 'neutral' as const,
    icon: CreditCard,
    iconColor: 'text-success',
    spark: [40, 36, 33, 30, 27, 24, 21.6],
  },
]

const breakdown = [
  { model: 'Claude Sonnet', pct: 45, tokens: '378K' },
  { model: 'GPT-4o', pct: 30, tokens: '252K' },
  { model: 'Gemini Pro', pct: 25, tokens: '212K' },
]

const invoices = [
  { id: 'INV-2049', date: 'Sep 1, 2026', amount: '$50.00', status: 'Paid' },
  { id: 'INV-2041', date: 'Aug 1, 2026', amount: '$50.00', status: 'Paid' },
  { id: 'INV-2033', date: 'Jul 1, 2026', amount: '$25.00', status: 'Paid' },
]

export function UsagePage() {
  return (
    <PageShell>
      <PageHeader
        title="Usage"
        description="Manage API keys, monitor token usage, and review billing information."
      />

      <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          {kpis.map((kpi) => (
            <motion.div key={kpi.label} variants={fadeUp}>
              <StatCard {...kpi} />
            </motion.div>
          ))}
        </div>

        <motion.div variants={fadeUp}>
          <Tabs defaultValue="overview">
            <div className="flex items-center justify-between">
              <TabsList>
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="billing">Billing</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="overview">
              <div className="grid gap-3 lg:grid-cols-2">
                <Card padding="none" className="overflow-hidden">
                  <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
                    <div>
                      <h2 className="text-[13px] font-semibold text-foreground">API keys</h2>
                      <p className="mt-0.5 text-xs text-muted">
                        OpenRouter and other provider keys
                      </p>
                    </div>
                    <Button variant="outline" size="sm" icon={<Key className="size-3.5" />}>
                      Add key
                    </Button>
                  </div>
                  <div className="divide-y divide-border">
                    <div className="flex items-center gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-medium text-foreground">OpenRouter</p>
                        <p className="mt-0.5 font-mono text-xs text-muted">
                          sk-or-••••••••••••4f2a
                        </p>
                      </div>
                      <Badge variant="success" dot>
                        Active
                      </Badge>
                      <button
                        type="button"
                        aria-label="Toggle key visibility"
                        className="rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-foreground"
                      >
                        <EyeOff className="size-3.5" />
                      </button>
                    </div>
                    <div className="flex items-center gap-3 px-4 py-3 text-xs text-muted">
                      <Eye className="size-4 shrink-0 text-subtle" strokeWidth={1.75} />
                      Add additional provider keys as needed
                    </div>
                  </div>
                </Card>

                <Card padding="none" className="overflow-hidden">
                  <div className="border-b border-border px-4 py-2.5">
                    <h2 className="text-[13px] font-semibold text-foreground">
                      Usage breakdown
                    </h2>
                    <p className="mt-0.5 text-xs text-muted">Token consumption by model</p>
                  </div>
                  <div className="space-y-4 p-4">
                    {breakdown.map((item) => (
                      <div key={item.model}>
                        <div className="mb-1.5 flex items-center justify-between text-xs">
                          <span className="font-medium text-foreground">{item.model}</span>
                          <span className="text-muted">{item.tokens}</span>
                        </div>
                        <Progress value={item.pct} />
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="billing">
              <Card padding="none" className="overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[520px] text-left">
                    <thead>
                      <tr className="border-b border-border bg-raised/40">
                        {['Invoice', 'Date', 'Amount', 'Status', ''].map((header) => (
                          <th
                            key={header}
                            className="px-4 py-2.5 text-[11px] font-semibold text-muted"
                          >
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {invoices.map((invoice) => (
                        <tr
                          key={invoice.id}
                          className="transition-colors hover:bg-raised/40"
                        >
                          <td className="px-4 py-3 font-mono text-xs text-foreground">
                            {invoice.id}
                          </td>
                          <td className="px-4 py-3 text-xs text-muted">{invoice.date}</td>
                          <td className="px-4 py-3 text-xs text-foreground">
                            {invoice.amount}
                          </td>
                          <td className="px-4 py-3">
                            <Badge variant="success" dot>
                              {invoice.status}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <Button variant="ghost" size="sm">
                              Download
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </TabsContent>
          </Tabs>
        </motion.div>
      </motion.div>
    </PageShell>
  )
}
