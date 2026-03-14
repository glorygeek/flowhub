import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const projectRoot = resolve(import.meta.dirname, "..");
const distDir = resolve(projectRoot, "dist");
const samplePlanPath = resolve(projectRoot, "sample-run-plan.json");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function render() {
  const samplePlan = JSON.parse(await readFile(samplePlanPath, "utf-8"));
  const prettyPlan = escapeHtml(JSON.stringify(samplePlan, null, 2));
  const html = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>FlowHub Client</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5f0e6;
        --panel: #fffaf3;
        --ink: #1f2a37;
        --muted: #52606d;
        --accent: #c2410c;
        --line: #e8dcc6;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(194, 65, 12, 0.14), transparent 28%),
          linear-gradient(180deg, #fbf7ef 0%, var(--bg) 100%);
        color: var(--ink);
      }
      main {
        max-width: 1080px;
        margin: 0 auto;
        padding: 48px 24px 64px;
      }
      .hero {
        display: grid;
        gap: 18px;
        margin-bottom: 28px;
      }
      .eyebrow {
        letter-spacing: 0.12em;
        text-transform: uppercase;
        font-size: 12px;
        color: var(--accent);
        font-weight: 700;
      }
      h1 {
        margin: 0;
        font-size: clamp(32px, 5vw, 56px);
        line-height: 1.05;
      }
      p {
        margin: 0;
        color: var(--muted);
        line-height: 1.6;
      }
      .grid {
        display: grid;
        gap: 18px;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        margin: 28px 0;
      }
      .card, pre {
        background: rgba(255, 250, 243, 0.88);
        border: 1px solid var(--line);
        border-radius: 20px;
        box-shadow: 0 20px 45px rgba(31, 42, 55, 0.06);
      }
      .card {
        padding: 20px;
      }
      .card h2 {
        margin: 0 0 10px;
        font-size: 18px;
      }
      ul {
        margin: 0;
        padding-left: 18px;
        color: var(--muted);
      }
      pre {
        padding: 20px;
        overflow: auto;
        white-space: pre-wrap;
        word-break: break-word;
        font-size: 13px;
        line-height: 1.5;
      }
      .footer {
        margin-top: 20px;
        font-size: 14px;
        color: var(--muted);
      }
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <div class="eyebrow">FlowHub Client</div>
        <h1>客户端负责拉取 Skill、缓存元数据，并在本地拼装工作流。</h1>
        <p>这是 Tauri 客户端的最小交付壳。当前运行时已经支持根据 FlowHub 返回的 plan bundle，去官方 Skill 中心抓取元数据、写入本地缓存、生成已解析工作流文件，再执行本地工作流 runtime。</p>
      </section>

      <section class="grid">
        <article class="card">
          <h2>当前能力</h2>
          <ul>
            <li>读取包含 <code>workflow_spec</code> 和 <code>client_execution_guidance</code> 的 plan bundle</li>
            <li>去官方 Registry 拉取 Skill 详情，并在限流时回退本地缓存</li>
            <li>优先使用客户端 OpenAI 兼容模型执行节点，失败时回退模拟 runtime</li>
            <li>输出 resolved workflow 文件，供后续真实执行器接管</li>
          </ul>
        </article>
        <article class="card">
          <h2>当前边界</h2>
          <ul>
            <li>节点执行仍是模拟 runtime，尚未真正运行下载到本地的 Skill 代码</li>
            <li>客户端 AI 执行器还未替换当前模拟逻辑</li>
            <li>此壳主要用于 Tauri 打包与交付验收</li>
          </ul>
        </article>
      </section>

      <section>
        <h2>示例 Plan Bundle</h2>
        <pre>${prettyPlan}</pre>
      </section>

      <p class="footer">CLI 验证命令：<code>npm run run-plan</code>。解析结果会落到 <code>.flowhub-cache</code> 或你指定的输出目录。</p>
    </main>
  </body>
</html>`;

  await mkdir(distDir, { recursive: true });
  await writeFile(resolve(distDir, "index.html"), html, "utf-8");
}

async function main() {
  await render();

  if (!process.argv.includes("--watch")) {
    return;
  }

  process.stdout.write("Watching static client shell sources...\n");
  let timer = null;
  const rerender = () => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(async () => {
      try {
        await render();
        process.stdout.write("Rebuilt static client shell.\n");
      } catch (error) {
        process.stderr.write(`${String(error)}\n`);
      }
    }, 150);
  };

  for (const path of [samplePlanPath, resolve(import.meta.dirname, "build-static.mjs")]) {
    await mkdir(dirname(path), { recursive: true });
  }

  const watcher = (await import("node:fs")).watch;
  const watchedPaths = [samplePlanPath, resolve(import.meta.dirname, "build-static.mjs")];
  for (const path of watchedPaths) {
    watcher(path, rerender);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
