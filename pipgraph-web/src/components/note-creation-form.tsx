'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card } from '@/components/ui/card';
import { useCreateEpisode } from '@/hooks/use-create-episode';

// Zod schema for form validation
const noteSchema = z.object({
  content: z.string()
    .min(10, 'Note content must be at least 10 characters'),
});

type NoteFormData = z.infer<typeof noteSchema>;

export function NoteCreationForm() {
  const { mutate: submitNote, isPending } = useCreateEpisode();

  const form = useForm<NoteFormData>({
    resolver: zodResolver(noteSchema),
    defaultValues: {
      content: '',
    },
  });

  const onSubmit = (data: NoteFormData) => {
    // Map form data to backend CreateEpisodeRequest schema
    // name is optional - backend will auto-generate via LLM
    const episodeData = {
      content: data.content,
      source_description: 'Web UI',
    };

    submitNote(episodeData, {
      onSuccess: (response) => {
        if (response.success && response.uuid) {
          toast.success('Note saved successfully', {
            description: response.name
              ? `Name: ${response.name}`
              : `UUID: ${response.uuid.slice(0, 8)}...`,
          });
          form.reset();
        } else {
          toast.error('Failed to save note', {
            description: response.error || 'Unknown error',
          });
        }
      },
      onError: (error) => {
        toast.error('Failed to save note', {
          description: error.message,
        });
      },
    });
  };

  return (
    <Card className="p-6">
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <div>
          {/* <Label htmlFor="content">Note Content</Label> */}
          <Textarea
            id="content"
            placeholder="Текст заметки.."
            rows={15}
            {...form.register('content')}
          />
          {form.formState.errors.content && (
            <p className="text-sm text-red-600 mt-1">
              {form.formState.errors.content.message}
            </p>
          )}
        </div>

        <Button type="submit" disabled={isPending} className="w-full">
          {isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Send className="mr-2 h-4 w-4" />
              Save Note
            </>
          )}
        </Button>
      </form>
    </Card>
  );
}
