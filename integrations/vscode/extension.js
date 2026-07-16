// Slate Context — VS Code integration (Phase 3 editor surface).
//
// Plain JavaScript, no dependencies, no build step: the extension shells out
// to the `slate` CLI (`status --json`) and renders the result as
//   - file-tree badges on AGENTS.md and .slate/* (F fresh / S stale / V needs-verification)
//   - a status-bar roll-up (click for the doc list; offers one-click sync)
// All trust math stays in the CLI — this is presentation only.

const vscode = require("vscode");
const cp = require("child_process");

const ICONS = { fresh: "●", stale: "○", "needs-verification": "◐" };
const BADGES = { fresh: "F", stale: "S", "needs-verification": "V" };

let statusByPath = new Map(); // repo-relative doc path -> {status, reason}
let decorationEmitter;
let statusBar;
let refreshTimer;

function workspaceRoot() {
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders.length ? folders[0].uri.fsPath : undefined;
}

function slateExecutable() {
  return vscode.workspace.getConfiguration("slate").get("executable", "slate");
}

function runSlate(args) {
  const root = workspaceRoot();
  return new Promise((resolve, reject) => {
    if (!root) return reject(new Error("no workspace folder open"));
    cp.execFile(
      slateExecutable(),
      ["-C", root, ...args],
      { timeout: 15000 },
      (error, stdout, stderr) => {
        // Exit 2 = no layer / not a git repo: not an error worth surfacing.
        if (error && error.code === 2) return resolve(null);
        if (error && !stdout) return reject(new Error(stderr || String(error)));
        resolve(stdout);
      }
    );
  });
}

async function refresh() {
  try {
    const out = await runSlate(["status", "--json"]);
    statusByPath = new Map();
    if (out) {
      for (const doc of JSON.parse(out)) {
        statusByPath.set(doc.path, { status: doc.status, reason: doc.reason });
      }
    }
  } catch (error) {
    statusByPath = new Map();
    console.warn("slate refresh failed:", error.message);
  }
  updateStatusBar();
  decorationEmitter.fire(undefined); // re-decorate everything
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refresh, 800); // debounce bursts of saves
}

function updateStatusBar() {
  if (!statusByPath.size) {
    statusBar.hide();
    return;
  }
  const counts = { fresh: 0, stale: 0, "needs-verification": 0 };
  for (const { status } of statusByPath.values()) counts[status]++;
  const problems = counts.stale + counts["needs-verification"];
  statusBar.text = problems
    ? `Slate ${ICONS.stale} ${problems} suspect`
    : `Slate ${ICONS.fresh} fresh`;
  statusBar.tooltip = `Context layer: ${counts.fresh} fresh · ${counts.stale} stale · ${counts["needs-verification"]} needs verification`;
  statusBar.backgroundColor = problems
    ? new vscode.ThemeColor("statusBarItem.warningBackground")
    : undefined;
  statusBar.show();
}

function relPath(uri) {
  const root = workspaceRoot();
  if (!root || !uri.fsPath.startsWith(root)) return undefined;
  return uri.fsPath.slice(root.length + 1).split(require("path").sep).join("/");
}

const decorationProvider = {
  provideFileDecoration(uri) {
    const rel = relPath(uri);
    const doc = rel && statusByPath.get(rel);
    if (!doc || doc.status === "fresh") return undefined;
    return new vscode.FileDecoration(
      BADGES[doc.status],
      `Slate: ${doc.status} — ${doc.reason}`,
      new vscode.ThemeColor(
        doc.status === "stale" ? "charts.orange" : "charts.yellow"
      )
    );
  },
};

async function showStatusPicker() {
  if (!statusByPath.size) {
    vscode.window.showInformationMessage(
      "No Slate context layer found — run `slate init` in this repo."
    );
    return;
  }
  const items = [...statusByPath.entries()].map(([path, doc]) => ({
    label: `${ICONS[doc.status]} ${path}`,
    description: doc.status,
    detail: doc.reason,
    path,
  }));
  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: "Slate context docs — select to open",
  });
  if (picked) {
    const uri = vscode.Uri.joinPath(
      vscode.workspace.workspaceFolders[0].uri,
      picked.path
    );
    vscode.window.showTextDocument(uri);
  }
}

async function syncLayer() {
  try {
    await runSlate(["sync"]);
    vscode.window.showInformationMessage(
      "Slate: generated docs synced. Review human-owned docs and `slate mark` them."
    );
  } catch (error) {
    vscode.window.showErrorMessage(`Slate sync failed: ${error.message}`);
  }
  refresh();
}

function activate(context) {
  decorationEmitter = new vscode.EventEmitter();
  decorationProvider.onDidChangeFileDecorations = decorationEmitter.event;

  statusBar = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    50
  );
  statusBar.command = "slate.showStatus";

  context.subscriptions.push(
    statusBar,
    decorationEmitter,
    vscode.window.registerFileDecorationProvider(decorationProvider),
    vscode.commands.registerCommand("slate.refresh", refresh),
    vscode.commands.registerCommand("slate.sync", syncLayer),
    vscode.commands.registerCommand("slate.showStatus", showStatusPicker),
    vscode.workspace.onDidSaveTextDocument(scheduleRefresh),
    vscode.workspace.onDidCreateFiles(scheduleRefresh),
    vscode.workspace.onDidDeleteFiles(scheduleRefresh),
    vscode.workspace.onDidRenameFiles(scheduleRefresh)
  );
  refresh();
}

function deactivate() {
  clearTimeout(refreshTimer);
}

module.exports = { activate, deactivate };
