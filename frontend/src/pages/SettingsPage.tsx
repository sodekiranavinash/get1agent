import { Bell, Globe, Moon, Palette, Shield } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { useTheme } from '../theme/ThemeProvider'

const settingsSections = [
  {
    icon: Palette,
    title: 'Appearance',
    description: 'Theme, density, and accent preferences',
    items: ['Dark / Light mode', 'Compact sidebar'],
  },
  {
    icon: Bell,
    title: 'Notifications',
    description: 'Workflow alerts and usage warnings',
    items: ['Email on workflow failure', 'Credit threshold alerts'],
  },
  {
    icon: Globe,
    title: 'Language & Region',
    description: 'Locale and timezone settings',
    items: ['English (US)', 'UTC+5:30'],
  },
  {
    icon: Shield,
    title: 'Security',
    description: 'Session and access controls',
    items: ['Two-factor authentication', 'Active sessions'],
  },
]

export function SettingsPage() {
  const { theme } = useTheme()

  return (
    <PageShell>
      <PageHeader
        title="Settings"
        description="Customize your workspace preferences and account options."
        badge="Account"
      />

      <div className="mb-6 flex items-center gap-3 rounded-2xl border border-border bg-accent-soft/50 px-4 py-3">
        <Moon className="h-5 w-5 text-accent" strokeWidth={1.75} />
        <div className="flex-1">
          <p className="text-sm font-medium text-foreground">Current theme</p>
          <p className="text-xs text-muted capitalize">{theme} mode active</p>
        </div>
        <Badge variant="accent">{theme}</Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {settingsSections.map(({ icon: Icon, title, description, items }) => (
          <Card key={title} hover padding="lg">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-raised text-accent">
                <Icon className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-foreground">{title}</h3>
                <p className="mt-1 text-xs text-muted">{description}</p>
                <ul className="mt-3 space-y-1.5">
                  {items.map((item) => (
                    <li key={item} className="flex items-center gap-2 text-xs text-muted">
                      <span className="h-1 w-1 rounded-full bg-accent" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </PageShell>
  )
}
