'use client';

import { ChevronRight, Check, Loader2 } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar';
import { TreeNode } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useLinkAndProcess } from '@/hooks/use-link-and-process';
import { toast } from 'sonner';

interface ParaTreeItemProps {
  node: TreeNode;
  selectedEntityUuid: string | null;
  onSelectEntity: (uuid: string) => void;
  level?: number;
  scoreMap?: Map<string, number>; // uuid -> normalized score (0-1)
  selectedNoteUuid?: string | null; // Selected unlinked note for linking
  onClearSelection?: () => void; // Callback to clear selection after successful link
}

export function ParaTreeItem({
  node,
  selectedEntityUuid,
  onSelectEntity,
  level = 0,
  scoreMap,
  selectedNoteUuid,
  onClearSelection,
}: ParaTreeItemProps) {
  const isSelected = selectedEntityUuid === node.id;
  const hasChildren = node.children && node.children.length > 0;

  // Link and process mutation
  const { mutate: linkAndProcess, isPending } = useLinkAndProcess();

  // Calculate score visualization if score exists for this node
  const normalizedScore = scoreMap?.get(node.id);
  const hasScore = normalizedScore !== undefined;

  // Apply minimum threshold for visibility (but show all scores)
  const displayScore = hasScore ? Math.max(normalizedScore!, 0.05) : 0;

  // Score indicator circle (size and opacity based on normalized score)
  const ScoreIndicator = hasScore ? (
    <div
      className="rounded-full bg-primary"
      style={{
        width: `${8 + displayScore * 8}px`, // Range: 8.4px (min) to 16px
        height: `${8 + displayScore * 8}px`,
        opacity: displayScore * 0.7 + 0.3, // Range: 0.335 (min) to 1.0
      }}
      title={`Relevance: ${(normalizedScore! * 100).toFixed(0)}%`}
    />
  ) : null;

  // Checkmark button: render when note is selected (visibility controlled by hover/click CSS)
  const showCheckmark = selectedNoteUuid !== null;

  // Button click handler
  const handleLinkClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Don't trigger parent onClick

    if (!selectedNoteUuid) return;

    linkAndProcess(
      {
        episodic_uuid: selectedNoteUuid,
        entity_uuid: node.id,
      },
      {
        onSuccess: () => {
          toast.success(`Note linked to ${node.name}`, {
            description: 'Note has been categorized and processed',
          });
          // Clear selection after successful link
          onClearSelection?.();
        },
        onError: (error) => {
          toast.error('Failed to link note', {
            description: error.message,
          });
        },
      }
    );
  };

  // Leaf node (no children) - simple button
  if (!hasChildren) {
    return (
      <SidebarMenuItem className="group/item">
        <SidebarMenuButton
          onClick={() => onSelectEntity(node.id)}
          className={cn(
            'flex items-center gap-2',
            isSelected && 'bg-sidebar-accent text-sidebar-accent-foreground'
          )}
          style={{ paddingLeft: `${level * 16 + 8}px` }}
        >
          <span className="flex-1">{node.name}</span>
          <div className="flex items-center gap-1 ml-auto">
            {ScoreIndicator}
            {showCheckmark && (
              <span
                onClick={handleLinkClick}
                role="button"
                tabIndex={0}
                className={cn(
                  'inline-flex items-center justify-center rounded-md',
                  'h-6 w-6 text-sm transition-all cursor-pointer',
                  'hover:bg-accent hover:text-accent-foreground',
                  'opacity-0 group-hover/item:opacity-100',
                  isPending && 'pointer-events-none opacity-50'
                )}
                title="Link this note to entity"
              >
                {isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Check className="size-4" />
                )}
              </span>
            )}
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>
    );
  }

  // Parent node - collapsible
  return (
    <Collapsible className="group/collapsible">
      <SidebarMenuItem className="group/item">
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
            <div className="flex items-center gap-1 ml-auto">
              {ScoreIndicator}
              {showCheckmark && (
                <span
                  onClick={handleLinkClick}
                  role="button"
                  tabIndex={0}
                  className={cn(
                    'inline-flex items-center justify-center rounded-md',
                    'h-6 w-6 text-sm transition-all cursor-pointer',
                    'hover:bg-accent hover:text-accent-foreground',
                    'opacity-0 group-hover/item:opacity-100',
                    isPending && 'pointer-events-none opacity-50'
                  )}
                  title="Link this note to entity"
                >
                  {isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Check className="size-4" />
                  )}
                </span>
              )}
            </div>
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
                selectedNoteUuid={selectedNoteUuid}
                onClearSelection={onClearSelection}
              />
            ))}
          </ul>
        </CollapsibleContent>
      </SidebarMenuItem>
    </Collapsible>
  );
}
