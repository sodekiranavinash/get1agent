import { useEffect, useState, type ReactNode } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  Mail,
  ScrollText,
  ShieldCheck,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { useApiClient } from '../lib/api'
import { useDemoMode } from '../auth/useDemoMode'
import { usePageQuery } from '../hooks/usePageQuery'
import {
  CONSENT_QUERY_KEY,
  GRIEVANCE_QUERY_KEY,
  GRIEVANCE_REQUEST_TYPES,
  createGrievance,
  deleteAccount,
  downloadJson,
  exportUserData,
  fetchConsent,
  fetchGrievances,
  recordConsent,
  withdrawConsent,
} from '../lib/privacy'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Spinner } from '../components/ui/Spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'

function SectionCard({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <Card padding="none" className="overflow-hidden">
      <div className="flex items-start gap-3 border-b border-border px-4 py-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
          {icon}
        </span>
        <div className="min-w-0">
          <h2 className="text-[13px] font-semibold text-foreground">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-xs leading-relaxed text-muted">{description}</p>
          ) : null}
        </div>
      </div>
      <div className="p-4">{children}</div>
    </Card>
  )
}

export function DataRightsPage() {
  const api = useApiClient()
  const { isAuthenticated, logout } = useAuth0()
  const demo = useDemoMode()
  const canUse = isAuthenticated && !demo

  const consent = usePageQuery(CONSENT_QUERY_KEY, () => fetchConsent(api), {
    enabled: canUse,
  })
  const grievances = usePageQuery(
    GRIEVANCE_QUERY_KEY,
    () => fetchGrievances(api),
    { enabled: canUse },
  )

  const purposes = consent.data?.purposes ?? []
  const contact = consent.data?.contact ?? grievances.data?.contact

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [adult, setAdult] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [deleting, setDeleting] = useState(false)

  const current = consent.data?.consent ?? null
  const accepted = Boolean(current && !current.withdrawnAt)

  // Seed the selection from the server whenever neither has been touched.
  useEffect(() => {
    if (!consent.data) return
    const existing = consent.data.consent
    if (existing && !existing.withdrawnAt) {
      setSelected(new Set(existing.purposes))
      setAdult(existing.adultConfirmed)
    } else {
      setSelected(
        new Set(consent.data.purposes.filter((p) => p.required).map((p) => p.id)),
      )
    }
  }, [consent.data])

  const requiredIds = purposes.filter((p) => p.required).map((p) => p.id)
  const allRequiredChosen = requiredIds.every((id) => selected.has(id))

  function togglePurpose(id: string, required: boolean) {
    if (required) return
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleAccept() {
    if (!adult) {
      toast.error('Please confirm you are 18 or older.')
      return
    }
    if (!allRequiredChosen) {
      toast.error('Please accept the required purposes to continue.')
      return
    }
    setSaving(true)
    try {
      await recordConsent(api, {
        purposes: Array.from(selected),
        adultConfirmed: true,
        language: navigator.language?.slice(0, 2) || 'en',
      })
      toast.success('Your consent has been recorded.')
      consent.refetch()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save consent')
    } finally {
      setSaving(false)
    }
  }

  async function handleWithdraw() {
    setSaving(true)
    try {
      await withdrawConsent(api)
      toast.success('Consent withdrawn. You can now close your account to erase your data.')
      consent.refetch()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not withdraw consent')
    } finally {
      setSaving(false)
    }
  }

  async function handleExport() {
    setExporting(true)
    try {
      const bundle = await exportUserData(api)
      const stamp = new Date().toISOString().slice(0, 10)
      downloadJson(`get1agent-data-export-${stamp}.json`, bundle)
      toast.success('Your data export has been downloaded.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not export your data')
    } finally {
      setExporting(false)
    }
  }

  async function handleDelete() {
    if (deleteConfirm.trim().toUpperCase() !== 'DELETE') {
      toast.error('Type DELETE to confirm.')
      return
    }
    setDeleting(true)
    try {
      await deleteAccount(api)
      toast.success('Your account and data have been erased.')
      // The identity is gone; sign out and return to the entry screen.
      logout({ logoutParams: { returnTo: window.location.origin } })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete your account')
      setDeleting(false)
      setDeleteOpen(false)
    }
  }

  // --- grievance form --------------------------------------------------------
  const [requestType, setRequestType] = useState<string>('access')
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleGrievance() {
    if (!subject.trim() || !message.trim()) {
      toast.error('Please add a subject and a description.')
      return
    }
    setSubmitting(true)
    try {
      await createGrievance(api, { subject, message, requestType })
      toast.success('Your request has been logged.')
      setSubject('')
      setMessage('')
      grievances.refetch()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not submit your request')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Privacy & data rights"
        description="Your rights under the Digital Personal Data Protection Act, 2023 — access, correction, erasure, consent and grievance redressal."
        badge="Privacy"
      />

      {!canUse ? (
        <Card padding="none" className="max-w-3xl p-5">
          <p className="text-[13px] leading-relaxed text-muted">
            {demo
              ? 'This is a read-only demo. Sign in to manage your consent, download your data, or close your account.'
              : 'Sign in to manage your consent, download your data, or close your account.'}
          </p>
          <Link
            to="/privacy"
            className="mt-3 inline-block text-[13px] font-medium text-accent hover:underline"
          >
            Read the privacy notice
          </Link>
        </Card>
      ) : (
        <div className="max-w-3xl space-y-3">
          {/* Consent --------------------------------------------------------- */}
          <SectionCard
            icon={<ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.75} />}
            title="Consent"
            description="Consent must be free, specific and informed. Withdraw it at any time."
          >
            {consent.isPending ? (
              <Spinner size="sm" />
            ) : (
              <div className="space-y-3">
                <ul className="space-y-2">
                  {purposes.map((purpose) => {
                    const active = selected.has(purpose.id)
                    return (
                      <li
                        key={purpose.id}
                        className="flex items-start gap-3 rounded-md border border-border bg-raised/40 p-3"
                      >
                        <input
                          id={`purpose-${purpose.id}`}
                          type="checkbox"
                          checked={active}
                          disabled={purpose.required}
                          onChange={() => togglePurpose(purpose.id, purpose.required)}
                          className="mt-0.5 h-4 w-4 shrink-0"
                          style={{ accentColor: 'var(--app-accent)' }}
                        />
                        <label htmlFor={`purpose-${purpose.id}`} className="min-w-0">
                          <span className="flex flex-wrap items-center gap-2 text-[13px] font-medium text-foreground">
                            {purpose.title}
                            {purpose.required ? (
                              <span className="rounded-full border border-border-strong px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-subtle uppercase">
                                Required
                              </span>
                            ) : (
                              <span className="text-[10px] font-medium tracking-wide text-subtle uppercase">
                                Optional
                              </span>
                            )}
                          </span>
                          <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                            {purpose.description}
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>

                <label className="flex items-start gap-3 rounded-md border border-border bg-raised/40 p-3">
                  <input
                    type="checkbox"
                    checked={adult}
                    onChange={(event) => setAdult(event.target.checked)}
                    className="mt-0.5 h-4 w-4 shrink-0"
                    style={{ accentColor: 'var(--app-accent)' }}
                  />
                  <span className="text-[13px] leading-relaxed text-muted">
                    I confirm I am <strong className="text-foreground">18 years or older</strong>.
                    get1agent is not intended for children, and we do not knowingly process a
                    child&apos;s data.
                  </span>
                </label>

                {accepted ? (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-success/30 bg-success-soft/40 p-3">
                    <span className="flex items-center gap-2 text-[12px] text-muted">
                      <CheckCircle2 className="h-4 w-4 text-success" />
                      Consent recorded on{' '}
                      {new Date(current!.acceptedAt).toLocaleDateString()}
                    </span>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={handleAccept} disabled={saving}>
                        Update
                      </Button>
                      <Button size="sm" variant="danger" onClick={handleWithdraw} disabled={saving}>
                        Withdraw
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Button onClick={handleAccept} disabled={saving} icon={saving ? <Spinner size="xs" /> : undefined}>
                    {saving ? 'Saving…' : 'Accept and continue'}
                  </Button>
                )}

                <p className="text-xs leading-relaxed text-subtle">
                  Read the full{' '}
                  <Link to="/privacy" className="font-medium text-accent hover:underline">
                    privacy notice
                  </Link>{' '}
                  and our{' '}
                  <Link to="/sub-processors" className="font-medium text-accent hover:underline">
                    sub-processors
                  </Link>
                  .
                </p>
              </div>
            )}
          </SectionCard>

          {/* Access — export ------------------------------------------------- */}
          <SectionCard
            icon={<Download className="h-3.5 w-3.5" strokeWidth={1.75} />}
            title="Download your data"
            description="Right of access: get a machine-readable copy of the personal data we hold."
          >
            <Button
              variant="outline"
              onClick={handleExport}
              disabled={exporting}
              icon={exporting ? <Spinner size="xs" /> : <Download className="h-3.5 w-3.5" />}
            >
              {exporting ? 'Preparing…' : 'Download my data (JSON)'}
            </Button>
          </SectionCard>

          {/* Grievance ------------------------------------------------------- */}
          <SectionCard
            icon={<ScrollText className="h-3.5 w-3.5" strokeWidth={1.75} />}
            title="Raise a request or grievance"
            description="Access, correction, erasure, consent questions or a complaint. We respond within the published timeline."
          >
            <div className="space-y-3">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-muted">Type</span>
                <Select value={requestType} onValueChange={setRequestType}>
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {GRIEVANCE_REQUEST_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-muted">Subject</span>
                <input
                  className="w-full rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none focus:border-accent/60"
                  value={subject}
                  maxLength={160}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder="Short summary"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-muted">Details</span>
                <textarea
                  className="min-h-24 w-full resize-y rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none focus:border-accent/60"
                  value={message}
                  maxLength={8000}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="Describe your request"
                />
              </label>
              <Button
                onClick={handleGrievance}
                disabled={submitting}
                icon={submitting ? <Spinner size="xs" /> : undefined}
              >
                {submitting ? 'Submitting…' : 'Submit request'}
              </Button>

              {grievances.data?.grievances?.length ? (
                <ul className="mt-2 divide-y divide-border rounded-md border border-border">
                  {grievances.data.grievances.map((item) => (
                    <li
                      key={item.ticketId}
                      className="flex items-center justify-between gap-3 px-3 py-2 text-[12px]"
                    >
                      <span className="min-w-0 truncate text-foreground">
                        {item.subject?.replace('[Data rights] ', '')}
                      </span>
                      <span className="shrink-0 text-subtle capitalize">{item.status}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </SectionCard>

          {/* Contact --------------------------------------------------------- */}
          {contact ? (
            <SectionCard
              icon={<Mail className="h-3.5 w-3.5" strokeWidth={1.75} />}
              title="Grievance officer"
              description="If you are not satisfied with our response you may complain to the Board."
            >
              <ul className="space-y-1.5 text-[13px] text-muted">
                <li>{contact.officer}</li>
                <li>
                  <a
                    href={`mailto:${contact.email}`}
                    className="font-medium text-accent hover:underline"
                  >
                    {contact.email}
                  </a>
                </li>
                <li>We aim to respond within {contact.responseDays} days.</li>
                <li>
                  <a
                    href={contact.boardUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-accent hover:underline"
                  >
                    {contact.board}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </li>
              </ul>
            </SectionCard>
          ) : null}

          {/* Erasure --------------------------------------------------------- */}
          <SectionCard
            icon={<AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.75} />}
            title="Delete your account"
            description="Right to erasure: permanently erase your account, files, index and conversations."
          >
            <Button
              variant="danger"
              onClick={() => {
                setDeleteConfirm('')
                setDeleteOpen(true)
              }}
              icon={<Trash2 className="h-3.5 w-3.5" />}
            >
              Delete my account and data
            </Button>
          </SectionCard>
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete your account and all data"
        description="This erases your profile, knowledge bases, documents, files, agents, workflows, skills, conversations and index. It cannot be undone."
        confirmLabel="Delete everything"
        destructive
        loading={deleting}
        onConfirm={handleDelete}
      >
        <div className="space-y-3 text-sm text-muted">
          <p>
            Type <strong className="text-foreground">DELETE</strong> to confirm.
          </p>
          <input
            autoFocus
            value={deleteConfirm}
            onChange={(event) => setDeleteConfirm(event.target.value)}
            className="w-full rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none focus:border-warning/60"
            placeholder="DELETE"
          />
        </div>
      </ConfirmDialog>
    </PageShell>
  )
}
