'use client';

import { useAllEpisodics } from '@/hooks/use-all-episodics';
import { useEpisodicsByEntity } from '@/hooks/use-episodics-by-entity';
import { EpisodicCard } from './episodic-card';
import { Skeleton } from '@/components/ui/skeleton';

interface EpisodicListProps {
  selectedEntityUuid: string | null;
  selectedEntityName?: string;
}

export function EpisodicList({
  selectedEntityUuid,
  selectedEntityName,
}: EpisodicListProps) {
  // Conditionally use different hooks based on selection
  const allEpisodicQuery = useAllEpisodics();
  const filteredEpisodicQuery = useEpisodicsByEntity(
    selectedEntityUuid || '',
    50
  );

  // Select appropriate query result
  const query = selectedEntityUuid ? filteredEpisodicQuery : allEpisodicQuery;
  const { data, isLoading, error } = query;

  const heading = selectedEntityName || (selectedEntityUuid ? 'Filtered Notes' : 'All Notes');

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-red-500">
        Error loading episodics: {error.message}
      </div>
    );
  }

  const episodics = data?.episodics || [];
  const count = episodics.length;

  return (
    <div className="p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold">{heading}</h2>
        <p className="text-muted-foreground text-sm mt-1">
          {count} {count === 1 ? 'note' : 'notes'}
        </p>
      </div>

      {count === 0 ? (
        <div className="text-muted-foreground">
          {selectedEntityUuid
            ? 'No notes found for this entity'
            : 'No notes found in the system'}
        </div>
      ) : (
        <div>
          {episodics.map((episodic) => (
            <EpisodicCard key={episodic.uuid} episodic={episodic} />
          ))}
        </div>
      )}
    </div>
  );
}
