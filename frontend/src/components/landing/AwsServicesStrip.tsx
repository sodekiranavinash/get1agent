import { useNavigate } from 'react-router-dom'
import { Boxes } from 'lucide-react'
import { Button } from '../ui/Button'
import { Reveal } from './Reveal'
import { AWS_SERVICES, AWS_SERVICES_MORE } from './awsServices'
import { AWS_SERVICE_HEADLINE, AWS_NATIVE_LINE } from '../architecture/stack'

/**
 * "Built on AWS" strip for the landing page.
 *
 * Shows the official AWS Architecture Icons for the headline services with a
 * gentle staggered reveal and hover lift, then names the rest. AWS icons are
 * © Amazon Web Services, Inc., used under the AWS icon terms.
 */
export function AwsServicesStrip() {
  const navigate = useNavigate()

  return (
    <section className="relative py-20">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/60 px-3 py-1 text-[11px] font-medium tracking-wide text-muted uppercase backdrop-blur-sm">
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-70" />
              <span className="relative inline-flex size-1.5 rounded-full bg-accent" />
            </span>
            {AWS_SERVICE_HEADLINE}
          </span>
          <h2 className="animate-text-sheen mt-4 bg-gradient-to-r from-foreground via-accent to-foreground bg-clip-text text-[26px] font-semibold tracking-tight text-transparent sm:text-[32px]">
            Fully AWS-native, end to end.
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-[13.5px] leading-relaxed text-muted">
            {AWS_NATIVE_LINE} Auth0 and Cloudflare are the only deliberate
            non-AWS dependencies.
          </p>
        </div>

        {/* Mid-section CTA into the full architecture surface. */}
        <Reveal delay={80}>
          <div className="mt-8 flex justify-center">
            <span className="glow-border">
              <Button
                size="lg"
                onClick={() => navigate('/architecture')}
                icon={<Boxes className="size-4" strokeWidth={1.75} />}
                className="glow-inner"
              >
                Explore architecture
              </Button>
            </span>
          </div>
        </Reveal>

        {/* Icon grid — staggered reveal + hover lift. */}
        <div className="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {AWS_SERVICES.map(({ name, note, Icon }, index) => (
            <Reveal key={name} delay={index * 45} className="h-full">
              <div className="group flex h-full items-start gap-3 rounded-2xl border border-border bg-surface/50 p-4 backdrop-blur-sm transition-all duration-300 hover:-translate-y-1 hover:border-accent/40 hover:bg-surface/80 hover:shadow-[0_10px_40px_-16px_rgba(0,0,0,0.35)]">
                <span className="flex size-9 shrink-0 items-center justify-center transition-transform duration-300 group-hover:scale-110">
                  <Icon className="size-9" title={name} />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[12.5px] font-semibold text-foreground">
                    {name}
                  </span>
                  <span className="mt-0.5 block text-[11px] leading-snug text-subtle">
                    {note}
                  </span>
                </span>
              </div>
            </Reveal>
          ))}
        </div>

        {/* The rest, named only. */}
        <Reveal delay={120}>
          <div className="mt-8 flex flex-wrap justify-center gap-2">
            {AWS_SERVICES_MORE.map((item) => (
              <span
                key={item}
                className="rounded-full border border-border bg-canvas/50 px-3 py-1 text-[11px] text-muted"
              >
                {item}
              </span>
            ))}
            <span className="rounded-full border border-border bg-canvas/50 px-3 py-1 text-[11px] text-muted">
              + more
            </span>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
