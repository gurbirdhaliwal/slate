# Slate Context — VS Code extension

Shows the freshness of the Slate context layer inside the editor:

- **File-tree badges** on `AGENTS.md` and `.slate/*` — `S` stale, `V` needs
  verification (fresh docs stay clean)
- **Status-bar roll-up** — `Slate ● fresh` or `Slate ○ 2 suspect`; click it
  for the per-doc list and jump-to-doc
- **Commands** — `Slate: Sync Context Layer`, `Slate: Refresh Context
  Status`, `Slate: Show Context Status`
- Auto-refreshes (debounced) on file save/create/delete/rename

All trust math lives in the CLI; the extension only renders
`slate status --json`.

## Requirements

- The `slate` CLI on your PATH (`pip install slate-context`), or set
  `slate.executable` in settings to its full path
- The workspace is a git repo with a context layer (`slate init`)

## Install

No build step — the extension is plain JavaScript.

```bash
cd integrations/vscode
npx @vscode/vsce package          # produces slate-context-0.2.0.vsix
code --install-extension slate-context-0.2.0.vsix
```

Or for development: open this folder in VS Code and press **F5**
(Run Extension).
