'use client';

import { ChevronRight, FolderTree, Folder, FileBox, Archive } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar';
import { TreeNode } from '@/lib/api';
import { cn } from '@/lib/utils';

interface ParaTreeItemProps {
  node: TreeNode;
  selectedEntityUuid: string | null;
  onSelectEntity: (uuid: string) => void;
  level?: number;
}

export function ParaTreeItem({
  node,
  selectedEntityUuid,
  onSelectEntity,
  level = 0,
}: ParaTreeItemProps) {
  const isSelected = selectedEntityUuid === node.id;
  const hasChildren = node.children && node.children.length > 0;

  // Icon and color by PARA type
  const getIconAndColor = () => {
    switch (node.type) {
      case 'Project':
        return { Icon: FolderTree, color: 'text-blue-500' };
      case 'Area':
        return { Icon: Folder, color: 'text-purple-500' };
      case 'Resource':
        return { Icon: FileBox, color: 'text-green-500' };
      case 'Archive':
        return { Icon: Archive, color: 'text-gray-400' };
      default:
        return { Icon: Folder, color: 'text-gray-500' };
    }
  };

  const { Icon, color } = getIconAndColor();

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
          <Icon className={cn('size-4', color)} />
          <span>{node.name}</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    );
  }

  // Parent node - collapsible
  return (
    <Collapsible className="group/collapsible">
      <SidebarMenuItem>
        <div className="flex items-center gap-1">
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
            <Icon className={cn('size-4', color)} />
            <span>{node.name}</span>
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
              />
            ))}
          </ul>
        </CollapsibleContent>
      </SidebarMenuItem>
    </Collapsible>
  );
}
