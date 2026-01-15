'use client';

import { useState } from 'react';
import { ParaTreeWithScores } from './para-tree-with-scores';
import { UnlinkedEpisodicList } from './unlinked-episodic-list';
import { useMakeSuggestions } from '@/hooks/use-make-suggestions';

export function InboxView() {
  const [selectedNoteUuid, setSelectedNoteUuid] = useState<string | null>(null);

  // Fetch suggestions when a note is selected
  const { data: suggestionsData } = useMakeSuggestions(selectedNoteUuid);

  // Clear selection (called after successful link+process)
  const clearSelection = () => setSelectedNoteUuid(null);

  return (
    <div className="flex h-screen">
      {/* Left Panel - PARA Tree with Score Indicators */}
      <div className="w-[25%] min-w-[240px] border-r overflow-y-auto bg-background">
        <ParaTreeWithScores
          suggestions={suggestionsData?.suggestions || []}
          selectedNoteUuid={selectedNoteUuid}
          onClearSelection={clearSelection}
        />
      </div>

      {/* Right Panel - Unlinked Notes List */}
      <div className="w-[75%] overflow-y-auto bg-background">
        <UnlinkedEpisodicList
          selectedNoteUuid={selectedNoteUuid}
          onSelectNote={setSelectedNoteUuid}
        />
      </div>
    </div>
  );
}
