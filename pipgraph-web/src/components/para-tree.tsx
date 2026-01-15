'use client';

import { useParaTree } from '@/hooks/use-para-tree';
import { ParaTreeItem } from './para-tree-item';
import { Skeleton } from '@/components/ui/skeleton';

interface ParaTreeProps {
  selectedEntityUuid: string | null;
  onSelectEntity: (uuid: string) => void;
}

export function ParaTree({ selectedEntityUuid, onSelectEntity }: ParaTreeProps) {
  const { data, isLoading, error } = useParaTree();

  if (isLoading) {
    return (
      <div className="p-4 space-y-2">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-red-500 text-sm">
        Error loading PARA tree: {error.message}
      </div>
    );
  }

  if (!data || data.tree.length === 0) {
    return (
      <div className="p-4 text-muted-foreground text-sm">
        No PARA entities found
      </div>
    );
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-4">PARA Structure</h2>
      <ul className="flex flex-col gap-1">
        {data.tree.map((node) => (
          <ParaTreeItem
            key={node.id}
            node={node}
            selectedEntityUuid={selectedEntityUuid}
            onSelectEntity={onSelectEntity}
          />
        ))}
      </ul>
    </div>
  );
}
