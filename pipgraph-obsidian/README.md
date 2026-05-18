# PipGraph — Obsidian plugin

In-vault UI for the PipGraph triage flow. This is the Obsidian client; the backend (FastAPI + Neo4j) lives in [`../backend`](../backend) and is the source of truth for graph state.

> **Status:** M1 (skeleton) only. The plugin loads, registers a right-sidebar panel, ribbon icon, and command — the panel itself is empty. See [`.docs/plans/`](./.docs/plans) for the roadmap and [`CLAUDE.md`](./CLAUDE.md) for direction.

## Develop against a vault

1. `npm install`
2. Symlink (or copy) this directory into a dev vault as a community plugin:
   ```bash
   ln -s "$PWD" /path/to/your-vault/.obsidian/plugins/pipgraph
   ```
3. `npm run dev` — esbuild watches `src/` and rebuilds `main.js` on save.
4. In Obsidian: **Settings → Community plugins → enable "PipGraph"**. Open the panel via the ribbon icon or the **PipGraph: Open triage panel** command.
5. Reload Obsidian (`Ctrl+R` / `Cmd+R`) after each rebuild to pick up the new bundle.

## Build for distribution

```bash
npm run build
```

Produces a minified `main.js`. A release bundle is `manifest.json` + `main.js` + `styles.css`.

## Layout

```
src/
├── main.ts                   # Plugin entry — onload / onunload / commands
└── views/
    └── TriagePanelView.ts    # Right-sidebar ItemView (empty placeholder in M1)
manifest.json                 # Obsidian plugin metadata
esbuild.config.mjs            # Build pipeline (dev watch / prod minify)
tsconfig.json                 # TypeScript strict mode
styles.css                    # Reserved for M5 (decoration)
```

See [`CLAUDE.md`](./CLAUDE.md) for the design direction and [`.docs/plans/01-skeleton.md`](./.docs/plans/01-skeleton.md) for what M1 covers.
