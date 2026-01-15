'use client';

import { ChevronRight } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar';
import { TreeNode } from '@/lib/api';
import { cn } from '@/lib/utils';

interface ParaTreeItemProps {
  node: TreeNode;
  selectedEntityUuid: string | null;
  onSelectEntity: (uuid: string) => void;
  level?: number;
  scoreMap?: Map<string, number>; // NEW: uuid -> normalized score (0-1)
}

export function ParaTreeItem({
  node,
  selectedEntityUuid,
  onSelectEntity,
  level = 0,
  scoreMap,
}: ParaTreeItemProps) {
  const isSelected = selectedEntityUuid === node.id;
  const hasChildren = node.children && node.children.length > 0;

  // Calculate score visualization if score exists for this node
  const normalizedScore = scoreMap?.get(node.id);
  const hasScore = normalizedScore !== undefined;

  // Apply minimum threshold for visibility (but show all scores)
  const displayScore = hasScore ? Math.max(normalizedScore!, 0.05) : 0;

  // Score indicator circle (size and opacity based on normalized score)
  const ScoreIndicator = hasScore ? (
    <div
      className="rounded-full ml-auto bg-primary"
      style={{
        width: `${8 + displayScore * 8}px`, // Range: 8.4px (min) to 16px
        height: `${8 + displayScore * 8}px`,
        opacity: displayScore * 0.7 + 0.3, // Range: 0.335 (min) to 1.0
      }}
      title={`Relevance: ${(normalizedScore! * 100).toFixed(0)}%`}
    />
  ) : null;

  // Leaf node (no children) - simple button
  if (!hasChildren) {
    return (
      <SidebarMenuItem>
        <SidebarMenuButton
          onClick={() => onSelectEntity(node.id)}
          className={cn(
            'flex items-center gap-2',
            isSelected && 'bg-sidebar-accent text-sidebar-accent-foreground'
          )}
          style={{ paddingLeft: `${level * 16 + 8}px` }}
        >
          <span className="flex-1">{node.name}</span>
          {ScoreIndicator}
        </SidebarMenuButton>
      </SidebarMenuItem>
    );
  }

  // Parent node - collapsible
  return (
    <Collapsible className="group/collapsible">
      <SidebarMenuItem>
        <div className="flex items-center">
          <CollapsibleTrigger asChild>
            <button
              className="p-1 hover:bg-sidebar-accent rounded"
              style={{ marginLeft: `${level * 16}px` }}
            >
              <ChevronRight className="size-4 transition-transform group-data-[state=open]/collapsible:rotate-90" />
            </button>
          </CollapsibleTrigger>
          <SidebarMenuButton
            onClick={() => onSelectEntity(node.id)}
            className={cn(
              'flex-1 flex items-center gap-2',
              isSelected && 'bg-sidebar-accent text-sidebar-accent-foreground'
            )}
          >
            <span className="flex-1">{node.name}</span>
            {ScoreIndicator}
          </SidebarMenuButton>
        </div>

        <CollapsibleContent>
          <ul className="ml-2">
            {node.children.map((child) => (
              <ParaTreeItem
                key={child.id}
                node={child}
                selectedEntityUuid={selectedEntityUuid}
                onSelectEntity={onSelectEntity}
                level={level + 1}
                scoreMap={scoreMap}
              />
            ))}
          </ul>
        </CollapsibleContent>
      </SidebarMenuItem>
    </Collapsible>
  );
}
