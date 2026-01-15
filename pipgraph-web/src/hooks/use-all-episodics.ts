import { useQuery } from '@tanstack/react-query';
import { listEpisodics } from '@/lib/api';

export function useAllEpisodics(limit = 100) {
  return useQuery({
    queryKey: ['episodics', 'all'],
    queryFn: () => listEpisodics({ limit }),
  });
}
