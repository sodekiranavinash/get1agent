import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  AlertCircle,
  Bell,
  Check,
  ChevronDown,
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
import { SettingsSkeleton } from '../components/ui/Skeleton'
import { Spinner } from '../components/ui/Spinner'
import { Switch } from '../components/ui/Switch'
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

const inputStyles =
  'w-full rounded-xl border border-border-strong bg-raised px-3 py-2.5 text-sm text-foreground placeholder:text-subtle transition-colors focus:border-accent/40 focus:outline-none focus:ring-2 focus:ring-accent/25'

const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
}

function initialsFor(name: string | null, email: string): string {
  const source = (name?.trim() || email || '?').trim()
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function SectionHeading({
  icon,
  title,
  description,
}: {
  icon: ReactNode
  title: string
  description: string
}) {
  return (
    <div className="flex items-start gap-3.5">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border bg-raised text-accent">
        {icon}
      </div>
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="mt-1 text-xs leading-relaxed text-muted">{description}</p>
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
    <div className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0">
      <div className="flex min-w-0 items-start gap-3">
        <div
          className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${toneStyles[tone]}`}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{title}</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            {description}
          </p>
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

    // Only send the fields the user actually changed. Everything else
    // (id, email, emailVerified, pictureUrl, …) is owned by the backend and
    // derived from the Auth0 token — it is never user-editable.
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
    } catch (err: unknown) {
      setSaveError(
        err instanceof Error ? err.message : 'Failed to save settings',
      )
      setSaveStatus('error')
    }
  }

  if (isPending) {
    return (
      <PageShell>
        <SettingsSkeleton />
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
        badge="Account"
        action={
          form
            ? {
                label: isSaving ? 'Saving…' : isSaved ? 'Saved' : 'Save changes',
                icon: isSaving ? (
                  <Spinner size="xs" />
                ) : (
                  <Check className="h-4 w-4" />
                ),
                onClick: handleSave,
                disabled: !isDirty || isSaving,
              }
            : undefined
        }
      />

      {errorMessage ? (
        <div className="mb-6 flex items-start gap-3 rounded-2xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      <>
        <div className="grid gap-4 lg:grid-cols-2">
            <motion.div
              {...fadeUp}
              transition={{ duration: 0.35, delay: 0.02 }}
              className="lg:col-span-2"
            >
              <Card padding="lg">
                <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-4">
                    <div className="relative">
                      {form.pictureUrl ? (
                        <img
                          src={form.pictureUrl}
                          alt=""
                          referrerPolicy="no-referrer"
                          className="h-16 w-16 rounded-2xl object-cover ring-1 ring-border-strong"
                        />
                      ) : (
                        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-accent to-info text-xl font-bold text-white shadow-glow">
                          {initialsFor(form.fullName, form.email)}
                        </div>
                      )}
                      {form.emailVerified ? (
                        <span className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full border-2 border-surface bg-success">
                          <Check
                            className="h-3 w-3 text-white"
                            strokeWidth={3}
                          />
                        </span>
                      ) : null}
                    </div>
                    <div className="min-w-0">
                      <h2 className="truncate text-lg font-semibold text-foreground">
                        {form.fullName || 'Add your name'}
                      </h2>
                      <p className="truncate text-sm text-muted">{form.email}</p>
                      <div className="mt-2">
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

                <div className="mt-6 grid gap-4 border-t border-border pt-6 sm:grid-cols-2">
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
                      <span className="shrink-0 text-[11px] font-medium uppercase tracking-wide text-subtle">
                        Managed by SSO
                      </span>
                    </div>
                  </div>
                </div>
              </Card>
            </motion.div>

            <motion.div {...fadeUp} transition={{ duration: 0.35, delay: 0.06 }}>
              <Card padding="lg" className="h-full">
                <SectionHeading
                  icon={<Palette className="h-5 w-5" strokeWidth={1.75} />}
                  title="Appearance"
                  description="Choose how get1agent looks to you."
                />
                <div className="mt-4 grid grid-cols-2 gap-3">
                  {(['light', 'dark'] as const).map((option) => {
                    const active = form.preferredTheme === option
                    const isLight = option === 'light'
                    return (
                      <button
                        key={option}
                        type="button"
                        aria-pressed={active}
                        onClick={() => handleThemeChange(option)}
                        className={`group rounded-xl border p-2.5 text-left transition-all duration-200 ${
                          active
                            ? 'border-accent/60 bg-accent-soft ring-1 ring-accent/40'
                            : 'border-border-strong bg-raised hover:border-accent/30 hover:bg-elevated'
                        }`}
                      >
                        <div
                          className={`relative h-20 overflow-hidden rounded-lg border p-2.5 ${
                            isLight
                              ? 'border-zinc-200 bg-white'
                              : 'border-white/10 bg-[#0e0e12]'
                          }`}
                        >
                          <div
                            className={`h-1.5 w-10 rounded-full ${
                              isLight ? 'bg-zinc-300' : 'bg-zinc-700'
                            }`}
                          />
                          <div className="mt-2 flex gap-1.5">
                            <div
                              className={`h-12 w-1/3 rounded-md ${
                                isLight ? 'bg-zinc-100' : 'bg-white/5'
                              }`}
                            />
                            <div className="flex-1 space-y-1.5">
                              <div
                                className={`h-4 rounded-md ${
                                  isLight ? 'bg-zinc-100' : 'bg-white/5'
                                }`}
                              />
                              <div
                                className={`h-6 rounded-md ${
                                  isLight ? 'bg-[#ea580c]/15' : 'bg-[#ff6d5a]/20'
                                }`}
                              />
                            </div>
                          </div>
                        </div>
                        <div className="mt-2.5 flex items-center justify-between px-0.5">
                          <span className="inline-flex items-center gap-1.5 text-xs font-semibold capitalize text-foreground">
                            {isLight ? (
                              <Sun className="h-3.5 w-3.5" />
                            ) : (
                              <Moon className="h-3.5 w-3.5" />
                            )}
                            {option}
                          </span>
                          {active ? (
                            <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-accent text-white">
                              <Check
                                className="h-2.5 w-2.5"
                                strokeWidth={3}
                              />
                            </span>
                          ) : null}
                        </div>
                      </button>
                    )
                  })}
                </div>
              </Card>
            </motion.div>

            <motion.div {...fadeUp} transition={{ duration: 0.35, delay: 0.1 }}>
              <Card padding="lg" className="h-full">
                <SectionHeading
                  icon={<Globe2 className="h-5 w-5" strokeWidth={1.75} />}
                  title="Language & Region"
                  description="Timezone used for schedules and reports."
                />
                <label className="mt-4 block">
                  <span className="mb-1.5 block text-xs font-medium text-muted">
                    Timezone
                  </span>
                  <div className="relative">
                    <select
                      value={form.timezone}
                      onChange={(event) =>
                        patch({ timezone: event.target.value })
                      }
                      className={`${inputStyles} appearance-none pr-10`}
                    >
                      {timezoneList.map((timezone) => (
                        <option key={timezone} value={timezone}>
                          {timezone}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
                  </div>
                </label>
                <p className="mt-2 text-xs text-subtle">
                  Schedules run in {form.timezone}.
                </p>
              </Card>
            </motion.div>

            <motion.div
              {...fadeUp}
              transition={{ duration: 0.35, delay: 0.14 }}
              className="lg:col-span-2"
            >
              <Card padding="lg">
                <SectionHeading
                  icon={<Bell className="h-5 w-5" strokeWidth={1.75} />}
                  title="Notifications"
                  description="Choose which alerts we send to your inbox."
                />
                <div className="mt-4 divide-y divide-border">
                  <ToggleRow
                    icon={<MailWarning className="h-4 w-4" />}
                    tone="info"
                    title="Email on workflow failure"
                    description="Get notified when a scheduled workflow run fails."
                    checked={form.emailOnWorkflowFailure}
                    onChange={(checked) =>
                      patch({ emailOnWorkflowFailure: checked })
                    }
                  />
                  <ToggleRow
                    icon={<Coins className="h-4 w-4" />}
                    tone="warning"
                    title="Credit threshold alerts"
                    description="Get warned when your AI credits run low."
                    checked={form.creditThresholdAlerts}
                    onChange={(checked) =>
                      patch({ creditThresholdAlerts: checked })
                    }
                  />
                </div>
              </Card>
            </motion.div>
          </div>
      </>
    </PageShell>
  )
}
