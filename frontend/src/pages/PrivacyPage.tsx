import { Cookie, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { InfoSections, type InfoSection } from '../components/layout/InfoSections'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { useCookiePreferences } from '../components/cookie/CookiePreferencesProvider'

const SECTIONS: InfoSection[] = [
  {
    title: 'Who we are',
    paragraphs: [
      'get1agent (also presented as OneAgent) is the data fiduciary that decides how your personal data is processed. This notice is given under the Digital Personal Data Protection Act, 2023 (the "DPDP Act") and explains what we collect, why, your rights, and how to exercise them.',
      'It applies when you create an account and use the platform at get1agent.com and its API.',
    ],
  },
  {
    title: 'Personal data we process, and why',
    paragraphs: [
      'We collect only what we need, for the specific purposes below. This is an itemised description of the data and the purpose of each item.',
    ],
    bullets: [
      'Account and authentication — your name, email address, profile picture and sign-in identifier, received from Google sign-in through Auth0, to create and secure your account and sign you in.',
      'Workspace content — the knowledge bases, documents, agents, workflows, skills, files and conversations you create, to provide the service you asked for.',
      'AI processing inputs — the prompts, questions and content you submit, and the tool outputs returned, to generate answers and search your knowledge.',
      'Billing and usage — token counts and AI-credit usage, to meter and show your usage and enforce limits.',
      'Service notifications — your notification preferences and email address, to alert you about failures and important account events.',
      'Security and operations — technical logs (IP address, user agent, timestamps) and error diagnostics, to keep the service secure, prevent abuse and debug issues.',
      'Cookies and local storage — as described in the cookies section below.',
    ],
  },
  {
    title: 'Our lawful basis: your consent',
    paragraphs: [
      'We process your personal data on the basis of your consent, given when you accept this notice. Consent must be free, specific, informed, unconditional and unambiguous, and is limited to the purposes above. You can review exactly what you consented to, and withdraw it at any time, on the Privacy & data rights page — withdrawing is as easy as giving consent.',
      'Some processing is also necessary to comply with law (for example, security and fraud prevention) and to provide the service you request.',
    ],
  },
  {
    title: 'Your rights',
    paragraphs: [
      'As a Data Principal under the DPDP Act you have the right to:',
    ],
    bullets: [
      'Access — request a summary of the personal data we process about you and the identities of the fiduciaries we share it with. You can download a machine-readable copy instantly.',
      'Correction and erasure — correct inaccurate data (your name and preferences in Settings), or erase your data and close your account. Erasure removes your profile, files, search index and conversations.',
      'Grievance redressal — raise a request or complaint and receive a response within the timeline published on the rights page.',
      'Nominations — nominate another person to exercise your rights in the event of death or incapacity, by contacting the grievance officer.',
      'Withdraw consent — withdraw your consent at any time, after which we stop the associated processing. Because processing is necessary to provide the service, withdrawing consent for required purposes means closing your account.',
    ],
  },
  {
    title: 'Exercise your rights',
    paragraphs: [
      'Use the Privacy & data rights page to download your data, manage or withdraw consent, raise a request, or delete your account. You can also write to the grievance officer listed below.',
    ],
  },
  {
    title: 'Sharing and sub-processors',
    paragraphs: [
      'We do not sell your personal data. The platform and its entire AI layer — embeddings, rerank and every model call — run on AWS (Amazon Bedrock and AgentCore). We share data only with the small set of sub-processors needed to run the platform — AWS for cloud and AI, plus identity, web-search and CDN providers — under contracts that limit their use of it to providing the service to us. The current list, and where each operates, is published on our sub-processors page.',
      'When you connect a third-party MCP server or add your own model provider key, that provider processes data under its own terms and your instructions.',
    ],
  },
  {
    title: 'Cross-border transfers',
    paragraphs: [
      'Your data is primarily stored in India (AWS Mumbai, ap-south-1). Some processing involves transferring data outside India — for example, to our identity, model, embedding and observability providers located in the United States and the European Union. We transfer data under contractual safeguards, and we will update this notice if the Government notifies restrictions on transfers to any country.',
    ],
  },
  {
    title: 'How long we keep data',
    paragraphs: [
      'We keep personal data only while your account is active and for as long as needed for the purposes above, then erase or anonymise it. On account deletion we erase your profile, content, files, index and conversations. Some security logs and records of consent may be retained for a limited period where the law requires it. Ephemeral items such as sessions and notifications carry a time-to-live and expire automatically.',
    ],
  },
  {
    title: 'Security',
    paragraphs: [
      'We protect data with encryption in transit and at rest, KMS-encrypted secrets, strict per-user isolation across the database, storage and vector index, authenticated API access, and sandboxed execution of generated code. See our security page to report a vulnerability.',
    ],
  },
  {
    title: 'Children',
    paragraphs: [
      'get1agent is not intended for children. A child is anyone under 18 under the DPDP Act. We block use by under-18s: the first time you sign in we ask your age, and if you are under 18 we do not provide the service and offer to erase any data you created. We do not track or behaviourally monitor children and do not direct targeted advertising at them.',
      'If we learn that we hold a child’s personal data, we will delete it.',
    ],
  },
  {
    title: 'Cookies and similar technologies',
    paragraphs: [
      'We use a small number of cookies and browser storage keys. Strictly necessary items keep you signed in and remember your cookie choice; optional categories are off until you allow them. You can change your selection at any time using the button below or the Cookie Preferences link in the footer.',
    ],
    bullets: [
      'Strictly necessary — authentication and your consent record (always active).',
      'Performance — optional usage statistics. No performance cookies are set today; the category is reserved for when we add analytics.',
      'Functional — preferences such as your sidebar state and theme.',
      'Targeting — we do not run targeted advertising and never set targeting cookies, so this category is always off.',
    ],
  },
  {
    title: 'Grievance officer and complaints',
    paragraphs: [
      'If you have a question or complaint about how we handle your personal data, contact our Data Protection & Grievance Officer at techwithkiranavinash@gmail.com. We aim to respond within 90 days.',
      'If you are not satisfied with our response, you have the right to lodge a complaint with the Data Protection Board of India. You may also nominate a person to exercise your rights in the event of your death or incapacity by writing to the same address.',
    ],
  },
  {
    title: 'Changes to this notice',
    paragraphs: [
      'We may update this notice as the service, the law, or our providers change. The current version and date are shown at the top of this page; where a change materially affects you we will ask you to review and accept the updated notice.',
    ],
  },
]

export function PrivacyPage() {
  const { openPreferences } = useCookiePreferences()

  return (
    <PageShell>
      <PageHeader
        title="Privacy notice"
        description="What personal data we process, why, your rights, and how to exercise them."
        badge="Legal"
      />

      <p className="mb-4 max-w-3xl text-[12px] text-subtle">
        Last updated 2 October 2026 · Notice version 2026-10-02 · Governed by the Digital Personal
        Data Protection Act, 2023.
      </p>

      <div className="mb-4 flex max-w-3xl flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-5 py-4">
        <span className="flex size-9 items-center justify-center rounded-lg border border-border bg-raised text-accent">
          <ShieldCheck className="size-4" />
        </span>
        <p className="min-w-0 flex-1 text-[12px] leading-relaxed text-muted">
          Manage your consent, download your data, raise a request or delete your account.
        </p>
        <Link to="/privacy/rights">
          <Button variant="outline" size="sm">
            Your privacy &amp; data rights
          </Button>
        </Link>
      </div>

      <div className="mb-4 flex max-w-3xl flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-5 py-4">
        <span className="flex size-9 items-center justify-center rounded-lg border border-border bg-raised text-accent">
          <Cookie className="size-4" />
        </span>
        <p className="min-w-0 flex-1 text-[12px] leading-relaxed text-muted">
          Control which optional cookies get1agent may use.
        </p>
        <Button variant="outline" size="sm" onClick={openPreferences}>
          Manage cookie preferences
        </Button>
      </div>

      <InfoSections sections={SECTIONS} />
    </PageShell>
  )
}
