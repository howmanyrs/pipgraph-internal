import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createEpisode, CreateEpisodeRequest, CreateEpisodeResponse } from '@/lib/api';

export function useCreateEpisode() {
  const queryClient = useQueryClient();

  return useMutation<CreateEpisodeResponse, Error, CreateEpisodeRequest>({
    mutationFn: createEpisode,
    onSuccess: () => {
      // Invalidate episodics cache to refresh lists
      queryClient.invalidateQueries({ queryKey: ['episodics'] });
    },
  });
}
