import { createContext, useContext, useEffect } from 'react'
import { useQuery } from '../lib/query'

/**
 * Minimum time a route/page skeleton stays visible (ms). This is the single
 * place to tune the app-wide loading feel — it keeps the shimmer from flashing.
 *
 * Applied on every route change by `RouteGate` in `layouts/MainLayout.tsx`.
 * A page that loads real data can short-circuit the remaining time by reporting
 * readiness through `RouteContentReadyContext`.
 */
export const PAGE_SKELETON_MIN_MS = 1000

type RouteContentReady = {
  reportReady: () => void
}

/**
 * Provided by `RouteGate`. Pages that fetch data call `reportReady` once the
 * data has settled, so the route skeleton can be dropped immediately instead of
 * waiting out the remaining minimum animation time.
 */
export const RouteContentReadyContext = createContext<RouteContentReady | null>(
  null,
)

/**
 * Standard page data hook. Wraps `useQuery` and adds the "no data yet" notion
 * so a page can render its shaped skeleton while pending.
 *
 * Usage:
 *   const { data, isPending } = usePageQuery('my-key', () => api.get('/...'))
 *   return <PageShell>{isPending ? <MySkeleton /> : <MyContent data={data!} />}</PageShell>
 */
export function usePageQuery<T>(
  key: string,
  fetcher: () => Promise<T>,
  options?: { refetchOnMount?: boolean },
) {
  const query = useQuery(key, fetcher, options)
  // Only treat "no data yet" as pending, so a background refetch (e.g. on
  // remount) doesn't flash the skeleton over already-rendered content.
  const isPending = query.data === undefined
  const routeContentReady = useContext(RouteContentReadyContext)

  useEffect(() => {
    if (!isPending) routeContentReady?.reportReady()
  }, [isPending, routeContentReady])

  return { ...query, isPending }
}
