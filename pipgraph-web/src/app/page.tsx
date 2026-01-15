import { AppSidebar } from '@/components/app-sidebar';
import { NoteCreationForm } from '@/components/note-creation-form';
import { SidebarInset } from '@/components/ui/sidebar';

export default function Home() {
  return (
    <>
      <AppSidebar />
      <SidebarInset>
        <div className="container mx-auto p-6 max-w-4xl">
          <div className="mb-6">
            {/* <h1 className="text-3xl font-bold tracking-tight">Создать заметку</h1> */}
            {/* <p className="text-muted-foreground mt-2">
              Create new notes and extract entities with AI2
            </p> */}
          </div>
          <NoteCreationForm />
        </div>
      </SidebarInset>
    </>
  );
}
