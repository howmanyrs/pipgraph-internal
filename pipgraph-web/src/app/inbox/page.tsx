import { AppSidebar } from '@/components/app-sidebar';
import { SidebarInset } from '@/components/ui/sidebar';
import { InboxView } from '@/components/inbox-view';

export default function InboxPage() {
  return (
    <>
      <AppSidebar />
      <SidebarInset>
        <InboxView />
      </SidebarInset>
    </>
  );
}
