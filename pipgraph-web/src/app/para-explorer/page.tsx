import { AppSidebar } from '@/components/app-sidebar';
import { ParaExplorerView } from '@/components/para-explorer-view';
import { SidebarInset } from '@/components/ui/sidebar';

export default function ParaExplorerPage() {
  return (
    <>
      <AppSidebar />
      <SidebarInset>
        <ParaExplorerView />
      </SidebarInset>
    </>
  );
}
