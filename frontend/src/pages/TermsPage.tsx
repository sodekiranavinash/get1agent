import { Link } from 'react-router-dom'
import { InfoSections } from '../components/layout/InfoSections'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

const SECTIONS = [
  {
    title: 'Acceptance of terms',
    paragraphs: [
      'By accessing or using OneAgent you agree to these Terms of Use. If you use the service on behalf of an organisation, you confirm you have authority to bind that organisation to these terms.',
    ],
  },
  {
    title: 'Your account',
    paragraphs: [
      'You are responsible for the activity under your account and for keeping your credentials secure. You must be old enough to enter a binding contract in your jurisdiction to use the service.',
    ],
    bullets: [
      'Provide accurate account information and keep it up to date.',
      'Do not share your account, tokens or API keys with anyone outside your workspace.',
      'Notify us promptly at security@get1agent.com if you suspect unauthorised access.',
    ],
  },
  {
    title: 'Your content and acceptable use',
    paragraphs: [
      'You retain ownership of the content you upload and the agents you build. You grant us the limited rights needed to operate the service — for example, to store, process and back up your data.',
    ],
    bullets: [
      'Do not upload content you do not have the right to use.',
      'Do not attempt to disrupt the service, bypass its limits or access other users\u2019 data.',
      'Do not use the service to build malware, spam or content that violates the law.',
    ],
  },
  {
    title: 'Third-party services',
    paragraphs: [
      'OneAgent can connect to third-party model providers, MCP servers and data sources. Your use of those services is governed by their terms, and you are responsible for any keys and costs associated with them.',
    ],
  },
  {
    title: 'Availability and changes',
    paragraphs: [
      'We work hard to keep the service available and improve it over time. Features may change, and we may occasionally need to interrupt the service for maintenance. We will give reasonable notice of material changes.',
    ],
  },
  {
    title: 'Disclaimer and liability',
    paragraphs: [
      'The service is provided on an as-is and as-available basis. To the extent permitted by law, we disclaim implied warranties and our aggregate liability is limited to the fees you paid for the service in the twelve months before a claim.',
    ],
  },
  {
    title: 'Termination',
    paragraphs: [
      'You may stop using the service at any time and delete your workspace from Settings. We may suspend or terminate access if these terms are breached. On termination we delete or anonymise your data in line with the Privacy Policy.',
    ],
  },
]

export function TermsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Terms of Use"
        description="The agreement that governs your use of OneAgent."
        badge="Legal"
      />

      <p className="mb-4 max-w-3xl text-[12px] text-subtle">
        Last updated September 2026. See also our{' '}
        <Link to="/privacy" className="font-medium text-accent hover:underline">
          Privacy Policy
        </Link>
        .
      </p>

      <InfoSections sections={SECTIONS} />
    </PageShell>
  )
}
