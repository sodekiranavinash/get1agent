import { Cookie } from 'lucide-react'
import { InfoSections, type InfoSection } from '../components/layout/InfoSections'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { useCookiePreferences } from '../components/cookie/CookiePreferencesProvider'

const SECTIONS: InfoSection[] = [
  {
    title: 'Information we collect',
    paragraphs: [
      'We collect account information you provide when signing in, usage data related to the agents and workflows you create, and technical logs needed to operate the service securely.',
    ],
  },
  {
    title: 'How we use your data',
    paragraphs: [
      'Your data is used to deliver agent and workflow features, improve reliability, and provide billing and administration tools. We do not sell your personal information.',
    ],
  },
  {
    id: 'cookies',
    title: 'Cookies and similar technologies',
    paragraphs: [
      'We use a small number of cookies and browser storage keys. Strictly necessary items keep you signed in and remember your cookie choice; optional categories are off until you allow them. You can change your selection at any time using the button below or the Cookie Preferences link in the footer.',
    ],
    bullets: [
      'Strictly necessary — authentication and your consent record (always active).',
      'Performance — aggregated usage statistics that help us improve the product.',
      'Functional — preferences such as your sidebar state and theme.',
      'Targeting — disabled unless you explicitly opt in; we do not sell your data.',
    ],
  },
  {
    title: 'Sharing and processors',
    paragraphs: [
      'We share data only with the service providers required to run the product, such as model providers, storage and observability vendors, under contracts that limit their use of it.',
    ],
  },
  {
    title: 'Retention',
    paragraphs: [
      'We keep operational data while your workspace is active and for a short period afterwards so you can recover it. Deleting a resource removes it from active systems and from backups on their normal rotation.',
    ],
  },
  {
    title: 'Your choices',
    paragraphs: [
      'You may review and update account details in Settings and manage cookie preferences at any time. To request data deletion or ask privacy questions, contact your workspace administrator or our support team.',
    ],
  },
]

export function PrivacyPage() {
  const { openPreferences } = useCookiePreferences()

  return (
    <PageShell>
      <PageHeader
        title="Privacy statement"
        description="How we collect, use, and protect your information."
        badge="Legal"
      />

      <div className="mb-4 flex max-w-3xl flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-5 py-4">
        <span className="flex size-9 items-center justify-center rounded-lg border border-border bg-raised text-accent">
          <Cookie className="size-4" />
        </span>
        <p className="min-w-0 flex-1 text-[12px] leading-relaxed text-muted">
          Control which optional cookies OneAgent may use.
        </p>
        <Button variant="outline" size="sm" onClick={openPreferences}>
          Manage cookie preferences
        </Button>
      </div>

      <InfoSections sections={SECTIONS} />
    </PageShell>
  )
}
