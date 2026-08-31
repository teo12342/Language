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
const BOLT_KB = require('./bolt-knowledge.js');

const OPENROUTER_KEY_SECRET = 'bolt.openrouterKey';
const OPENROUTER_MODEL_STATE = 'bolt.assistantModel';
const OPENROUTER_API = 'https://openrouter.ai/api/v1';

// ---- Local Bolt knowledge base retrieval ----
// Keyword-overlap scoring over a bundled, static reference (bolt-knowledge.js).
// Not a vector DB, not model fine-tuning - a real, working retrieval step
// that keeps answers grounded in Bolt's actual documented behavior instead
// of the model's possibly-wrong prior knowledge of an obscure language.
function searchKB(query, maxChunks = 4) {
  const q = query.toLowerCase();
  const words = q.split(/[^a-z0-9_]+/i).filter((w) => w.length > 2);
  const scored = BOLT_KB.map((chunk) => {
    let score = 0;
    for (const kw of chunk.keywords) {
      if (q.includes(kw.toLowerCase())) score += 3;
    }
    const lowerText = chunk.text.toLowerCase();
    for (const w of words) {
      if (lowerText.includes(w)) score += 1;
    }
    return { chunk, score };
  })
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score);
  return scored.slice(0, maxChunks).map((s) => s.chunk);
}

async function fetchJson(url, apiKey, body) {
  const res = await fetch(url, {
    method: body ? 'POST' : 'GET',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': 'https://bolt-lang.vercel.app',
      'X-Title': 'Bolt Studio Assistant',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`OpenRouter ${res.status}: ${text.slice(0, 400)}`);
  }
  return JSON.parse(text);
}

function scoreModelForCoding(m) {
  const id = (m.id || '').toLowerCase();
  let s = 0;
  if (id.includes('coder') || id.includes('code')) s += 60;
  if (id.includes('qwen')) s += 15;
  if (id.includes('deepseek')) s += 15;
  if (id.includes('instruct')) s += 5;
  s += Math.min((m.context_length || 0) / 2000, 40);
  return s;
}

async function pickBestFreeCodingModel(apiKey) {
  const res = await fetchJson(`${OPENROUTER_API}/models`, apiKey);
  const models = Array.isArray(res.data) ? res.data : [];
  const free = models.filter((m) => {
    const p = m.pricing || {};
    return parseFloat(p.prompt || '0') === 0 && parseFloat(p.completion || '0') === 0;
  });
  if (free.length === 0) {
    throw new Error('No free models currently available on OpenRouter.');
  }
  free.sort((a, b) => scoreModelForCoding(b) - scoreModelForCoding(a));
  return free[0];
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Very small formatter: turns ``` fenced blocks into <pre><code>, escapes
// everything else. Not a full markdown renderer - deliberately minimal.
function formatAssistantReply(text) {
  const parts = String(text).split(/```(\w*)\n?/);
  let html = '';
  for (let i = 0; i < parts.length; i++) {
    if (i % 3 === 0) {
      html += escapeHtml(parts[i]).replace(/\n/g, '<br>');
    } else if (i % 3 === 2) {
      html += `<pre><code>${escapeHtml(parts[i])}</code></pre>`;
    }
  }
  return html;
}

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

  // ---- Bolt Assistant ----
  /** @type {vscode.WebviewPanel | undefined} */
  let assistantPanel;
  /** @type {{role: string, content: string}[]} */
  let assistantHistory = [];

  async function ensureApiKey(forcePrompt) {
    let key = forcePrompt ? undefined : await context.secrets.get(OPENROUTER_KEY_SECRET);
    if (!key) {
      key = await vscode.window.showInputBox({
        title: 'Bolt Assistant: OpenRouter API key',
        prompt: 'Get a free key at openrouter.ai/keys. Stored encrypted on this machine only, never sent anywhere but OpenRouter.',
        password: true,
        ignoreFocusOut: true,
      });
      if (!key) return undefined;
      await context.secrets.store(OPENROUTER_KEY_SECRET, key);
      // A new key may work with a different free lineup - re-pick the model.
      await context.globalState.update(OPENROUTER_MODEL_STATE, undefined);
    }
    return key;
  }

  async function setOpenRouterKeyCommand() {
    const key = await ensureApiKey(true);
    if (key) vscode.window.showInformationMessage('Bolt Assistant: API key saved.');
  }

  function assistantHtml() {
    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; height: 100%; background: #171410; color: #ece5d6; font-family: -apple-system, "Segoe UI", sans-serif; }
  #wrap { display: flex; flex-direction: column; height: 100%; }
  #header { padding: 8px 12px; background: #211d17; border-bottom: 1px solid #3a3327; font-size: 12px; color: #a89d86; display: flex; justify-content: space-between; align-items: center; }
  #header a { color: #e2895f; cursor: pointer; text-decoration: none; }
  #messages { flex: 1; overflow-y: auto; padding: 12px; }
  .msg { margin-bottom: 14px; max-width: 90%; }
  .msg.user { margin-left: auto; text-align: right; }
  .bubble { display: inline-block; padding: 8px 12px; border-radius: 10px; font-size: 13px; line-height: 1.5; text-align: left; }
  .msg.user .bubble { background: #e2895f; color: #171410; }
  .msg.assistant .bubble { background: #211d17; border: 1px solid #3a3327; }
  .msg.system .bubble { background: transparent; border: 1px dashed #3a3327; color: #8a8066; font-size: 12px; }
  pre { background: #13110d; border: 1px solid #3a3327; border-radius: 6px; padding: 8px 10px; overflow-x: auto; font-family: ui-monospace, monospace; font-size: 12px; margin: 6px 0; }
  code { font-family: ui-monospace, monospace; }
  #inputRow { display: flex; gap: 6px; padding: 10px; border-top: 1px solid #3a3327; background: #171410; }
  #q { flex: 1; background: #211d17; color: #ece5d6; border: 1px solid #3a3327; border-radius: 6px; padding: 8px 10px; font-family: inherit; font-size: 13px; resize: none; }
  #send { background: #e2895f; color: #171410; border: none; border-radius: 6px; padding: 0 16px; font-weight: 700; cursor: pointer; }
  #send:disabled { opacity: 0.5; cursor: default; }
</style>
</head>
<body>
<div id="wrap">
  <div id="header">
    <span id="modelLabel">Bolt Assistant</span>
    <a onclick="vscodeApi.postMessage({type:'changeKey'})">Change API key</a>
  </div>
  <div id="messages"></div>
  <div id="inputRow">
    <textarea id="q" rows="2" placeholder="Ask about Bolt, or paste code to debug..."></textarea>
    <button id="send">Send</button>
  </div>
</div>
<script>
  const vscodeApi = acquireVsCodeApi();
  const messagesEl = document.getElementById('messages');
  const qEl = document.getElementById('q');
  const sendEl = document.getElementById('send');

  function addMessage(role, html) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.innerHTML = '<div class="bubble">' + html + '</div>';
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function send() {
    const text = qEl.value.trim();
    if (!text) return;
    addMessage('user', text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'));
    qEl.value = '';
    sendEl.disabled = true;
    vscodeApi.postMessage({ type: 'ask', text });
  }

  sendEl.addEventListener('click', send);
  qEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  window.addEventListener('message', (event) => {
    const msg = event.data;
    if (msg.type === 'modelName') {
      document.getElementById('modelLabel').textContent = 'Bolt Assistant · ' + msg.model;
    } else if (msg.type === 'thinking') {
      addMessage('system', 'thinking…').id = 'thinking-indicator';
      document.querySelector('.msg.system:last-child').id = 'thinking-indicator';
    } else if (msg.type === 'reply') {
      const t = document.getElementById('thinking-indicator');
      if (t) t.remove();
      addMessage('assistant', msg.html);
      sendEl.disabled = false;
    } else if (msg.type === 'error') {
      const t = document.getElementById('thinking-indicator');
      if (t) t.remove();
      addMessage('system', msg.text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'));
      sendEl.disabled = false;
    }
  });
</script>
</body>
</html>`;
  }

  async function askAssistant(question) {
    const apiKey = await ensureApiKey(false);
    if (!apiKey) return { error: 'No API key set.' };

    let model = context.globalState.get(OPENROUTER_MODEL_STATE);
    if (!model) {
      try {
        const best = await pickBestFreeCodingModel(apiKey);
        model = best.id;
        await context.globalState.update(OPENROUTER_MODEL_STATE, model);
      } catch (e) {
        return { error: 'Could not pick a model: ' + e.message };
      }
    }
    if (assistantPanel) assistantPanel.webview.postMessage({ type: 'modelName', model });

    const kbChunks = searchKB(question);
    const systemPrompt =
      'You are the built-in assistant inside Bolt Studio, an editor for the Bolt programming language (a small Python-flavored scripting language). ' +
      'Answer using the reference material below when it is relevant; if the question is unrelated to Bolt, just answer normally. Keep answers concise and use ```bo code fences for Bolt code.\n\n' +
      kbChunks.map((c) => `### ${c.title}\n${c.text}`).join('\n\n');

    const messages = [{ role: 'system', content: systemPrompt }, ...assistantHistory, { role: 'user', content: question }];

    try {
      const resp = await fetchJson(`${OPENROUTER_API}/chat/completions`, apiKey, { model, messages });
      const reply = resp.choices && resp.choices[0] && resp.choices[0].message && resp.choices[0].message.content;
      if (!reply) return { error: 'Empty response from model.' };
      assistantHistory.push({ role: 'user', content: question });
      assistantHistory.push({ role: 'assistant', content: reply });
      // Keep history bounded so requests stay small.
      if (assistantHistory.length > 20) assistantHistory = assistantHistory.slice(-20);
      return { reply };
    } catch (e) {
      return { error: e.message };
    }
  }

  async function openAssistant() {
    if (assistantPanel) {
      assistantPanel.reveal(vscode.ViewColumn.Beside, true);
      return;
    }
    assistantPanel = vscode.window.createWebviewPanel(
      'boltAssistant',
      'Bolt Assistant',
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: false },
      { enableScripts: true, retainContextWhenHidden: true }
    );
    assistantPanel.webview.html = assistantHtml();
    assistantPanel.onDidDispose(() => { assistantPanel = undefined; });

    const cachedModel = context.globalState.get(OPENROUTER_MODEL_STATE);
    if (cachedModel) assistantPanel.webview.postMessage({ type: 'modelName', model: cachedModel });

    assistantPanel.webview.onDidReceiveMessage(async (msg) => {
      if (msg.type === 'changeKey') {
        await setOpenRouterKeyCommand();
        return;
      }
      if (msg.type === 'ask') {
        assistantPanel.webview.postMessage({ type: 'thinking' });
        const result = await askAssistant(msg.text);
        if (result.error) {
          assistantPanel.webview.postMessage({ type: 'error', text: result.error });
        } else {
          assistantPanel.webview.postMessage({ type: 'reply', html: formatAssistantReply(result.reply) });
        }
      }
    });
  }

  // Persistent, always-visible status bar buttons - no keybinding or menu
  // hunting required, just click them.
  const statusBarButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarButton.text = '$(open-preview) Preview';
  statusBarButton.tooltip = 'Bolt: Run & Preview the current file';
  statusBarButton.command = 'bolt.previewFile';
  statusBarButton.show();

  const assistantButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
  assistantButton.text = '$(sparkle) Assistant';
  assistantButton.tooltip = 'Bolt Assistant (needs your own free OpenRouter API key)';
  assistantButton.command = 'bolt.openAssistant';
  assistantButton.show();

  context.subscriptions.push(
    vscode.commands.registerCommand('bolt.previewFile', previewFile),
    vscode.commands.registerCommand('bolt.openPreviewPanel', openPreviewPanel),
    vscode.commands.registerCommand('bolt.openAssistant', openAssistant),
    vscode.commands.registerCommand('bolt.setOpenRouterKey', setOpenRouterKeyCommand),
    { dispose: killChild },
    output,
    statusBarButton,
    assistantButton
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
