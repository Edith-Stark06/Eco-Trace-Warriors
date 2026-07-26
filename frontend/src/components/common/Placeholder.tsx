interface PlaceholderProps {
  title: string;
  /** Short line under the title; defaults to the sprint placeholder text. */
  subtitle?: string;
}

/**
 * Generic "coming soon" placeholder used by every route in Sprint 9.1.
 *
 * This sprint is infrastructure only — no dashboards or business UI. Each
 * page renders this until its feature is implemented in a later sprint.
 */
export function Placeholder({ title, subtitle = 'Coming Soon' }: PlaceholderProps) {
  return (
    <section className="flex flex-1 flex-col items-center justify-center gap-2 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm text-muted-foreground">{subtitle}</p>
    </section>
  );
}
