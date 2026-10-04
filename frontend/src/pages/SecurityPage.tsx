import { useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { Send, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { useApiClient } from '../lib/api'
import { useDemoMode } from '../auth/useDemoMode'
import { usePageQuery } from '../hooks/usePageQuery'
import {
  SECURITY_PAGES,
  createSecurityReport,
  fetchSecurityReports,
  type SecurityReport,
} from '../lib/support'
import { InfoSections } from '../components/layout/InfoSections'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Spinner } from '../components/ui/Spinner'

const SECTIONS = [
  {
    title: 'Reporting a vulnerability',
    paragraphs: [
      'If you believe you have found a security issue in OneAgent (powered by get1agent.com), please tell us before disclosing it publicly so we can investigate and fix it. Use the form above and include a description, reproduction steps and any supporting material.',
    ],
    bullets: [
      'Include the affected URL or page and the impact you believe it has.',
      'Where possible, share a proof of concept or screenshots rather than live exploitation.',
      'Do not access, modify or delete data that does not belong to you.',
    ],
  },
  {
    title: 'How reports are handled',
    paragraphs: [
      'OneAgent is a free product, so reports are reviewed on a best-effort basis — we cannot promise a response time. Thank you for helping us keep it secure.',
      'Reports are one-way: you send them, the security team reads them. If you need a back-and-forth, use Support instead.',
    ],
  },
  {
    title: 'In scope',
    paragraphs: ['Security issues in the OneAgent product and platform are in scope.'],
    bullets: [
      'Authentication and authorisation flaws across the API and app.',
      'Server-side request forgery, injection or sandbox escapes.',
      'Cross-tenant access to knowledge bases, files or conversations.',
    ],
  },
  {
    title: 'Out of scope',
    paragraphs: [
      'The following are generally out of scope, though we still appreciate a heads-up.',
    ],
    bullets: [
      'Findings from automated scanners without a demonstrated impact.',
      'Missing security headers or best-practice hardening with no exploit path.',
      'Attacks requiring a compromised device, browser extension or user credentials.',
      'Social engineering, physical access or denial-of-service volume attacks.',
    ],
  },
  {
    title: 'Safe harbour',
    paragraphs: [
      'We will not pursue legal action against researchers who act in good faith under this policy, follow the rules above, and give us a reasonable chance to fix an issue before public disclosure.',
    ],
  },
]

/**
 * Security policy plus the one-way report form. Reporting requires a signed-in
 * account so a submission is attributable; the demo is read-only.
 */
export function SecurityPage() {
  const api = useApiClient()
  const { isAuthenticated } = useAuth0()
  const demo = useDemoMode()
  const canWrite = isAuthenticated && !demo

  const [url, setUrl] = useState('')
  const [page, setPage] = useState(SECURITY_PAGES[0])
  const [description, setDescription] = useState('')
  const [sending, setSending] = useState(false)

  const { data: reports, refetch } = usePageQuery(
    'security-reports',
    () => fetchSecurityReports(api),
    { enabled: canWrite },
  )

  const submit = async () => {
    if (!description.trim()) return
    setSending(true)
    try {
      await createSecurityReport(api, {
        url: url.trim(),
        page,
        body: description.trim(),
      })
      setUrl('')
      setDescription('')
      refetch()
      toast.success('Report submitted — thank you.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not submit report')
    } finally {
      setSending(false)
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Report a security issue"
        description="Disclose a vulnerability responsibly. Reports go to the security team only."
        badge="Security"
        badgeVariant="warning"
      />

      {canWrite ? (
        <section className="mb-4 max-w-3xl rounded-lg border border-border bg-surface p-5">
          <h2 className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
            <ShieldCheck className="size-4 text-accent" />
            Submit a report
          </h2>
          <p className="mt-1 text-[12px] leading-relaxed text-muted">
            One-way, text only. The team cannot reply in this thread — use
            Support for a conversation.
          </p>
          <div className="mt-4 space-y-3">
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-subtle">
                Affected URL
              </span>
              <input
                className="field"
                type="url"
                value={url}
                maxLength={2000}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://… (optional)"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-subtle">
                Which page or area?
              </span>
              <select
                className="field"
                value={page}
                onChange={(event) => setPage(event.target.value)}
              >
                {SECURITY_PAGES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-subtle">
                Describe the issue
              </span>
              <textarea
                className="field min-h-[140px] resize-y"
                value={description}
                maxLength={8000}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What you found, how to reproduce it, and the impact."
              />
            </label>
            <div className="flex justify-end">
              <Button
                icon={sending ? <Spinner /> : <Send className="size-3.5" />}
                disabled={sending || !description.trim()}
                onClick={submit}
              >
                Submit report
              </Button>
            </div>
          </div>

          {(reports?.length ?? 0) > 0 ? (
            <div className="mt-5 border-t border-border pt-4">
              <h3 className="text-[11px] font-semibold tracking-[0.08em] text-subtle uppercase">
                Your reports
              </h3>
              <ul className="mt-2 space-y-1.5">
                {reports!.map((report: SecurityReport) => (
                  <li
                    key={report.id}
                    className="flex items-center gap-3 rounded-md border border-border bg-raised/40 px-3 py-2"
                  >
                    <span className="min-w-0 flex-1 truncate text-[12px] text-foreground">
                      {report.page || 'Unspecified page'}
                      {report.url ? ` · ${report.url}` : ''}
                    </span>
                    <Badge
                      variant={report.status === 'resolved' ? 'success' : 'warning'}
                    >
                      {report.status === 'resolved' ? 'Resolved' : 'Received'}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : (
        <div className="mb-4 max-w-3xl rounded-lg border border-border bg-surface p-5">
          <h2 className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
            <ShieldCheck className="size-4 text-accent" />
            Sign in to submit a report
          </h2>
          <p className="mt-1 text-[12px] leading-relaxed text-muted">
            {demo
              ? 'The read-only demo cannot submit reports. Sign in to report an issue.'
              : 'Security reports must come from a signed-in account so we can attribute and follow up on them.'}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Link to="/" className="no-underline">
              <Button size="sm">Sign in</Button>
            </Link>
            <a
              href="mailto:techwithkiranavinash@gmail.com"
              className="text-[13px] font-medium text-accent hover:underline"
            >
              or email techwithkiranavinash@gmail.com
            </a>
          </div>
        </div>
      )}

      <InfoSections sections={SECTIONS} />
    </PageShell>
  )
}
