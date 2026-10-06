/** Switch the configured Qwen instance only at an idle, unfrozen client boundary. */
import {readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {active, applies} from './pi-hooks.mjs';

export function registerServer(pi, python) {
  pi.registerCommand('server', {
    description: 'Show or select the Qwen endpoint: /server 192.168.1.34:8000',
    async handler(args, ctx) {
      if (!active(ctx.model)) throw new Error('mypi workflow only');
      await ctx.waitForIdle();
      const address = args.trim();
      if (address && process.env.QWEN_WORKFLOW_STATE) {
        ctx.ui.notify('A worker has a frozen contract. Change /server in the main chat before launching the next task.', 'error'); return;
      }
      const minimum = Number(process.env.QWEN_WORKFLOW_INPUT_BUDGET || 0) + Number(process.env.QWEN_WORKFLOW_OUTPUT_BUDGET || 0) + 8192;
      const result = await pi.exec(python, [join(process.env.QWEN_WORKFLOW_TOOLKIT, 'server_config.py'), ...(address ? [address, '--minimum-context', String(Math.max(32768, minimum))] : [])], {timeout: 20000});
      if (result.code) throw new Error(result.stderr || result.stdout);
      const connection = JSON.parse(result.stdout);
      if (address) {
        process.env.MYPI_SERVER_URL = connection.url;
        process.env.MYPI_MODEL = connection.model;
        const catalog = join(process.env.PI_CODING_AGENT_DIR, 'models.json');
        const config = JSON.parse(readFileSync(catalog, 'utf8'));
        const provider = config.providers['local-qwen-workflow'];
        provider.baseUrl = connection.url + '/v1';
        provider.models[0].id = connection.model;
        provider.models[0].name = connection.model;
        provider.models[0].contextWindow = Math.min(provider.models[0].contextWindow, connection.context_window);
        writeFileSync(catalog, JSON.stringify(config, null, 2));
        await ctx.modelRegistry.refresh();
        if (applies(ctx.model)) {
          const model = ctx.modelRegistry.find('local-qwen-workflow', connection.model);
          if (!model || !await pi.setModel(model)) throw new Error('Endpoint saved; start a new mypi chat to activate its model');
        }
      }
      ctx.ui.notify(`Qwen: ${connection.url}/v1 · ${connection.model} · ${connection.context_window || 'verify with mypi status'} tokens. Projects and tests stay on this machine.`, 'info');
    },
  });
}
