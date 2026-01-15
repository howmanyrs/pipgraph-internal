/**
 * TanStack Query hook for fetching PARA entity suggestions
 *
 * Finds relevant PARA entities for an episodic note using hybrid search
 * (BM25 + vector similarity). Only runs when episodicUuid is provided.
 */

import { useQuery } from '@tanstack/react-query';
import { makeSuggestions, MakeSuggestionsResponse } from '@/lib/api';

export function useMakeSuggestions(episodicUuid: string | null, limit = 10) {
  return useQuery<MakeSuggestionsResponse>({
    queryKey: ['suggestions', episodicUuid, limit],
    queryFn: () => makeSuggestions({ episodic_uuid: episodicUuid!, limit }),
    enabled: !!episodicUuid, // Only run when episodicUuid is set
    staleTime: 60000, // 1 minute
  });
}
