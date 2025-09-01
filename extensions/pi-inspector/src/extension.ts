import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {
  const output = vscode.window.createOutputChannel('Pi Inspector');
  const port = vscode.workspace.getConfiguration().get<number>('piInspector.port', 5050);
  const baseUrl = `http://127.0.0.1:${port}`;

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
    const data = await fetchJson('/health');
    output.appendLine(`/health -> ${JSON.stringify(data)}`);
    vscode.window.showInformationMessage('Pi Inspector: Health fetched');
  });

  const cmdCapabilities = vscode.commands.registerCommand('piInspector.capabilities', async () => {
    const data = await fetchJson('/capabilities');
    output.appendLine(`/capabilities -> ${JSON.stringify(data)}`);
    vscode.window.showInformationMessage('Pi Inspector: Capabilities fetched');
  });

  // Try to register LM tools for Copilot Agent Mode (API depends on VS Code/Copilot version)
  tryRegisterLmTools(context, baseUrl, output);

  context.subscriptions.push(cmdHealth, cmdCapabilities, output);
}

export function deactivate() {}

function tryRegisterLmTools(context: vscode.ExtensionContext, baseUrl: string, output: vscode.OutputChannel) {
  const lm: any = (vscode as any).lm;
  if (!lm || typeof lm.registerTool !== 'function') {
    output.appendLine('LM Tools API not available; skipping tool registration.');
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
      output.appendLine(`Registered LM tool: ${name}`);
    } catch (e: any) {
      output.appendLine(`Failed to register LM tool ${name}: ${e?.message || e}`);
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
