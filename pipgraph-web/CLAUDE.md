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
- **shadcn/ui** (New York style, via MCP server)
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

**Backend dependency**: Ensure `backend/` is running at `http://localhost:8000` (or configure via environment variables).

## Project Structure

```
pipgraph-web/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── layout.tsx         # Root layout (providers, fonts)
│   │   ├── page.tsx           # Home page
│   │   └── globals.css        # Global styles + Tailwind base
│   ├── components/            # React components
│   │   └── ui/                # shadcn/ui components (auto-generated via MCP)
│   ├── lib/                   # Utilities
│   │   └── utils.ts           # cn() helper for className merging
│   └── hooks/                 # Custom React hooks (create as needed)
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
| GET | `/dev/episodic?uuid={uuid}` | Get episodic by UUID |
| GET | `/dev/episodic?name={name}` | Get episodic by name (file path) |
| GET | `/dev/episodics` | List all episodics |
| POST | `/dev/create-episode` | Create lightweight episodic |
| POST | `/dev/para-entity` | Create PARA entity (Project/Area/Resource/Archive) |
| GET | `/dev/para-entities` | List PARA entities |
| POST | `/dev/link-entity-episode` | Link entity to episode |
| POST | `/dev/make-suggestions` | Hybrid search for relevant PARA entities |

### TanStack Query Pattern

**Always use TanStack Query** for API calls. Never use raw `fetch()` in components.

```typescript
// Example: Fetch episodics list
import { useQuery } from '@tanstack/react-query';

function EpisodicsList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['episodics', { limit: 100 }],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/v1/dev/episodics?limit=100`);
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

## Working with shadcn/ui via MCP Server

**IMPORTANT**: This project uses an MCP server for shadcn/ui components. Claude Code has direct access to component source via MCP tools.

### Adding Components

When you need a shadcn component (e.g., Button, Card, Dialog):

1. **Fetch via MCP tool**: Use `mcp__shadcn-ui-mcp__get_component` to get source code
2. **Place in `src/components/ui/`**: Save as `{component-name}.tsx`
3. **Import and use**: Import from `@/components/ui/{component-name}`

```typescript
// Example: Adding a Button component
import { mcp__shadcn_ui_mcp__get_component } from 'mcp-tools';

// Fetch button source
const buttonSource = await mcp__shadcn_ui_mcp__get_component({ componentName: 'button' });

// Save to src/components/ui/button.tsx
// Then use:
import { Button } from '@/components/ui/button';
```

### Available MCP Tools

- `mcp__shadcn-ui-mcp__list_components` - List all available components
- `mcp__shadcn-ui-mcp__get_component` - Get component source code
- `mcp__shadcn-ui-mcp__get_component_demo` - Get usage examples
- `mcp__shadcn-ui-mcp__get_component_metadata` - Get component info
- `mcp__shadcn-ui-mcp__list_blocks` - List pre-built UI blocks (e.g., `dashboard-01`, `login-02`)
- `mcp__shadcn-ui-mcp__get_block` - Get full block source with components

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

### 2. **Type Safety First**
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
      const res = await fetch('/api/v1/dev/episodics');
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

1. **Forgetting `'use client'`**: If you use hooks (useState, useQuery), add `'use client'` at top.
2. **Mixing server/client**: Server components can't use client-only hooks. Compose them correctly.
3. **Not using TanStack Query**: Always use it for API calls. Don't write manual loading states.
4. **Hardcoded API URLs**: Use environment variables or a centralized config.
5. **Skipping Zod validation**: Always validate form inputs. Backend errors are harder to debug.

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

## Next Steps

📋 **See `.todo/setup-tasks.md`** for detailed initialization checklist.

Quick overview:
1. **Setup providers**: Create `QueryClientProvider` in `src/app/layout.tsx`
2. **Build Inbox view**: List episodics pending classification
3. **PARA management**: CRUD interface for Projects/Areas/Resources
4. **Search interface**: Use `/dev/make-suggestions` endpoint
5. **Note viewer**: Render episodic content with Markdown

## Documentation References

### Project Documentation
- **Setup Tasks**: `.todo/setup-tasks.md` - initialization checklist
- **Backend API**: `backend/app/api/endpoints/dev.py` - all available endpoints
- **Backend Schemas**: `backend/app/api/schemas/dev.py` - Pydantic models for API
- **Backend CLAUDE.md**: `backend/CLAUDE.md` - backend architecture guide

### External Documentation
- **Next.js Docs**: https://nextjs.org/docs
- **TanStack Query**: https://tanstack.com/query/latest/docs/framework/react/overview
- **shadcn/ui**: https://ui.shadcn.com/ (use MCP server for components)
- **Tailwind CSS**: https://tailwindcss.com/docs

---

**Golden Rule for Claude Code**: When in doubt, use MCP tools for shadcn components, TanStack Query for data, and keep it simple. This is a prototype, not a production system.
