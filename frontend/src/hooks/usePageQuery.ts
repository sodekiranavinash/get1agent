import { useQuery } from '../lib/query'

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
  // Only treat "no data yet while still loading" as pending, so a background
  // refetch (e.g. on remount) doesn't flash the skeleton over already-rendered
  // content, and a failed fetch stops the skeleton so the page can show its
  // error state instead of spinning forever.
  const isPending = query.data === undefined && query.status === 'pending'

  return { ...query, isPending }
}
