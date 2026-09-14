import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

const sections = [
  {
    title: 'Information we collect',
    body: 'We collect account information you provide when signing in, usage data related to agents and workflows you create, and technical logs needed to operate the service securely.',
  },
  {
    title: 'How we use your data',
    body: 'Your data is used to deliver agent and workflow features, improve reliability, and provide billing and administration tools. We do not sell your personal information.',
  },
  {
    title: 'Your choices',
    body: 'You may review and update account details in Settings. To request data deletion or ask privacy questions, contact your workspace administrator or our support team.',
  },
]

export function PrivacyPage() {
  return (
    <PageShell>
      <PageHeader
        title="Privacy statement"
        description="How we collect, use, and protect your information."
        badge="Legal"
      />

      <div className="max-w-3xl space-y-3">
        {sections.map((section) => (
          <section
            key={section.title}
            className="rounded-lg border border-border bg-surface p-5"
          >
            <h2 className="text-[13px] font-semibold text-foreground">
              {section.title}
            </h2>
            <p className="mt-2 text-[13px] leading-relaxed text-muted">
              {section.body}
            </p>
          </section>
        ))}
      </div>
    </PageShell>
  )
}
