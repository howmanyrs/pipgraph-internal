import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import ReactMarkdown from 'react-markdown';
import { EpisodicNode } from '@/lib/api';

interface EpisodicCardProps {
  episodic: EpisodicNode;
}

export function EpisodicCard({ episodic }: EpisodicCardProps) {
  // Format date for display
  const formattedDate = episodic.created_at
    ? new Date(episodic.created_at).toLocaleDateString('ru-RU', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : 'Unknown date';

  // Truncate content to 300 characters
  const contentPreview = episodic.content
    ? episodic.content.slice(0, 300) + (episodic.content.length > 300 ? '...' : '')
    : '';

  return (
    <Card className="mb-4">
      <CardHeader>
        <div className="flex justify-between items-start">
          <CardTitle className="text-lg">{episodic.name}</CardTitle>
          <span className="text-sm text-muted-foreground">{formattedDate}</span>
        </div>
      </CardHeader>
      <CardContent>
        <article className="prose prose-sm prose-neutral max-w-none">
          <ReactMarkdown>{contentPreview}</ReactMarkdown>
        </article>
      </CardContent>
    </Card>
  );
}
