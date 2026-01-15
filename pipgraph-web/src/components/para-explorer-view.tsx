'use client';

import { useState } from 'react';
import { ParaTree } from './para-tree';
import { EpisodicList } from './episodic-list';
import { useParaTree } from '@/hooks/use-para-tree';
import { TreeNode } from '@/lib/api';

// Helper function to find node by UUID in tree
function findNodeByUuid(nodes: TreeNode[], uuid: string): TreeNode | null {
  for (const node of nodes) {
    if (node.id === uuid) return node;
    if (node.children.length > 0) {
      const found = findNodeByUuid(node.children, uuid);
      if (found) return found;
    }
  }
  return null;
}

export function ParaExplorerView() {
  const [selectedEntityUuid, setSelectedEntityUuid] = useState<string | null>(null);
  const { data: treeData } = useParaTree();

  // Find selected node name
  const selectedNode = selectedEntityUuid && treeData?.tree
    ? findNodeByUuid(treeData.tree, selectedEntityUuid)
    : null;

  return (
    <div className="h-screen flex">
      {/* Left Panel - PARA Tree */}
      <div className="w-[25%] min-w-[240px] border-r overflow-y-auto bg-background">
        <ParaTree
          selectedEntityUuid={selectedEntityUuid}
          onSelectEntity={setSelectedEntityUuid}
        />
      </div>

      {/* Right Panel - Episodic List */}
      <div className="w-[75%] overflow-y-auto bg-background">
        <EpisodicList
          selectedEntityUuid={selectedEntityUuid}
          selectedEntityName={selectedNode?.name}
        />
      </div>
    </div>
  );
}
