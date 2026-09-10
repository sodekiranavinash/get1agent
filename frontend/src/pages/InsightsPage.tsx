import { Bot, TrendingUp, Workflow, Zap } from 'lucide-react'
import { Card, CardDescription, CardHeader, CardTitle } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { StatCard } from '../components/ui/StatCard'

const weeklyTokens = [62, 74, 68, 91, 84, 96, 88]
const workflowRuns = [12, 18, 15, 22, 19, 24, 21]

export function InsightsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Insights"
        description="Track usage trends, workflow performance, and agent activity over time."
        badge="Manage"
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Avg. Daily Tokens"
          value="118K"
          change="+9% vs last week"
          trend="up"
          icon={Zap}
          iconColor="text-warning"
        />
        <StatCard
          label="Workflow Success Rate"
          value="94%"
          change="+2% vs last week"
          trend="up"
          icon={Workflow}
          iconColor="text-info"
        />
        <StatCard
          label="Active Agents"
          value="12"
          change="3 ran today"
          trend="neutral"
          icon={Bot}
        />
        <StatCard
          label="Cost Trend"
          value="$4.20/day"
          change="-6% vs last week"
          trend="down"
          icon={TrendingUp}
          iconColor="text-success"
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card padding="lg">
          <CardHeader>
            <div>
              <CardTitle>Token Usage</CardTitle>
              <CardDescription>Daily token consumption over the last 7 days</CardDescription>
            </div>
          </CardHeader>

          <div className="flex h-44 items-end gap-2">
            {weeklyTokens.map((value, index) => (
              <div key={index} className="flex flex-1 flex-col items-center gap-2">
                <div
                  className="w-full rounded-t-md bg-gradient-to-t from-accent/70 to-accent"
                  style={{ height: `${value}%` }}
                />
                <span className="text-[10px] text-muted">
                  {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][index]}
                </span>
              </div>
            ))}
          </div>
        </Card>

        <Card padding="lg">
          <CardHeader>
            <div>
              <CardTitle>Workflow Runs</CardTitle>
              <CardDescription>Completed runs per day over the last 7 days</CardDescription>
            </div>
          </CardHeader>

          <div className="flex h-44 items-end gap-2">
            {workflowRuns.map((value, index) => (
              <div key={index} className="flex flex-1 flex-col items-center gap-2">
                <div
                  className="w-full rounded-t-md bg-gradient-to-t from-info/70 to-info"
                  style={{ height: `${(value / 24) * 100}%` }}
                />
                <span className="text-[10px] text-muted">
                  {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][index]}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </PageShell>
  )
}
