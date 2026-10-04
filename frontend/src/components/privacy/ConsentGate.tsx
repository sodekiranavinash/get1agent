import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Loader2, LogOut, ShieldCheck, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { useApiClient } from '../../lib/api'
import { useDemoMode } from '../../auth/useDemoMode'
import { usePageQuery } from '../../hooks/usePageQuery'
import {
  CONSENT_QUERY_KEY,
  deleteAccount,
  fetchConsent,
  recordConsent,
} from '../../lib/privacy'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'

type AgeChoice = 'adult' | 'minor' | null

/**
 * Records DPDP consent the first time a signed-in user reaches the app, and
 * enforces the 18+ policy.
 *
 * DPDP requires consent to be a clear affirmative action, specific to the
 * purposes shown, and recorded. get1agent does not serve children, so the user
 * first declares whether they are 18 or older; selecting "under 18" hard-blocks
 * the app (the dialog cannot be dismissed) and offers to erase the account. The
 * server refuses to record consent without `adultConfirmed: true`, so the gate
 * cannot be bypassed by calling the API directly. Skipped entirely in the demo.
 */
export function ConsentGate() {
  const api = useApiClient()
  const { isAuthenticated, logout } = useAuth0()
  const demo = useDemoMode()
  const enabled = isAuthenticated && !demo

  const { data } = usePageQuery(CONSENT_QUERY_KEY, () => fetchConsent(api), {
    enabled,
  })

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [ageChoice, setAgeChoice] = useState<AgeChoice>(null)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  const purposes = data?.purposes ?? []
  const current = data?.consent ?? null
  const needsConsent = Boolean(data) && (!current || Boolean(current.withdrawnAt))
  const isMinor = ageChoice === 'minor'

  useEffect(() => {
    if (!data) return
    setSelected(new Set(data.purposes.filter((p) => p.required).map((p) => p.id)))
  }, [data])

  const open = enabled && needsConsent && !dismissed
  if (!open) return null

  function signOut() {
    logout({ logoutParams: { returnTo: window.location.origin } })
  }

  function toggle(id: string, required: boolean) {
    if (required) return
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleAccept() {
    if (ageChoice !== 'adult') {
      toast.error('Please confirm you are 18 or older.')
      return
    }
    setSaving(true)
    try {
      await recordConsent(api, {
        purposes: Array.from(selected),
        adultConfirmed: true,
        language: navigator.language?.slice(0, 2) || 'en',
      })
      toast.success('Thanks — your consent has been recorded.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save consent')
    } finally {
      setSaving(false)
    }
  }

  async function handleMinorDelete() {
    setDeleting(true)
    try {
      await deleteAccount(api)
      toast.success('Your account and data have been erased.')
      signOut()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete your account')
      setDeleting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // A self-declared minor cannot dismiss the block; they must sign out.
        if (!next && !isMinor) setDismissed(true)
      }}
      size="lg"
      icon={
        <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-raised text-accent">
          {isMinor ? <AlertTriangle className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
        </span>
      }
      title={isMinor ? 'get1agent is for adults only' : 'Before you continue'}
      description={
        isMinor
          ? 'You told us you are under 18, so we cannot provide the service.'
          : 'We need your consent to process your personal data. This is required under the DPDP Act, 2023.'
      }
      footer={
        isMinor ? (
          <>
            <Button
              variant="danger"
              onClick={handleMinorDelete}
              disabled={deleting}
              icon={deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            >
              {deleting ? 'Deleting…' : 'Delete my account and data'}
            </Button>
            <Button variant="outline" onClick={signOut} icon={<LogOut className="h-4 w-4" />}>
              Sign out
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={signOut} disabled={saving}>
              Sign out
            </Button>
            <Button variant="ghost" onClick={() => setDismissed(true)} disabled={saving}>
              Not now
            </Button>
            <Button
              onClick={handleAccept}
              disabled={saving || ageChoice !== 'adult'}
              icon={saving ? <Loader2 className="h-4 w-4 animate-spin" /> : undefined}
            >
              {saving ? 'Saving…' : 'I agree'}
            </Button>
          </>
        )
      }
    >
      {isMinor ? (
        <div className="space-y-3 text-[13px] leading-relaxed text-muted">
          <p>
            Under the Digital Personal Data Protection Act, 2023 a child is anyone under 18, and
            we would need a parent or guardian&apos;s verifiable consent to process your data.
            get1agent does not offer that, so the service is not available to you.
          </p>
          <p>
            If you have already created an account or uploaded anything, you can erase it now.
            Otherwise, simply sign out.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <p className="mb-2 text-[13px] font-medium text-foreground">
              Are you 18 years or older?
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                aria-pressed={ageChoice === 'adult'}
                onClick={() => setAgeChoice('adult')}
                className={`rounded-md border p-3 text-left text-[13px] transition-colors ${
                  ageChoice === 'adult'
                    ? 'border-accent/50 bg-accent-soft text-foreground'
                    : 'border-border bg-raised/40 text-muted hover:border-border-strong'
                }`}
              >
                Yes, I am 18 or older
              </button>
              <button
                type="button"
                aria-pressed={isMinor}
                onClick={() => setAgeChoice('minor')}
                className={`rounded-md border p-3 text-left text-[13px] transition-colors ${
                  isMinor
                    ? 'border-warning/50 bg-warning-soft text-foreground'
                    : 'border-border bg-raised/40 text-muted hover:border-border-strong'
                }`}
              >
                No, I am under 18
              </button>
            </div>
          </div>

          <ul className="space-y-2">
            {purposes.map((purpose) => (
              <li
                key={purpose.id}
                className="flex items-start gap-3 rounded-md border border-border bg-raised/40 p-3"
              >
                <input
                  id={`gate-purpose-${purpose.id}`}
                  type="checkbox"
                  checked={selected.has(purpose.id)}
                  disabled={purpose.required}
                  onChange={() => toggle(purpose.id, purpose.required)}
                  className="mt-0.5 h-4 w-4 shrink-0"
                  style={{ accentColor: 'var(--app-accent)' }}
                />
                <label htmlFor={`gate-purpose-${purpose.id}`} className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2 text-[13px] font-medium text-foreground">
                    {purpose.title}
                    <span className="text-[10px] font-medium tracking-wide text-subtle uppercase">
                      {purpose.required ? 'Required' : 'Optional'}
                    </span>
                  </span>
                  <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                    {purpose.description}
                  </span>
                </label>
              </li>
            ))}
          </ul>

          <p className="text-xs leading-relaxed text-subtle">
            Read the full{' '}
            <Link to="/privacy" className="font-medium text-accent hover:underline">
              privacy notice
            </Link>{' '}
            and our{' '}
            <Link to="/sub-processors" className="font-medium text-accent hover:underline">
              sub-processors
            </Link>
            . You can change or withdraw consent any time under{' '}
            <Link to="/privacy/rights" className="font-medium text-accent hover:underline">
              Privacy &amp; data rights
            </Link>
            .
          </p>
        </div>
      )}
    </Dialog>
  )
}
