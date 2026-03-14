const pluginUrl = new URL('../openclaw-plugin/index.js', import.meta.url);
const mod = await import(pluginUrl.href);
const tools = new Map();

const api = {
  config: {
    apiBaseUrl: 'http://127.0.0.1:8000/api/v1',
    apiKey: 'dev-flowhub-key',
    timeoutMs: 20000,
    defaultExecutionMode: 'remote',
    defaultOutputFormat: 'markdown'
  },
  registerTool(def) {
    tools.set(def.name, def);
  }
};

mod.default(api);

const planTool = tools.get('flowhub_plan_command');
const confirmTool = tools.get('flowhub_confirm_request');

if (!planTool || !confirmTool) {
  throw new Error('FlowHub plugin did not register the expected tools');
}

async function main() {
  const guidance = await planTool.execute('guidance-case', {
    goal: '你好'
  });

  const business = await planTool.execute('business-case', {
    goal: '分析 AAPL 和 NVDA 最近 3 个月走势，并给我一份 markdown 简报',
    targets: [{ type: 'text', label: 'tickers', value: 'AAPL,NVDA' }],
    output_format: 'markdown',
    execution_mode: 'remote',
    user_notes: '关注趋势、估值、风险和近期市场新闻，不要包含加密货币。'
  });

  const businessText = business.content[0].text;
  const requestIdMatch = businessText.match(/request_id: (\d+)/);
  const workflowIdMatch = businessText.match(/workflow_id: (\d+)/);
  if (!requestIdMatch) {
    throw new Error(`request_id missing from business plan output\n${businessText}`);
  }

  const requestId = Number(requestIdMatch[1]);
  const workflowId = workflowIdMatch ? Number(workflowIdMatch[1]) : null;

  const confirm = await confirmTool.execute('business-confirm', {
    request_id: requestId
  });

  console.log(
    JSON.stringify(
      {
        guidanceText: guidance.content[0].text,
        requestId,
        workflowId,
        businessText,
        confirmText: confirm.content[0].text
      },
      null,
      2
    )
  );
}

await main();
