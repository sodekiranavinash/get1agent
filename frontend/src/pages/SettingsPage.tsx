import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  AlertCircle,
  Bell,
  Check,
  Coins,
  Globe2,
  MailWarning,
  Moon,
  Palette,
  Sun,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Spinner } from '../components/ui/Spinner'
import { Switch } from '../components/ui/Switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { useTheme } from '../theme/ThemeProvider'
import {
  useUserSettings,
  type ThemePreference,
  type UserSettings,
  type UserSettingsUpdate,
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

const inputStyles = 'field'

function initialsFor(name: string | null, email: string): string {
  const source = (name?.trim() || email || '?').trim()
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function PanelHeader({
  icon,
  title,
  description,
}: {
  icon: ReactNode
  title: string
  description?: string
}) {
  return (
    <div className="flex items-start gap-3 border-b border-border px-4 py-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
        {icon}
      </div>
      <div className="min-w-0">
        <h3 className="text-[13px] font-semibold text-foreground">{title}</h3>
        {description ? (
          <p className="mt-0.5 text-xs leading-relaxed text-muted">{description}</p>
        ) : null}
      </div>
    </div>
  )
}

function ToggleRow({
  icon,
  tone,
  title,
  description,
  checked,
  onChange,
}: {
  icon: ReactNode
  tone: 'info' | 'warning'
  title: string
  description: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  const toneStyles = {
    info: 'bg-info-soft text-info',
    warning: 'bg-warning-soft text-warning',
  }

  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3">
      <div className="flex min-w-0 items-start gap-3">
        <div
          className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${toneStyles[tone]}`}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-foreground">{title}</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">{description}</p>
        </div>
      </div>
      <Switch checked={checked} onChange={onChange} label={title} />
    </div>
  )
}

export function SettingsPage() {
  const { setTheme } = useTheme()
  const {
    data,
    error: loadError,
    isPending,
    refetch,
    updateSettings,
  } = useUserSettings()
  const [form, setForm] = useState<UserSettings | null>(null)
  const [baseline, setBaseline] = useState<UserSettings | null>(null)
  const [seededId, setSeededId] = useState<string | null>(null)
  const [saveStatus, setSaveStatus] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle')
  const [saveError, setSaveError] = useState('')

  if (data && data.id !== seededId) {
    setSeededId(data.id)
    setForm(data)
    setBaseline(data)
  }

  useEffect(() => {
    if (data) setTheme(data.preferredTheme)
  }, [data, setTheme])

  const isSaving = saveStatus === 'saving'
  const isSaved = saveStatus === 'saved'
  const errorMessage = loadError
    ? loadError.message
    : saveStatus === 'error'
      ? saveError
      : ''

  const isDirty = useMemo(() => {
    if (!form || !baseline) return false
    return (
      (form.fullName ?? '') !== (baseline.fullName ?? '') ||
      form.preferredTheme !== baseline.preferredTheme ||
      form.timezone !== baseline.timezone ||
      form.emailOnWorkflowFailure !== baseline.emailOnWorkflowFailure ||
      form.creditThresholdAlerts !== baseline.creditThresholdAlerts
    )
  }, [form, baseline])

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
    if (saveStatus === 'saved') setSaveStatus('idle')
  }

  const handleThemeChange = (theme: ThemePreference) => {
    setTheme(theme)
    patch({ preferredTheme: theme })
  }

  const handleSave = async () => {
    if (!form || !baseline) return

    const update: UserSettingsUpdate = {}
    if ((form.fullName ?? '') !== (baseline.fullName ?? '')) {
      update.fullName = form.fullName
    }
    if (form.preferredTheme !== baseline.preferredTheme) {
      update.preferredTheme = form.preferredTheme
    }
    if (form.timezone !== baseline.timezone) {
      update.timezone = form.timezone
    }
    if (form.emailOnWorkflowFailure !== baseline.emailOnWorkflowFailure) {
      update.emailOnWorkflowFailure = form.emailOnWorkflowFailure
    }
    if (form.creditThresholdAlerts !== baseline.creditThresholdAlerts) {
      update.creditThresholdAlerts = form.creditThresholdAlerts
    }

    setSaveStatus('saving')
    setSaveError('')
    try {
      const updated =
        Object.keys(update).length > 0 ? await updateSettings(update) : form
      setForm(updated)
      setBaseline(updated)
      setSeededId(updated.id)
      setTheme(updated.preferredTheme)
      setSaveStatus('saved')
      toast.success('Settings saved')
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to save settings'
      setSaveError(message)
      setSaveStatus('error')
      toast.error('Could not save settings', { description: message })
    }
  }

  if (isPending) {
    return (
      <PageShell>
        <div className="mb-5 space-y-2">
          <div className="skeleton h-5 w-32" />
          <div className="skeleton h-3.5 w-80 max-w-full" />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="skeleton h-40 rounded-lg lg:col-span-2" />
          <div className="skeleton h-44 rounded-lg" />
          <div className="skeleton h-44 rounded-lg" />
        </div>
      </PageShell>
    )
  }

  if (loadError) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState
            title="Couldn't load settings"
            error={loadError}
            onRetry={refetch}
          />
        </div>
      </PageShell>
    )
  }

  if (!form) {
    return null
  }

  return (
    <PageShell>
      <PageHeader
        title="Settings"
        description="Manage your profile, appearance, notifications and regional preferences."
        action={{
          label: isSaving ? 'Saving…' : isSaved ? 'Saved' : 'Save changes',
          icon: isSaving ? (
            <Spinner size="xs" />
          ) : (
            <Check className="h-3.5 w-3.5" />
          ),
          onClick: handleSave,
          disabled: !isDirty || isSaving,
        }}
      />

      {errorMessage ? (
        <div className="mb-3 flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning-soft px-3.5 py-2.5 text-[13px] text-warning">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="grid gap-3 lg:grid-cols-2"
      >
        <Card padding="none" className="overflow-hidden lg:col-span-2">
          <div className="flex flex-col gap-4 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3.5">
              {form.pictureUrl ? (
                <img
                  src={form.pictureUrl}
                  alt=""
                  referrerPolicy="no-referrer"
                  className="h-12 w-12 rounded-lg border border-border object-cover"
                />
              ) : (
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent text-base font-semibold text-white">
                  {initialsFor(form.fullName, form.email)}
                </div>
              )}
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-foreground">
                  {form.fullName || 'Add your name'}
                </h2>
                <p className="truncate text-xs text-muted">{form.email}</p>
                <div className="mt-1.5">
                  {form.emailVerified ? (
                    <Badge variant="success" dot>
                      Email verified
                    </Badge>
                  ) : (
                    <Badge variant="warning">Email unverified</Badge>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted">
                Full name
              </span>
              <input
                type="text"
                value={form.fullName ?? ''}
                maxLength={255}
                placeholder="Your full name"
                onChange={(event) => patch({ fullName: event.target.value })}
                className={inputStyles}
              />
            </label>
            <div className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted">Email</span>
              <div className="flex h-9 items-center justify-between gap-3 rounded-md border border-border bg-raised px-3">
                <span className="truncate text-[13px] text-foreground">{form.email}</span>
                <span className="shrink-0 text-[10px] font-medium tracking-wide text-subtle uppercase">
                  SSO
                </span>
              </div>
            </div>
          </div>
        </Card>

        <Card padding="none" className="overflow-hidden">
          <PanelHeader
            icon={<Palette className="h-3.5 w-3.5" strokeWidth={1.75} />}
            title="Appearance"
            description="Choose how get1agent looks to you."
          />
          <div className="grid grid-cols-2 gap-3 p-4">
            {(['light', 'dark'] as const).map((option) => {
              const active = form.preferredTheme === option
              const isLight = option === 'light'
              return (
                <button
                  key={option}
                  type="button"
                  aria-pressed={active}
                  onClick={() => handleThemeChange(option)}
                  className={`rounded-md border p-2 text-left transition-colors ${
                    active
                      ? 'border-accent/50 bg-accent-soft'
                      : 'border-border bg-raised/40 hover:border-border-strong hover:bg-raised'
                  }`}
                >
                  <div
                    className={`h-16 overflow-hidden rounded border p-2 ${
                      isLight
                        ? 'border-zinc-200 bg-white'
                        : 'border-white/10 bg-[#0e0e12]'
                    }`}
                  >
                    <div
                      className={`h-1.5 w-8 rounded-full ${
                        isLight ? 'bg-zinc-300' : 'bg-zinc-700'
                      }`}
                    />
                    <div className="mt-2 flex gap-1.5">
                      <div
                        className={`h-9 w-1/3 rounded ${
                          isLight ? 'bg-zinc-100' : 'bg-white/5'
                        }`}
                      />
                      <div className="flex-1 space-y-1.5">
                        <div
                          className={`h-3 rounded ${
                            isLight ? 'bg-zinc-100' : 'bg-white/5'
                          }`}
                        />
                        <div
                          className={`h-4 rounded ${
                            isLight ? 'bg-[#ea580c]/15' : 'bg-[#ff6d5a]/20'
                          }`}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between px-0.5">
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground capitalize">
                      {isLight ? (
                        <Sun className="h-3.5 w-3.5" />
                      ) : (
                        <Moon className="h-3.5 w-3.5" />
                      )}
                      {option}
                    </span>
                    {active ? (
                      <Check className="h-3.5 w-3.5 text-accent" strokeWidth={2.5} />
                    ) : null}
                  </div>
                </button>
              )
            })}
          </div>
        </Card>

        <Card padding="none" className="overflow-hidden">
          <PanelHeader
            icon={<Globe2 className="h-3.5 w-3.5" strokeWidth={1.75} />}
            title="Language & region"
            description="Timezone used for schedules and reports."
          />
          <div className="p-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted">Timezone</span>
              <Select
                value={form.timezone}
                onValueChange={(value) => patch({ timezone: value })}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Select timezone" />
                </SelectTrigger>
                <SelectContent>
                  {timezoneList.map((timezone) => (
                    <SelectItem key={timezone} value={timezone}>
                      {timezone}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <p className="mt-2 text-xs text-subtle">
              Schedules run in {form.timezone}.
            </p>
          </div>
        </Card>

        <Card padding="none" className="overflow-hidden lg:col-span-2">
          <PanelHeader
            icon={<Bell className="h-3.5 w-3.5" strokeWidth={1.75} />}
            title="Notifications"
            description="Choose which alerts we send to your inbox."
          />
          <div className="divide-y divide-border">
            <ToggleRow
              icon={<MailWarning className="h-3.5 w-3.5" />}
              tone="info"
              title="Email on workflow failure"
              description="Get notified when a scheduled workflow run fails."
              checked={form.emailOnWorkflowFailure}
              onChange={(checked) => patch({ emailOnWorkflowFailure: checked })}
            />
            <ToggleRow
              icon={<Coins className="h-3.5 w-3.5" />}
              tone="warning"
              title="Credit threshold alerts"
              description="Get warned when your AI credits run low."
              checked={form.creditThresholdAlerts}
              onChange={(checked) => patch({ creditThresholdAlerts: checked })}
            />
          </div>
        </Card>
      </motion.div>
    </PageShell>
  )
}
