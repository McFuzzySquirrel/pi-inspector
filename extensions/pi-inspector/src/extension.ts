import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {
  const output = vscode.window.createOutputChannel('Pi Inspector');
  const port = vscode.workspace.getConfiguration().get<number>('piInspector.port', 5050);
  const baseUrl = `http://127.0.0.1:${port}`;
  output.appendLine(`[Pi Inspector] Activated. Base URL: ${baseUrl}`);
  // Reveal the output on activation so users see logs immediately
  try { output.show(true); } catch {}

  // Ensure fetch exists in this VS Code host; some builds may require a polyfill
  try {
    // @ts-ignore
    if (typeof fetch === 'undefined') {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      require('undici/polyfill');
      output.appendLine('[Pi Inspector] Applied fetch polyfill (undici).');
    }
  } catch (e: any) {
    output.appendLine(`[Pi Inspector] Fetch polyfill not applied: ${e?.message || e}`);
  }

  async function fetchJson(path: string) {
    const url = `${baseUrl}${path}`;
    try {
      if (typeof (globalThis as any).fetch !== 'function') {
        throw new Error('global fetch is not available');
      }
      const resp = await (globalThis as any).fetch(url);
      return await resp.json();
    } catch (e: any) {
      output.appendLine(`Error fetching ${path}: ${e?.message || e}`);
      return null;
    }
  }

  const cmdHealth = vscode.commands.registerCommand('piInspector.health', async () => {
  output.appendLine('[Pi Inspector] Command: Health');
    const data = await fetchJson('/health');
    output.appendLine(`/health -> ${JSON.stringify(data)}`);
    vscode.window.showInformationMessage('Pi Inspector: Health fetched');
  });

  const cmdCapabilities = vscode.commands.registerCommand('piInspector.capabilities', async () => {
  output.appendLine('[Pi Inspector] Command: Capabilities');
    const data = await fetchJson('/capabilities');
    output.appendLine(`/capabilities -> ${JSON.stringify(data)}`);
    vscode.window.showInformationMessage('Pi Inspector: Capabilities fetched');
  });

  // Try to register LM tools for Copilot Agent Mode (API depends on VS Code/Copilot version)
  tryRegisterLmTools(context, baseUrl, output);

  // Manual command to re-register tools on demand
  const cmdRegisterTools = vscode.commands.registerCommand('piInspector.registerTools', async () => {
    tryRegisterLmTools(context, baseUrl, output);
    vscode.window.showInformationMessage('Pi Inspector: attempted LM tools registration (see Output).');
  });

  const cmdShowOutput = vscode.commands.registerCommand('piInspector.showOutput', async () => {
    try { output.show(true); } catch {}
  });

  context.subscriptions.push(cmdHealth, cmdCapabilities, cmdRegisterTools, cmdShowOutput, output);

  // Register a Chat Participant so users can @Pi Inspector in Copilot Chat
  try {
    const chatApi: any = (vscode as any).chat;
    if (chatApi && typeof chatApi.registerChatParticipant === 'function') {
      const participant = chatApi.registerChatParticipant('pi-inspector', {
        name: 'Pi Inspector',
        async handleRequest(request: any, _context: any, stream: any, _token: vscode.CancellationToken) {
          const prompt: string = String(request?.prompt || '')
            .trim();
          output.appendLine(`[Pi Inspector] Chat request: ${prompt}`);

          async function get(path: string) {
            if (typeof (globalThis as any).fetch !== 'function') {
              throw new Error('global fetch is not available in this VS Code build');
            }
            const resp = await (globalThis as any).fetch(`${baseUrl}${path}`);
            return await resp.json();
          }

          try {
            const sendJson = async (title: string, path: string) => {
              const data = await get(path);
              await stream.markdown(`### ${title}`);
              await stream.markdown('```json');
              await stream.markdown(JSON.stringify(data, null, 2));
              await stream.markdown('```');
            };

            if (/capabilities?/i.test(prompt)) {
              await sendJson('Capabilities', '/capabilities');
            } else if (/health|status/i.test(prompt)) {
              await sendJson('Health', '/health');
            } else if (/cpu[-_ ]?temp|temperature/i.test(prompt)) {
              await sendJson('CPU Temperature', '/cpu-temp');
            } else if (/system[-_ ]?info|specs?|hardware|summary/i.test(prompt)) {
              await sendJson('System Info', '/system-info');
            } else {
              await stream.markdown('Try: capabilities, health, cpu temp, or system info.');
            }
            // Always return a final response to avoid Chat UI retries
            return { kind: 'markdown', value: 'Done.' };
          } catch (e: any) {
            const msg = e?.message || String(e);
            output.appendLine(`[Pi Inspector] Chat error: ${msg}`);
            await stream.markdown(`Error: ${msg}`);
            return { kind: 'markdown', value: `Error: ${msg}` };
          }
        },
      });
      context.subscriptions.push(participant);
      output.appendLine('[Pi Inspector] Chat participant registered (@Pi Inspector).');
    } else {
      output.appendLine('[Pi Inspector] Chat API not available; @Pi Inspector will not appear.');
    }
  } catch (err: any) {
    output.appendLine(`[Pi Inspector] Failed to register chat participant: ${err?.message || err}`);
  }
}

export function deactivate() {}

function tryRegisterLmTools(context: vscode.ExtensionContext, baseUrl: string, output: vscode.OutputChannel) {
  const lm: any = (vscode as any).lm;
  if (!lm || typeof lm.registerTool !== 'function') {
  output.appendLine('[Pi Inspector] LM Tools API not available; skipping tool registration. Ensure VS Code + Copilot Chat support tools.');
    return;
  }

  const register = (name: string, description: string, path: string, inputSchema: any = { type: 'object', properties: {}, additionalProperties: false }) => {
    try {
      const disposable = lm.registerTool({ name, description, inputSchema, tags: ['pi', 'raspberry-pi', 'local'] }, async (_input: any, _ctx: any, _tok: any) => {
  const data = await fetchJsonPath(baseUrl, path);
        const text = JSON.stringify(data ?? {});
        // Prefer typed ToolResultPart if present
        const TextPart = (vscode as any).LanguageModelToolResultTextPart;
        if (typeof TextPart === 'function') {
          return { content: [new TextPart(text)] };
        }
        return { content: [{ type: 'text', text }] };
      });
      context.subscriptions.push(disposable);
  output.appendLine(`[Pi Inspector] Registered LM tool: ${name}`);
    } catch (e: any) {
  output.appendLine(`[Pi Inspector] Failed to register LM tool ${name}: ${e?.message || e}`);
    }
  };

  register('pi.health', 'Get local Raspberry Pi inspector health', '/health');
  register('pi.cpuTemp', 'Get CPU temperature in Celsius', '/cpu-temp');
  register('pi.systemInfo', 'Get full system information summary', '/system-info');
  register('pi.capabilities', 'Get local capabilities/tools detected on the Pi', '/capabilities');
}

async function fetchJsonPath(baseUrl: string, path: string) {
  const url = `${baseUrl}${path}`;
  if (typeof (globalThis as any).fetch !== 'function') {
    throw new Error('global fetch is not available in this VS Code build');
  }
  const resp = await (globalThis as any).fetch(url);
  return await resp.json();
}
