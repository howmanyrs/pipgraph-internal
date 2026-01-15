'use client';

import { useUnlinkedEpisodics } from '@/hooks/use-unlinked-episodics';
import { EpisodicCard } from './episodic-card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface UnlinkedEpisodicListProps {
  selectedNoteUuid: string | null;
  onSelectNote: (uuid: string) => void;
}

export function UnlinkedEpisodicList({
  selectedNoteUuid,
  onSelectNote,
}: UnlinkedEpisodicListProps) {
  const { data, isLoading, error } = useUnlinkedEpisodics(100);

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
        Error loading unlinked episodics: {error.message}
      </div>
    );
  }

  const episodics = data?.episodics || [];
  const count = episodics.length;

  return (
    <div className="p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Unlinked Notes</h2>
        <p className="text-muted-foreground text-sm mt-1">
          {count} {count === 1 ? 'note' : 'notes'} waiting for categorization
        </p>
      </div>

      {count === 0 ? (
        <div className="text-muted-foreground">
          No unlinked notes found. All notes are categorized!
        </div>
      ) : (
        <div className="space-y-2">
          {episodics.map((episodic) => (
            <div
              key={episodic.uuid}
              onClick={() => onSelectNote(episodic.uuid)}
              className={cn(
                'cursor-pointer rounded-md transition-all',
                selectedNoteUuid === episodic.uuid &&
                  'ring-2 ring-primary ring-offset-2'
              )}
            >
              <EpisodicCard episodic={episodic} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
