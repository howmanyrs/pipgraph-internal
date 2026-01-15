'use client';

import { useParaTree } from '@/hooks/use-para-tree';
import { ParaTreeItem } from './para-tree-item';
import { Skeleton } from '@/components/ui/skeleton';
import { ParaSuggestion } from '@/lib/api';
import { useMemo } from 'react';

interface ParaTreeWithScoresProps {
  suggestions: ParaSuggestion[];
}

/**
 * Normalizes suggestion scores to 0-1 range based on max score
 * Creates a Map for O(1) lookup by UUID
 */
function normalizeSuggestions(
  suggestions: ParaSuggestion[]
): Map<string, number> {
  if (!suggestions || suggestions.length === 0) {
    return new Map();
  }

  const maxScore = Math.max(...suggestions.map((s) => s.score));

  // Handle edge case where all scores are 0
  if (maxScore === 0) {
    return new Map();
  }

  const scoreMap = new Map<string, number>();
  suggestions.forEach((suggestion) => {
    scoreMap.set(suggestion.uuid, suggestion.score / maxScore);
  });

  return scoreMap;
}

export function ParaTreeWithScores({ suggestions }: ParaTreeWithScoresProps) {
  const { data, isLoading, error } = useParaTree();

  // Memoize score normalization to avoid recalculating on every render
  const scoreMap = useMemo(
    () => normalizeSuggestions(suggestions),
    [suggestions]
  );

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
      {scoreMap.size > 0 && (
        <p className="text-xs text-muted-foreground mb-2">
          Showing relevance scores for selected note
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {data.tree.map((node) => (
          <ParaTreeItem
            key={node.id}
            node={node}
            selectedEntityUuid={null} // No selection in Inbox view
            onSelectEntity={() => {}} // No-op in Inbox view
            scoreMap={scoreMap} // Pass normalized scores
          />
        ))}
      </ul>
    </div>
  );
}
