'use client';

import { useState } from 'react';
import { ParaTreeWithScores } from './para-tree-with-scores';
import { UnlinkedEpisodicList } from './unlinked-episodic-list';
import { useMakeSuggestions } from '@/hooks/use-make-suggestions';

export function InboxView() {
  const [selectedNoteUuid, setSelectedNoteUuid] = useState<string | null>(null);

  // Fetch suggestions when a note is selected
  const { data: suggestionsData } = useMakeSuggestions(selectedNoteUuid);

  return (
    <div className="flex h-screen">
      {/* Left Panel - PARA Tree with Score Indicators */}
      <div className="w-[35%] border-r overflow-y-auto bg-background">
        <ParaTreeWithScores
          suggestions={suggestionsData?.suggestions || []}
        />
      </div>

      {/* Right Panel - Unlinked Notes List */}
      <div className="w-[65%] overflow-y-auto bg-background">
        <UnlinkedEpisodicList
          selectedNoteUuid={selectedNoteUuid}
          onSelectNote={setSelectedNoteUuid}
        />
      </div>
    </div>
  );
}
