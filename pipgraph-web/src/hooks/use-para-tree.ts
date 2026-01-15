import { useQuery } from '@tanstack/react-query';
import { getParaTree } from '@/lib/api';

export function useParaTree() {
  return useQuery({
    queryKey: ['para-tree'],
    queryFn: getParaTree,
    staleTime: 5 * 60 * 1000, // 5 minutes (tree structure is relatively static)
  });
}
