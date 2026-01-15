/**
 * TanStack Query hook for fetching unlinked episodics
 *
 * Fetches episodic nodes that are NOT linked to any PARA entities.
 * These are "orphaned" notes that need PARA categorization (Inbox).
 */

import { useQuery } from '@tanstack/react-query';
import { getUnlinkedEpisodics, ListUnlinkedEpisodicResponse } from '@/lib/api';

export function useUnlinkedEpisodics(limit = 100) {
  return useQuery<ListUnlinkedEpisodicResponse>({
    queryKey: ['episodics', 'unlinked', limit],
    queryFn: () => getUnlinkedEpisodics({ limit }),
    staleTime: 60000, // 1 minute
  });
}
