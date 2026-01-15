/**
 * TanStack Query mutation hook for linking note to PARA entity and processing
 *
 * Performs two sequential operations:
 * 1. Links episodic to entity (creates MENTIONS relationship)
 * 2. Processes the episodic node (extracts entities)
 *
 * On success, invalidates unlinked episodics and suggestions queries
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  linkEntityToEpisode,
  processExistingEpisode,
  LinkEntityEpisodeResponse,
  ProcessExistingEpisodeResponse,
} from '@/lib/api';

interface LinkAndProcessRequest {
  episodic_uuid: string;
  entity_uuid: string;
}

interface LinkAndProcessResponse {
  linkResult: LinkEntityEpisodeResponse;
  processResult: ProcessExistingEpisodeResponse;
}

export function useLinkAndProcess() {
  const queryClient = useQueryClient();

  return useMutation<LinkAndProcessResponse, Error, LinkAndProcessRequest>({
    mutationFn: async ({ episodic_uuid, entity_uuid }) => {
      // Step 1: Link episodic to entity (create MENTIONS relationship)
      const linkResult = await linkEntityToEpisode({
        episodic_uuid,
        entity_uuid,
      });

      if (!linkResult.success) {
        throw new Error(linkResult.error || 'Failed to link note to entity');
      }

      // Step 2: Process episodic (extract entities)
      const processResult = await processExistingEpisode({
        episodic_uuid,
      });

      if (!processResult.success) {
        throw new Error(
          processResult.error || 'Failed to process note after linking'
        );
      }

      return { linkResult, processResult };
    },
    onSuccess: (data, variables) => {
      // Invalidate unlinked episodics list (note should disappear)
      queryClient.invalidateQueries({ queryKey: ['episodics', 'unlinked'] });

      // Invalidate suggestions for this episodic (clear stale suggestions)
      queryClient.invalidateQueries({
        queryKey: ['suggestions', variables.episodic_uuid],
      });
    },
  });
}
