import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

export function PrivacyPage() {
  return (
    <PageShell>
      <PageHeader
        title="Privacy Statement"
        description="How we collect, use, and protect your information."
      />

      <div className="prose prose-sm mt-8 max-w-3xl space-y-6 text-muted">
        <section className="rounded-2xl border border-border bg-surface/60 p-6">
          <h2 className="text-base font-semibold text-foreground">Information we collect</h2>
          <p className="mt-2 text-sm leading-relaxed">
            We collect account information you provide when signing in, usage data related to
            agents and workflows you create, and technical logs needed to operate the service
            securely.
          </p>
        </section>

        <section className="rounded-2xl border border-border bg-surface/60 p-6">
          <h2 className="text-base font-semibold text-foreground">How we use your data</h2>
          <p className="mt-2 text-sm leading-relaxed">
            Your data is used to deliver agent and workflow features, improve reliability, and
            provide billing and administration tools. We do not sell your personal information.
          </p>
        </section>

        <section className="rounded-2xl border border-border bg-surface/60 p-6">
          <h2 className="text-base font-semibold text-foreground">Your choices</h2>
          <p className="mt-2 text-sm leading-relaxed">
            You may review and update account details in Settings. To request data deletion or
            ask privacy questions, contact your workspace administrator or our support team.
          </p>
        </section>
      </div>
    </PageShell>
  )
}
