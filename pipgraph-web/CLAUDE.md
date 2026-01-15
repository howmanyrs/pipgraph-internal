# PipGraph Web — Quick Reference for Claude Code

## Project Overview

**pipgraph-web** is a Next.js-based web interface for the PipGraph knowledge graph system. It provides a rapid prototyping UI for interacting with the PipGraph backend API, focusing on note processing, entity management, and PARA organization.

**Architecture**: Frontend consumes REST API from `backend/app/api` (FastAPI).

## Technology Stack

### Core Framework
- **Next.js 16.1.1** (App Router, TypeScript, React 19)
- **TypeScript** (strict mode enabled)
- **Node.js** packages managed via npm

### Styling & Components
- **Tailwind CSS v4** (@tailwindcss/postcss)
- **shadcn/ui** (New York style, **use MCP tools for all operations** - see `SHADCN.md`)
- **lucide-react** icons (preferred for all icons)
- **class-variance-authority** + **clsx** + **tailwind-merge** for dynamic styles

### Data Fetching & State
- **TanStack Query v5** (@tanstack/react-query) - handles all server state, caching, mutations
- **React Hook Form** + **Zod** - form management and validation
- **@hookform/resolvers** - integrates Zod with React Hook Form

### Content Rendering
- **react-markdown** v10 - renders Markdown from episodic notes

## Quick Start

```bash
cd pipgraph-web/
npm install              # Dependencies already installed
npm run dev              # Start dev server (http://localhost:3000)
npm run build            # Production build
npm run lint             # ESLint check
```

**Backend dependency**: Ensure `backend/` is running at `http://localhost:8001` (or configure via environment variables).

## Project Structure

```
pipgraph-web/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── layout.tsx         # Root layout (providers, fonts)
│   │   ├── page.tsx           # Home page (Inbox with note form)
│   │   └── globals.css        # Global styles + Tailwind base
│   ├── components/            # React components
│   │   ├── ui/                # shadcn/ui components
│   │   │   ├── button.tsx     # Button component
│   │   │   ├── card.tsx       # Card container
│   │   │   ├── label.tsx      # Form labels
│   │   │   ├── textarea.tsx   # Multi-line input
│   │   │   ├── sidebar.tsx    # Sidebar navigation
│   │   │   ├── sonner.tsx     # Toast notifications
│   │   │   └── skeleton.tsx   # Loading placeholders
│   │   ├── app-sidebar.tsx    # Application sidebar (Inbox nav)
│   │   ├── note-creation-form.tsx  # Note creation form
│   │   └── providers.tsx      # Client-side providers wrapper
│   ├── lib/                   # Utilities
│   │   ├── api.ts             # Typed API client for backend
│   │   └── utils.ts           # cn() helper for className merging
│   ├── hooks/                 # Custom React hooks
│   │   └── use-create-episode.ts  # TanStack Query mutation for episodes
│   └── .todo/                 # Implementation plans and tasks
├── public/                    # Static assets
├── components.json            # shadcn/ui configuration
├── tsconfig.json              # TypeScript config
├── next.config.ts             # Next.js config
└── package.json               # Dependencies
```

## Backend API Integration

### Base URL
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_PREFIX = '/api/v1/dev';
```

### Key Endpoints (from `backend/app/api/endpoints/dev.py`)

**⚠️ API is evolving**: Backend API is actively developed and new endpoints will be added. Always check `backend/app/api/endpoints/dev.py` for the latest available endpoints.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/dev/process-note` | Process note with full LLM pipeline |
| POST | `/dev/process-existing-episode` | Re-process existing episodic node |
| GET | `/dev/episodic?note_path={path}` | Get episodic by file path (note name) |
| GET | `/dev/episodic/list?limit={n}` | List all episodics (ordered by created_at) |
| GET | `/dev/episodic/unlinked?limit={n}` | List episodics without PARA entity links (Inbox) |
| GET | `/dev/episodics/by-entity?entity_uuid={uuid}&limit={n}` | Get episodics that mention specific entity |
| POST | `/dev/episode` | Create lightweight episodic (auto-generate name if not provided) |
| POST | `/dev/para-entity` | Create PARA entity (Project/Area/Resource/Archive) |
| GET | `/dev/para-entity/list?limit={n}&para_type={types}` | List PARA entities with optional filtering |
| POST | `/dev/link-entity-episode` | Link entity to episode (MENTIONS relationship) |
| POST | `/dev/link-para-nodes` | Link PARA entities (BELONGS_TO hierarchy) |
| POST | `/dev/make-suggestions` | Hybrid search for relevant PARA entities (BM25 + vector) |
| DELETE | `/dev/node/{node_uuid}` | Delete node (Episodic or Entity) with all relationships |
| GET | `/dev/para-tree` | Get hierarchical PARA tree structure (recursive) |

### TanStack Query Pattern

**Always use TanStack Query** for API calls. Never use raw `fetch()` in components.

```typescript
// Example: Fetch episodics list
import { useQuery } from '@tanstack/react-query';

function EpisodicsList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['episodics', { limit: 100 }],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/v1/dev/episodic/list?limit=100`);
      if (!res.ok) throw new Error('Failed to fetch');
      return res.json();
    },
  });

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return <div>{data.episodics.map(/* render */)}</div>;
}
```

**Mutations example** (optimistic updates):
```typescript
const mutation = useMutation({
  mutationFn: async (uuid: string) => {
    const res = await fetch(`${API_BASE}/api/v1/dev/episodic`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uuid }),
    });
    if (!res.ok) throw new Error('Delete failed');
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['episodics'] });
  },
});
```

## Working with shadcn/ui Components

### Installed Components

The following shadcn/ui components are already available in `src/components/ui/`:

- **button.tsx** - Button with variants (default, destructive, outline, ghost, link)
- **card.tsx** - Card container with header, content, footer
- **label.tsx** - Form field labels
- **textarea.tsx** - Multi-line text input
- **sidebar.tsx** - Sidebar navigation with context provider
- **sonner.tsx** - Toast notifications (uses `sonner` library)
- **skeleton.tsx** - Loading state placeholders

### Adding New Components

**IMPORTANT: Use MCP Server as PRIMARY method** for working with shadcn/ui components.

This project has an active shadcn MCP server configured. **Always use MCP tools** for browsing, searching, and adding components.

#### MCP Workflow (RECOMMENDED)

**1. Search for components:**
```typescript
// Search by keyword
mcp__shadcn__search_items_in_registries({
  registries: ["@shadcn"],
  query: "dialog",
  limit: 5
})
```

**2. View component details:**
```typescript
// Get component info and dependencies
mcp__shadcn__view_items_in_registries({
  items: ["@shadcn/dialog"]
})
```

**3. Get usage examples:**
```typescript
// Find demo/example code
mcp__shadcn__get_item_examples_from_registries({
  registries: ["@shadcn"],
  query: "dialog-demo"
})
```

**4. Get installation command:**
```typescript
// Get the CLI command to add components
mcp__shadcn__get_add_command_for_items({
  items: ["@shadcn/dialog", "@shadcn/alert-dialog"]
})
// Returns: npx shadcn@latest add @shadcn/dialog @shadcn/alert-dialog
```

**Full shadcn/ui documentation**: See `SHADCN.md` in this directory for complete component catalog and guides.

#### Manual Installation (Fallback)

If MCP server is unavailable:

1. Visit https://ui.shadcn.com/docs/components/{component-name}
2. Copy component source code
3. Save to `src/components/ui/{component-name}.tsx`
4. Install required dependencies (usually @radix-ui packages)
5. Add `'use client'` directive if component uses React hooks

**Important**: All components using `createContext`, `useState`, or other React hooks MUST have `'use client'` at the top.

### Component Configuration

**Style**: New York (defined in `components.json`)
**Icons**: Use `lucide-react` exclusively
**Aliases**: Configured in `tsconfig.json` paths:
- `@/components` → `src/components`
- `@/lib` → `src/lib`
- `@/hooks` → `src/hooks`

## Key Development Principles

### 1. **Minimize Over-Engineering**
- Build only what's requested, no extra features
- Avoid premature abstractions
- Three similar lines > complex utility function
- Don't add error handling for impossible scenarios

### 2. **Type Safety First**Create new notes and extract entities with A
- Use Zod schemas for form validation
- Derive TypeScript types from Zod: `type FormData = z.infer<typeof schema>`
- Mirror backend Pydantic models in frontend Zod schemas when possible

### 3. **Component Patterns**

**Server Components (default)**: Use for static content, direct data fetching
**Client Components**: Use for interactivity (`'use client'` directive)

```typescript
// Server Component (default, no directive needed)
export default async function Page() {
  const data = await fetch(/* ... */);
  return <div>{data}</div>;
}

// Client Component (requires 'use client')
'use client';
import { useState } from 'react';

export function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
```

### 4. **Styling with Tailwind**

Use the `cn()` utility for conditional classes:

```typescript
import { cn } from '@/lib/utils';

<div className={cn(
  "base-classes",
  isActive && "active-classes",
  error && "error-classes"
)} />
```

### 5. **Markdown Rendering**

Use `react-markdown` with Tailwind Typography (when installed):

```typescript
import ReactMarkdown from 'react-markdown';

<article className="prose prose-neutral max-w-none">
  <ReactMarkdown>{noteContent}</ReactMarkdown>
</article>
```

## Using Existing Components

### API Client

The typed API client is available at `src/lib/api.ts`. All backend endpoints are typed:

```typescript
import { createEpisode, listEpisodics } from '@/lib/api';

// Create episode (fast, no LLM)
const result = await createEpisode({
  name: 'note-2025-01-14.md',
  content: 'My note content',
  source_description: 'Web UI',
});

// List all episodics
const { episodics, count } = await listEpisodics({ limit: 100 });
```

### Custom Hooks

**useCreateEpisode** - TanStack Query mutation for creating episodes:

```typescript
'use client';
import { useCreateEpisode } from '@/hooks/use-create-episode';
import { toast } from 'sonner';

function MyComponent() {
  const { mutate: createEpisode, isPending } = useCreateEpisode();

  const handleSubmit = () => {
    createEpisode(
      { name: 'note.md', content: 'Content', source_description: 'Web' },
      {
        onSuccess: (response) => {
          toast.success('Note saved!');
        },
        onError: (error) => {
          toast.error('Failed to save', { description: error.message });
        },
      }
    );
  };

  return <button onClick={handleSubmit} disabled={isPending}>Save</button>;
}
```

### Toast Notifications

Use Sonner for toast notifications:

```typescript
'use client';
import { toast } from 'sonner';

// Success toast
toast.success('Note saved successfully', {
  description: 'Episode UUID: 12345...',
});

// Error toast
toast.error('Failed to save note', {
  description: 'Network error',
});

// Loading toast
const toastId = toast.loading('Saving...');
// Later: toast.dismiss(toastId);
```

### Sidebar Navigation

Current sidebar structure in `AppSidebar`:

```typescript
<Sidebar>
  <SidebarContent>
    <SidebarGroup>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton asChild>
            <Link href="/">
              <Inbox />
              <span>Inbox</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup>
  </SidebarContent>
</Sidebar>
```

To add new navigation items, add more `SidebarMenuItem` components.

## Common Tasks

### Task 1: Create a New Page

```bash
# Create page file
touch src/app/inbox/page.tsx
```

```typescript
// src/app/inbox/page.tsx
export default function InboxPage() {
  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold">Inbox</h1>
      {/* Content */}
    </div>
  );
}
```

### Task 2: Fetch Data with TanStack Query

```typescript
'use client';
import { useQuery } from '@tanstack/react-query';

export function DataList() {
  const { data, isLoading } = useQuery({
    queryKey: ['items'],
    queryFn: async () => {
      const res = await fetch('/api/v1/dev/episodic/list');
      return res.json();
    },
  });

  if (isLoading) return <p>Loading...</p>;
  return <ul>{data.episodics.map(/* ... */)}</ul>;
}
```

### Task 3: Create a Form with Validation

```typescript
'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const schema = z.object({
  name: z.string().min(1, 'Required'),
  content: z.string().min(10, 'Min 10 characters'),
});

type FormData = z.infer<typeof schema>;

export function NoteForm() {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = (data: FormData) => {
    console.log(data);
    // Submit via mutation
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <input {...register('name')} />
      {errors.name && <p>{errors.name.message}</p>}
      {/* ... */}
    </form>
  );
}
```

## Environment Variables

Create `.env.local` for local overrides:

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**IMPORTANT**: All client-side env vars MUST be prefixed with `NEXT_PUBLIC_`.

## Testing Strategy

**Current focus**: Rapid prototyping. Formal testing not yet configured.

**Future**: Consider Vitest + React Testing Library for unit tests, Playwright for E2E.

## Common Pitfalls

1. **Forgetting `'use client'`**: If you use hooks (useState, useQuery, useContext) or `createContext`, add `'use client'` at top.
   - **Critical**: Components using `React.createContext` MUST have `'use client'` directive
   - Error: `createContext only works in Client Components`

2. **Mixing server/client**: Server components can't use client-only hooks. Compose them correctly.
   - Server components (default): Good for static content, data fetching
   - Client components (`'use client'`): Required for interactivity, state, effects

3. **Not using TanStack Query**: Always use it for API calls. Don't write manual loading states.
   - Use custom hooks like `useCreateEpisode` for mutations
   - Use `useQuery` for data fetching with automatic caching

4. **Hardcoded API URLs**: Use environment variables or the typed API client from `src/lib/api.ts`.
   - Never hardcode `http://localhost:8000` in components
   - Use `NEXT_PUBLIC_API_URL` in `.env.local`

5. **Skipping Zod validation**: Always validate form inputs. Backend errors are harder to debug.
   - Use `zodResolver` with React Hook Form
   - Mirror backend Pydantic schemas in frontend Zod schemas

6. **Incorrect API endpoints**: Backend endpoint is `/dev/episode`, not `/dev/create-episode`.
   - Always verify against `backend/app/api/endpoints/dev.py`
   - Use typed API client to avoid typos

## Integration with Backend

**⚠️ Backend is evolving**: The backend API is under active development. New endpoints and schema changes will be introduced regularly. Always verify against the latest `backend/app/api/endpoints/dev.py` and `backend/app/api/schemas/dev.py`.

**Schema synchronization**: When backend Pydantic models change (e.g., `ProcessNoteRequest`), update corresponding Zod schemas in frontend.

**Example mapping**:
```python
# backend/app/api/schemas/dev.py
class ProcessNoteRequest(BaseModel):
    name: str
    episode_body: str
    source_description: str | None = None
```

```typescript
// frontend Zod schema
const processNoteSchema = z.object({
  name: z.string(),
  episode_body: z.string(),
  source_description: z.string().optional(),
});
```

## Current Implementation Status

### ✅ Completed Features

**Infrastructure**:
- ✅ TanStack Query Provider configured in `src/components/providers.tsx`
- ✅ Typed API client (`src/lib/api.ts`) for all backend endpoints
- ✅ shadcn/ui components installed (button, card, textarea, label, sidebar, sonner, skeleton)
- ✅ Environment configuration (`.env.local` for `NEXT_PUBLIC_API_URL`)

**UI Components**:
- ✅ Fixed vertical sidebar with navigation (`AppSidebar`)
- ✅ Note creation form with validation (`NoteCreationForm`)
- ✅ Toast notifications for user feedback (Sonner)
- ✅ Custom hook for episode creation (`useCreateEpisode`)

**Current Page**:
- ✅ **Home (Inbox)** - `/` - Create new notes with fast episode creation (no LLM wait)

### 🚧 Next Steps

📋 **See `.todo/setup-tasks.md`** for detailed task list.

**Immediate priorities**:
1. **Episodics list view** - Display created notes in Inbox
2. **PARA entity management** - CRUD interface for Projects/Areas/Resources/Archives
3. **Search/suggestions interface** - Use `/dev/make-suggestions` endpoint
4. **Markdown preview** - Render note content with `react-markdown`
5. **Navigation expansion** - Add more sidebar items (PARA sections, Settings)

### 📝 Implementation Pattern

When adding new features, follow this pattern:

1. **Create custom hook** (if API call needed) in `src/hooks/`
2. **Create component** in `src/components/`
3. **Add to page** or create new page in `src/app/`
4. **Use existing shadcn/ui components** from `src/components/ui/`
5. **Update documentation** in `.todo/setup-tasks.md`

## Documentation References

### Project Documentation
- **shadcn/ui Guide**: `SHADCN.md` - complete shadcn/ui component catalog and documentation (mirror of https://ui.shadcn.com/llms.txt)
- **Setup Tasks**: `.todo/setup-tasks.md` - initialization checklist
- **Backend API**: `backend/app/api/endpoints/dev.py` - all available endpoints
- **Backend Schemas**: `backend/app/api/schemas/dev.py` - Pydantic models for API
- **Backend CLAUDE.md**: `backend/CLAUDE.md` - backend architecture guide

### External Documentation
- **Next.js Docs**: https://nextjs.org/docs
- **TanStack Query**: https://tanstack.com/query/latest/docs/framework/react/overview
- **shadcn/ui**: https://ui.shadcn.com/ (use MCP server for components, see `SHADCN.md` for full reference)
- **Tailwind CSS**: https://tailwindcss.com/docs

---

## Quick Reference Summary

### ✅ What's Working
- Dev server: `npm run dev` → http://localhost:3000
- Production build: `npm run build` (working after adding `'use client'` to sidebar)
- Linting: `npm run lint` (0 errors, 0 warnings)
- Backend API: Typed client in `src/lib/api.ts`
- UI: Sidebar navigation + Note creation form + Toast notifications

### 🎯 Key Files to Know
- **`SHADCN.md`** - Complete shadcn/ui component reference (use with MCP)
- **`src/lib/api.ts`** - All backend API functions (typed)
- **`src/components/providers.tsx`** - TanStack Query + Sidebar + Toast providers
- **`src/hooks/use-create-episode.ts`** - Mutation hook for creating episodes
- **`src/components/note-creation-form.tsx`** - Main form component
- **`.todo/setup-tasks.md`** - Completed and pending tasks

### 🚨 Critical Requirements
1. **Always** use shadcn MCP tools for browsing and adding UI components (see `SHADCN.md`)
2. **Always** add `'use client'` to components using hooks or createContext
3. **Always** use TanStack Query for API calls (never raw fetch in components)
4. **Always** validate forms with Zod + React Hook Form
5. **Always** use typed API client from `src/lib/api.ts`
6. **Never** skip error handling - use toast notifications for user feedback

---

**Golden Rule for Claude Code**: When in doubt, use existing patterns from the codebase, TanStack Query for data, and keep it simple. This is a prototype, not a production system.
