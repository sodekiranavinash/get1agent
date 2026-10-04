import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

type SubProcessor = {
  name: string
  purpose: string
  data: string
  location: string
  url: string
}

/**
 * The sub-processors get1agent engages, mirroring the platform's real data
 * flows. Kept as data so it is a one-line change when a provider changes.
 */
const SUB_PROCESSORS: SubProcessor[] = [
  {
    name: 'Amazon Web Services (AWS)',
    purpose:
      'Cloud hosting and the entire AI layer: compute, object storage, database, vector index, key management — plus Amazon Bedrock for embeddings, rerank, web search and every model call, and AgentCore for the managed agent platform (runtime, memory, policy, gateway, identity, registry, evaluations, browser).',
    data: 'All customer data (account, content, files, prompts, model outputs, traces, logs, encrypted secrets)',
    location: 'India (ap-south-1) — Bedrock Rerank and Web Search run in US West',
    url: 'https://aws.amazon.com/compliance/data-privacy/',
  },
  {
    name: 'Auth0 (Okta)',
    purpose: 'Authentication and identity (Google sign-in)',
    data: 'Name, email address, profile picture, sign-in metadata',
    location: 'United States',
    url: 'https://www.okta.com/privacy-policy/',
  },
  {
    name: 'Cloudflare',
    purpose: 'DNS and content delivery',
    data: 'Request metadata (IP, user agent) for the web surface',
    location: 'Global',
    url: 'https://www.cloudflare.com/privacypolicy/',
  },
]

const USER_CONFIGURED = [
  'Remote MCP servers you connect — governed by that provider’s terms, under your control.',
  'Your own model providers added to the Vault — we send prompts to them only when you select them.',
  'External APIs your agents call through the http-fetch or browser tools — the destination you choose.',
]

function Cell({ children }: { children: ReactNode }) {
  return (
    <td className="border-t border-border px-3 py-2.5 align-top text-[12px] leading-relaxed text-muted">
      {children}
    </td>
  )
}

export function SubProcessorsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Sub-processors"
        description="The third-party providers that process personal data on our behalf, and where."
        badge="Privacy"
      />

      <div className="max-w-4xl space-y-4">
        <p className="max-w-3xl text-[13px] leading-relaxed text-muted">
          get1agent is <span className="text-foreground">fully AWS-native</span>: the platform and
          its entire AI layer — embeddings, rerank and every model call — run on Amazon Web
          Services (Amazon Bedrock and AgentCore). The processors below run the service; each is
          bound by a contract that limits their use of your data to providing the service to us.
          Personal data is primarily stored in India (AWS{' '}
          <span className="text-foreground">ap-south-1</span>); some processing involves a transfer
          outside India, which we disclose in the{' '}
          <Link to="/privacy" className="font-medium text-accent hover:underline">
            privacy notice
          </Link>
          . You can object to a processor by contacting the grievance officer.
        </p>

        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr className="text-left text-[11px] font-semibold tracking-wide text-subtle uppercase">
                <th className="px-3 py-2.5">Provider</th>
                <th className="px-3 py-2.5">Purpose</th>
                <th className="px-3 py-2.5">Data</th>
                <th className="px-3 py-2.5">Location</th>
              </tr>
            </thead>
            <tbody>
              {SUB_PROCESSORS.map((processor) => (
                <tr key={processor.name}>
                  <Cell>
                    <a
                      href={processor.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 font-medium text-foreground hover:text-accent"
                    >
                      {processor.name}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </Cell>
                  <Cell>{processor.purpose}</Cell>
                  <Cell>{processor.data}</Cell>
                  <Cell>{processor.location}</Cell>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="text-[13px] font-semibold text-foreground">
            Providers you configure
          </h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-muted">
            {USER_CONFIGURED.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </PageShell>
  )
}
