import { Link } from 'react-router-dom'
import { InfoSections } from '../components/layout/InfoSections'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

const SECTIONS = [
  {
    title: 'Acceptance of terms',
    paragraphs: [
      'By accessing or using OneAgent (powered by get1agent.com) you agree to these Terms of Use. If you use the service on behalf of an organisation, you confirm you have authority to bind that organisation to these terms.',
    ],
  },
  {
    title: 'Your account',
    paragraphs: [
      'You are responsible for the activity under your account and for keeping your credentials secure. You must be at least 18 years old to use the service; get1agent is not intended for children.',
    ],
    bullets: [
      'Provide accurate account information and keep it up to date.',
      'Do not share your account, tokens or API keys with anyone outside your workspace.',
      'Notify us promptly at techwithkiranavinash@gmail.com if you suspect unauthorised access.',
    ],
  },
  {
    title: 'Privacy and data protection',
    paragraphs: [
      'We process your personal data as a data fiduciary under the Digital Personal Data Protection Act, 2023. Our privacy notice describes what we collect, why, the sub-processors we use, and how long we keep data. We ask for your consent before processing, and you can review or withdraw it at any time.',
      'You have the right to access, correct and erase your personal data, to raise a grievance, and to nominate another person to exercise your rights. Use the Privacy & data rights page to download your data, manage consent, raise a request or delete your account. Our grievance officer is available at techwithkiranavinash@gmail.com.',
    ],
  },
  {
    title: 'Your content and acceptable use',
    paragraphs: [
      'You retain ownership of the content you upload and the agents you build. You grant us the limited rights needed to operate the service — for example, to store, process and back up your data.',
    ],
    bullets: [
      'Do not upload content you do not have the right to use.',
      'Do not upload other people\u2019s personal data unless you have a lawful basis to do so — you are responsible for the content you put into a knowledge base.',
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
    title: 'Trademarks and attribution',
    paragraphs: [
      'OneAgent (powered by get1agent.com) is a product of the get1agent platform. Product names, logos and brands are the property of their respective owners. OneAgent is an independent product and is not affiliated with, endorsed by, or sponsored by any other company, product or service that uses a similar name. Any third-party names are used only to identify the services they refer to.',
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
      'You may stop using the service at any time and delete your account, together with your data, from the Privacy & data rights page. We may suspend or terminate access if these terms are breached. On termination we delete or anonymise your data in line with our privacy notice.',
    ],
  },
]

export function TermsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Terms of Use"
        description="The agreement that governs your use of OneAgent (powered by get1agent.com)."
        badge="Legal"
      />

      <p className="mb-4 max-w-3xl text-[12px] text-subtle">
        Last updated October 2026. See also our{' '}
        <Link to="/privacy" className="font-medium text-accent hover:underline">
          Privacy Notice
        </Link>{' '}
        and{' '}
        <Link to="/privacy/rights" className="font-medium text-accent hover:underline">
          Privacy &amp; data rights
        </Link>
        .
      </p>

      <InfoSections sections={SECTIONS} />
    </PageShell>
  )
}
