// Bolt Studio built-in previewer.
//
// Two commands:
//   bolt.previewFile      Run the active file (Bolt, Python, JS, TS, or HTML)
//                         and show it in a preview panel. For scripts that
//                         start a local web server, the panel opens
//                         automatically the moment "localhost:PORT" (or
//                         "127.0.0.1:PORT") shows up in the program's
//                         stdout - that covers Bolt's serve(), Python's
//                         http.server, Node/Express, Flask, etc. equally,
//                         since it only depends on what the program prints,
//                         not what language wrote it.
//   bolt.openPreviewPanel Open an empty preview panel with a URL bar, for
//                         pointing at any already-running app on any port.
//
// No build step - plain CommonJS, matching the rest of this project's
// "no build step" philosophy.

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const cp = require('child_process');

function activate(context) {
  const output = vscode.window.createOutputChannel('Bolt Preview');

  /** @type {vscode.WebviewPanel | undefined} */
  let panel;
  /** @type {import('child_process').ChildProcess | undefined} */
  let child;

  function killChild() {
    if (child && !child.killed) {
      // Kill the whole process tree on Windows (node/python often spawn
      // children of their own for e.g. dev servers with auto-reload).
      if (process.platform === 'win32' && child.pid) {
        cp.spawn('taskkill', ['/pid', String(child.pid), '/T', '/F']);
      } else {
        child.kill();
      }
    }
    child = undefined;
  }

  function previewHtml(url, title) {
    const safeUrl = String(url).replace(/"/g, '&quot;');
    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; height: 100%; background: #171410; }
  .bar {
    display: flex; gap: 6px; align-items: center;
    padding: 6px 8px; background: #211d17; border-bottom: 1px solid #3a3327;
    font-family: -apple-system, "Segoe UI", sans-serif;
  }
  .bar button {
    background: #e2895f; color: #171410; border: none; border-radius: 4px;
    padding: 4px 10px; cursor: pointer; font-weight: 600;
  }
  .bar button:hover { background: #f0a578; }
  .bar input {
    flex: 1; background: #171410; color: #ece5d6; border: 1px solid #3a3327;
    border-radius: 4px; padding: 5px 9px; font-family: ui-monospace, monospace; font-size: 12.5px;
  }
  iframe { width: 100%; height: calc(100% - 41px); border: none; background: #fff; }
</style>
</head>
<body>
  <div class="bar">
    <button title="Reload" onclick="reload()">&#8635;</button>
    <input id="url" value="${safeUrl}" onkeydown="if(event.key==='Enter') go()" />
    <button onclick="go()">Go</button>
  </div>
  <iframe id="frame" src="${safeUrl}"></iframe>
  <script>
    function go() { document.getElementById('frame').src = document.getElementById('url').value; }
    function reload() { const f = document.getElementById('frame'); const u = f.src; f.src = ''; setTimeout(() => f.src = u, 30); }
  </script>
</body>
</html>`;
  }

  function openPreview(url, title) {
    if (!panel) {
      panel = vscode.window.createWebviewPanel(
        'boltPreview',
        title || 'Preview',
        { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
        { enableScripts: true, retainContextWhenHidden: true }
      );
      panel.onDidDispose(() => { panel = undefined; });
    } else {
      panel.title = title || panel.title;
      panel.reveal(vscode.ViewColumn.Beside, true);
    }
    panel.webview.html = previewHtml(url, title);
  }

  const RUNNABLE_LANGUAGES = new Set(['bolt', 'python', 'javascript', 'javascriptreact', 'typescript', 'typescriptreact']);
  const PORT_RE = /(?:localhost|127\.0\.0\.1):(\d{2,5})/i;

  async function previewFile() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('Open a file to preview.');
      return;
    }
    const doc = editor.document;
    if (doc.isDirty) await doc.save();
    const file = doc.fileName;
    const langId = doc.languageId;
    const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
    const cwd = folder ? folder.uri.fsPath : path.dirname(file);

    // HTML needs no process at all - preview the file directly.
    if (langId === 'html') {
      openPreview(vscode.Uri.file(file).toString(), 'Preview: ' + path.basename(file));
      return;
    }

    if (!RUNNABLE_LANGUAGES.has(langId)) {
      vscode.window.showWarningMessage(`Bolt Preview doesn't know how to run "${langId}" files yet. It supports Bolt, Python, JavaScript, TypeScript, and HTML.`);
      return;
    }

    killChild();
    output.clear();
    output.show(true);

    let cmd, args;
    if (langId === 'bolt') {
      const cliPath = path.join(cwd, 'cli.py');
      if (fs.existsSync(cliPath)) {
        cmd = 'python';
        args = [cliPath, file];
      } else {
        vscode.window.showWarningMessage("No cli.py found in this workspace's root - can't run the Bolt script. Open the Bolt language repo as your workspace folder.");
        return;
      }
    } else if (langId === 'python') {
      cmd = 'python';
      args = [file];
    } else if (langId === 'javascript' || langId === 'javascriptreact') {
      cmd = 'node';
      args = [file];
    } else {
      cmd = 'npx';
      args = ['--yes', 'ts-node', file];
    }

    output.appendLine(`$ ${cmd} ${args.join(' ')}\n`);
    child = cp.spawn(cmd, args, { cwd, shell: process.platform === 'win32' });

    let opened = false;
    const tryOpenFromOutput = (text) => {
      if (opened) return;
      const m = text.match(PORT_RE);
      if (m) {
        opened = true;
        const url = `http://localhost:${m[1]}`;
        // Small delay: the server just printed the line but may not have
        // started accepting connections on the very same tick yet.
        setTimeout(() => openPreview(url, 'Preview: ' + path.basename(file)), 400);
      }
    };

    child.stdout.on('data', (data) => {
      const text = data.toString();
      output.append(text);
      tryOpenFromOutput(text);
    });
    child.stderr.on('data', (data) => output.append(data.toString()));
    child.on('close', (code) => output.appendLine(`\n[process exited with code ${code}]`));
    child.on('error', (err) => output.appendLine(`\n[failed to start "${cmd}": ${err.message}]`));
  }

  async function openPreviewPanel() {
    const url = await vscode.window.showInputBox({
      prompt: 'URL of the running app to preview',
      value: 'http://localhost:8080',
      placeHolder: 'http://localhost:8080',
    });
    if (url) openPreview(url, 'Bolt Preview');
  }

  // A persistent, always-visible status bar button - no keybinding or menu
  // hunting required, just click it.
  const statusBarButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarButton.text = '$(open-preview) Preview';
  statusBarButton.tooltip = 'Bolt: Run & Preview the current file';
  statusBarButton.command = 'bolt.previewFile';
  statusBarButton.show();

  context.subscriptions.push(
    vscode.commands.registerCommand('bolt.previewFile', previewFile),
    vscode.commands.registerCommand('bolt.openPreviewPanel', openPreviewPanel),
    { dispose: killChild },
    output,
    statusBarButton
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
