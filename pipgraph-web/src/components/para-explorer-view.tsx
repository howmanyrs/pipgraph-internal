'use client';

import { useState } from 'react';
import { ParaTree } from './para-tree';
import { EpisodicList } from './episodic-list';

export function ParaExplorerView() {
  const [selectedEntityUuid, setSelectedEntityUuid] = useState<string | null>(null);

  return (
    <div className="h-screen flex">
      {/* Left Panel - PARA Tree */}
      <div className="w-[35%] border-r overflow-y-auto bg-background">
        <ParaTree
          selectedEntityUuid={selectedEntityUuid}
          onSelectEntity={setSelectedEntityUuid}
        />
      </div>

      {/* Right Panel - Episodic List */}
      <div className="w-[65%] overflow-y-auto bg-background">
        <EpisodicList selectedEntityUuid={selectedEntityUuid} />
      </div>
    </div>
  );
}
