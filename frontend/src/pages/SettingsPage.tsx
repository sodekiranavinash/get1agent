import { useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  Bell,
  Check,
  Globe,
  Loader2,
  Moon,
  Palette,
  Sun,
  User,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Switch } from '../components/ui/Switch'
import { useTheme } from '../theme/ThemeProvider'
import {
  useUserSettings,
  type ThemePreference,
  type UserSettings,
} from '../lib/userSettings'

const FALLBACK_TIMEZONES = [
  'UTC',
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Chicago',
  'America/Los_Angeles',
]

const inputStyles =
  'w-full rounded-xl border border-border-strong bg-raised px-3 py-2.5 text-sm text-foreground placeholder:text-subtle transition-colors focus:border-accent/40 focus:outline-none focus:ring-2 focus:ring-accent/25'

type Status = 'loading' | 'idle' | 'saving' | 'saved' | 'error'

export function SettingsPage() {
  const { setTheme } = useTheme()
  const { getSettings, updateSettings } = useUserSettings()
  const [form, setForm] = useState<UserSettings | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    getSettings()
      .then((data) => {
        if (!active) return
        setForm(data)
        setTheme(data.preferredTheme)
        setStatus('idle')
      })
      .catch((err: unknown) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load settings')
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [getSettings, setTheme])

  const timezoneOptions = useMemo(() => {
    const supported = (
      Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
    ).supportedValuesOf
    if (typeof supported === 'function') return supported('timeZone')
    return FALLBACK_TIMEZONES
  }, [])

  const timezoneList = useMemo(() => {
    if (!form || timezoneOptions.includes(form.timezone)) return timezoneOptions
    return [form.timezone, ...timezoneOptions]
  }, [form, timezoneOptions])

  const patch = (changes: Partial<UserSettings>) => {
    setForm((current) => (current ? { ...current, ...changes } : current))
    if (status === 'saved') setStatus('idle')
  }

  const handleThemeChange = (theme: ThemePreference) => {
    setTheme(theme)
    patch({ preferredTheme: theme })
  }

  const handleSave = async () => {
    if (!form) return
    setStatus('saving')
    setError('')
    try {
      const updated = await updateSettings({
        fullName: form.fullName,
        preferredTheme: form.preferredTheme,
        timezone: form.timezone,
        emailOnWorkflowFailure: form.emailOnWorkflowFailure,
        creditThresholdAlerts: form.creditThresholdAlerts,
      })
      setForm(updated)
      setTheme(updated.preferredTheme)
      setStatus('saved')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save settings')
      setStatus('error')
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Settings"
        description="Manage your profile, appearance, notifications and regional preferences."
        badge="Account"
        action={
          form
            ? {
                label: status === 'saving' ? 'Saving…' : 'Save changes',
                icon:
                  status === 'saving' ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  ),
                onClick: handleSave,
              }
            : undefined
        }
      />

      {status === 'error' ? (
        <div className="mb-6 flex items-start gap-3 rounded-2xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {status === 'saved' ? (
        <div className="mb-6 flex items-start gap-3 rounded-2xl border border-success/30 bg-success-soft px-4 py-3 text-sm text-success">
          <Check className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Your settings have been saved.</span>
        </div>
      ) : null}

      {status === 'loading' || !form ? (
        <div className="flex items-center gap-3 rounded-2xl border border-border bg-surface px-4 py-6 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading your settings…
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card padding="lg" className="lg:col-span-2">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-raised text-accent">
                <User className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-sm font-semibold text-foreground">Profile</h3>
                <p className="mt-1 text-xs text-muted">
                  This name is shown across your workspace.
                </p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1.5 block text-xs font-medium text-muted">
                      Full name
                    </span>
                    <input
                      type="text"
                      value={form.fullName ?? ''}
                      maxLength={255}
                      placeholder="Your full name"
                      onChange={(event) =>
                        patch({ fullName: event.target.value })
                      }
                      className={inputStyles}
                    />
                  </label>
                  <div className="block">
                    <span className="mb-1.5 block text-xs font-medium text-muted">
                      Email
                    </span>
                    <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-raised px-3 py-2.5">
                      <span className="truncate text-sm text-foreground">
                        {form.email}
                      </span>
                      {form.emailVerified ? (
                        <Badge variant="success" dot>
                          Verified
                        </Badge>
                      ) : (
                        <Badge variant="warning">Unverified</Badge>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Card>

          <Card padding="lg">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-raised text-accent">
                <Palette className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-sm font-semibold text-foreground">
                  Appearance
                </h3>
                <p className="mt-1 text-xs text-muted">
                  Choose how get1agent looks to you.
                </p>
                <div className="mt-4 inline-flex rounded-xl border border-border-strong bg-raised p-1">
                  {(['light', 'dark'] as const).map((option) => {
                    const active = form.preferredTheme === option
                    return (
                      <button
                        key={option}
                        type="button"
                        onClick={() => handleThemeChange(option)}
                        className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold capitalize transition-colors ${
                          active
                            ? 'bg-accent text-white shadow-control'
                            : 'text-muted hover:text-foreground'
                        }`}
                      >
                        {option === 'light' ? (
                          <Sun className="h-3.5 w-3.5" />
                        ) : (
                          <Moon className="h-3.5 w-3.5" />
                        )}
                        {option}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          </Card>

          <Card padding="lg">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-raised text-accent">
                <Globe className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-sm font-semibold text-foreground">
                  Language &amp; Region
                </h3>
                <p className="mt-1 text-xs text-muted">
                  Timezone used for schedules and reports.
                </p>
                <label className="mt-4 block">
                  <span className="mb-1.5 block text-xs font-medium text-muted">
                    Timezone
                  </span>
                  <select
                    value={form.timezone}
                    onChange={(event) =>
                      patch({ timezone: event.target.value })
                    }
                    className={inputStyles}
                  >
                    {timezoneList.map((timezone) => (
                      <option key={timezone} value={timezone}>
                        {timezone}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          </Card>

          <Card padding="lg" className="lg:col-span-2">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-raised text-accent">
                <Bell className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-sm font-semibold text-foreground">
                  Notifications
                </h3>
                <p className="mt-1 text-xs text-muted">
                  Choose which alerts we send to your inbox.
                </p>
                <div className="mt-4 space-y-4">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        Email on workflow failure
                      </p>
                      <p className="mt-0.5 text-xs text-muted">
                        Get notified when a scheduled workflow run fails.
                      </p>
                    </div>
                    <Switch
                      checked={form.emailOnWorkflowFailure}
                      onChange={(checked) =>
                        patch({ emailOnWorkflowFailure: checked })
                      }
                      label="Email on workflow failure"
                    />
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        Credit threshold alerts
                      </p>
                      <p className="mt-0.5 text-xs text-muted">
                        Get warned when your AI credits run low.
                      </p>
                    </div>
                    <Switch
                      checked={form.creditThresholdAlerts}
                      onChange={(checked) =>
                        patch({ creditThresholdAlerts: checked })
                      }
                      label="Credit threshold alerts"
                    />
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {form && status !== 'loading' ? (
        <div className="mt-6 flex justify-end">
          <Button
            size="lg"
            onClick={handleSave}
            disabled={status === 'saving'}
            icon={
              status === 'saving' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )
            }
          >
            {status === 'saving' ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      ) : null}
    </PageShell>
  )
}
