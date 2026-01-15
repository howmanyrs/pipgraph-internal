import { useQuery } from '@tanstack/react-query';
import { getEpisodicsByEntity } from '@/lib/api';

export function useEpisodicsByEntity(entityUuid: string, limit = 50) {
  return useQuery({
    queryKey: ['episodics', 'by-entity', entityUuid],
    queryFn: () => getEpisodicsByEntity({ entity_uuid: entityUuid, limit }),
    enabled: !!entityUuid, // Only run if entityUuid is truthy
  });
}
