# Sub-processor DPA register

## What is a DPA?

A **Data Processing Agreement** (DPA) is the contract between get1agent (the
**Data Fiduciary**) and a vendor that handles personal data on our behalf (a
**Data Processor**). The DPDP Act (Section 8(2)) requires a valid contract with
every processor before it processes data for us.

In plain terms, a DPA is the vendor's written promise to:

- process the data **only on our instructions**, for the stated purpose;
- keep it **secure** and report breaches to us;
- help us answer **data-principal rights** requests (access, erasure);
- **delete or return** the data when we stop using the service; and
- flow these duties down to *their* sub-processors.

You do **not** usually draft these. Most providers publish a standard
**Data Processing Addendum** that is either (a) automatically part of their
terms, or (b) available to accept/request in their dashboard. "Executing" it means
accepting or signing their standard form. Keep the confirmation email or the
signed PDF.

## Status

This is a **pre-launch checklist**. It becomes important when you have real
users; it is not blocking for a private/personal deployment. Work down the list
as you scale and store each accepted DPA (or a link + date) with these docs.

| Provider | Handles | Get the DPA | Status |
|---|---|---|---|
| **Amazon Web Services** | Everything AWS-native: hosting (compute, storage, database, vectors, KMS, queues, CI role) **and the whole AI layer** — Amazon Bedrock (embeddings, rerank, inference, Guardrails, web search) and AgentCore (runtime, memory, policy, gateway, identity, registry, evaluations, browser) | AWS Customer Agreement + [Data Processing Addendum](https://aws.amazon.com/agreement/) (self-serve in the AWS console) | ☐ to do |
| **Auth0 (Okta)** | Authentication / identity | [Okta DPA](https://www.okta.com/agreements/) — accept in the Okta/Auth0 dashboard | ☐ to do |
| **Cloudflare** | DNS / CDN | [Cloudflare DPA](https://www.cloudflare.com/cloudflare-customer-dpa/) (self-serve) | ☐ to do |

> The platform is **fully AWS-native**: Bedrock and AgentCore fall under the same
> AWS Customer Agreement / DPA as the rest of the cloud layer, so AWS is a single
> row — and **web search is the AgentCore Gateway's built-in connector**, also under
> AWS. Auth0 and Cloudflare are the only non-AWS processors.

## When a DPA is signed

1. Save it to `docs/compliance/dpas/<provider>.pdf` (or record the link + date).
2. Tick the box above and add the date.
3. Keep the sub-processor list on the privacy page in sync
   (`frontend/src/pages/SubProcessorsPage.tsx`).
