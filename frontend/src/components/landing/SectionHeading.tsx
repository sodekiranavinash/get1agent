import { Reveal } from './Reveal'

type SectionHeadingProps = {
  eyebrow: string
  title: string
  description?: string
  align?: 'center' | 'left'
}

/** Consistent eyebrow / title / description block for landing sections. */
export function SectionHeading({
  eyebrow,
  title,
  description,
  align = 'center',
}: SectionHeadingProps) {
  const alignment =
    align === 'center' ? 'mx-auto max-w-2xl text-center' : 'max-w-2xl'

  return (
    <Reveal className={alignment}>
      <p className="text-[11px] font-semibold tracking-[0.18em] text-accent uppercase">
        {eyebrow}
      </p>
      <h2 className="mt-3 text-[1.6rem] leading-tight font-semibold tracking-tight text-foreground sm:text-[2rem]">
        {title}
      </h2>
      {description ? (
        <p className="mt-3 text-[14px] leading-relaxed text-muted">{description}</p>
      ) : null}
    </Reveal>
  )
}
