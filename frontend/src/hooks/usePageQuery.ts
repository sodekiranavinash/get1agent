import { useQuery } from '../lib/query'

/**
 * Minimum time a route/page skeleton stays visible (ms). This is the single
 * place to tune the app-wide loading feel — it keeps the shimmer from flashing.
 *
 * Applied on every route change by `RouteGate` in `layouts/MainLayout.tsx`.
 */
export const PAGE_SKELETON_MIN_MS = 1000

/**
 * Standard page data hook. Wraps `useQuery` and adds the "no data yet" notion
 * so a page can render its shaped skeleton while pending.
 *
 * Usage:
 *   const { data, isPending } = usePageQuery('my-key', () => api.get('/...'))
 *   return <PageShell>{isPending ? <MySkeleton /> : <MyContent data={data!} />}</PageShell>
 */
export function usePageQuery<T>(key: string, fetcher: () => Promise<T>) {
  const query = useQuery(key, fetcher)
  const isPending = query.isLoading || query.data === undefined

  return { ...query, isPending }
}
