#!/usr/bin/env node
/**
 * csp_probe.js —— 在真实浏览器里验证 CSP 到底拦住了什么。
 *
 * 用法::
 *
 *   node csp_probe.js --url <URL> [--expect blocked|open] [--chrome <path>]
 *                     [--out <JSON>] [--timeout <ms>]
 *
 * 它做什么
 * --------
 * 页面加载完成后，往 DOM 里**动态插入**两段脚本，然后回答三个问题：
 *
 *   1. 内联脚本执行了吗？        （CSP 的 script-src 不含 'unsafe-inline'/nonce 就该被拦）
 *   2. 跨域脚本加载了吗？        （这里用真实的那段腾讯 Beacon 地址）
 *   3. 浏览器报了几条 CSP 违规？
 *
 * 同时读回主文档响应里的 Content-Security-Policy 头，作为「这次到底有没有策略」的
 * 凭据 —— 不然「没拦住」和「压根没设策略」在结果上长得一模一样。
 *
 * 为什么必须成对跑（这一步是整件事的关键）
 * ----------------------------------------
 * 只跑一次证明不了任何事。脚本没加载，可能是 CSP 挡的，**也可能是那个域名根本不通**。
 * 所以正确顺序是：
 *
 *   # 1) 对照组：把 CSP 关掉，确认两段脚本确实能跑起来
 *   DJANGO_CSP=0 python manage.py runserver 127.0.0.1:8766
 *   node csp_probe.js --url http://127.0.0.1:8766/ --expect open
 *
 *   # 2) 实验组：开着 CSP，同样的脚本应当被拦
 *   python manage.py runserver 127.0.0.1:8765
 *   node csp_probe.js --url http://127.0.0.1:8765/ --expect blocked
 *
 * 两次结果相反，才算证据。这正是「HTTP 层的证据 ≠ 浏览器层的行为」的落地方式：
 * 只看响应头只能知道策略被发出去了，只有真浏览器能告诉你它有没有生效。
 *
 * 顺带还验一件事：页面自己的 main.js 在 CSP 下还活着吗
 * ----------------------------------------------------
 * 主站脚本是唯一一个 <script>，被 CSP 误伤的话页面看着「正常」但交互全废。
 * 所以脚本会滚一下页面，检查 #siteHeader 有没有被 main.js 加上 is-scrolled ——
 * 有就说明它真的执行了。
 *
 * 退出码: 0 = 结果符合 --expect；1 = 不符合；2 = 参数/环境问题
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

// 真实存在的那段埋点地址。用真地址而不是随便一个外域，是为了让证据更贴题。
const BEACON_URL = 'https://beacon.cdn.qq.com/sdk/4.5.9/beacon_web.min.js';
const INLINE_MARKER = '__csp_probe_inline_ran';

// ---------------------------------------------------------------- 参数

function parseArgs(argv) {
  const a = argv.slice(2);
  const o = { url: null, expect: 'blocked', chrome: null, out: null, timeout: 60000 };
  const next = () => { if (!a.length) { console.error('[X] 参数缺值'); process.exit(2); } return a.shift(); };
  while (a.length) {
    const k = a.shift();
    if (k === '--help' || k === '-h') { console.log(fs.readFileSync(__filename, 'utf8').split('*/')[0]); process.exit(0); }
    else if (k === '--url') o.url = next();
    else if (k === '--expect') o.expect = next();
    else if (k === '--chrome') o.chrome = next();
    else if (k === '--out') o.out = next();
    else if (k === '--timeout') o.timeout = parseInt(next(), 10);
    else { console.error('[X] 未知参数: ' + k); process.exit(2); }
  }
  if (!o.url) { console.error('[X] 缺少 --url'); process.exit(2); }
  if (!['blocked', 'open'].includes(o.expect)) { console.error('[X] --expect 只能是 blocked / open'); process.exit(2); }
  return o;
}

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  process.env.LOCALAPPDATA
    ? path.join(process.env.LOCALAPPDATA, 'Google\\Chrome\\Application\\chrome.exe') : '',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean);

function findChrome(explicit) {
  if (explicit) {
    if (!fs.existsSync(explicit)) { console.error('[X] 指定的 Chrome 不存在: ' + explicit); process.exit(2); }
    return explicit;
  }
  for (const c of CHROME_CANDIDATES) if (fs.existsSync(c)) return c;
  console.error('[X] 未找到 Chrome，请用 --chrome 指定');
  process.exit(2);
}

// ---------------------------------------------------------------- CDP 客户端

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.handlers = [];
    ws.addEventListener('message', (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id != null && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.method + ': ' + JSON.stringify(msg.error)));
        else resolve(msg.result);
      } else if (msg.method) {
        for (const h of this.handlers) h(msg);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error('CDP 超时: ' + method));
        }
      }, 30000);
    });
  }
  on(fn) { this.handlers.push(fn); }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForPort(port, deadline) {
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (r.ok) return await r.json();
    } catch { /* 还没起来 */ }
    await sleep(150);
  }
  throw new Error('Chrome 调试端口未就绪');
}

// ---------------------------------------------------------------- 主流程

async function main() {
  const opt = parseArgs(process.argv);
  const chrome = findChrome(opt.chrome);
  const port = 9222 + Math.floor(Math.random() * 700);
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'csp-probe-'));
  const deadline = Date.now() + opt.timeout;

  const child = spawn(chrome, [
    '--headless=new', '--disable-gpu', '--no-proxy-server', '--hide-scrollbars',
    '--no-first-run', '--no-default-browser-check', '--disable-extensions',
    '--mute-audio',
    '--remote-debugging-port=' + port,
    '--user-data-dir=' + userDataDir,
    '--window-size=1280,900',
    'about:blank',
  ], { stdio: 'ignore' });

  const cleanup = () => {
    try { child.kill(); } catch { }
    try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch { }
  };

  let ws;
  try {
    await waitForPort(port, deadline);
    const ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    ws = new WebSocket(ver.webSocketDebuggerUrl);
    await new Promise((res, rej) => {
      ws.addEventListener('open', res, { once: true });
      ws.addEventListener('error', () => rej(new Error('无法连上浏览器 WebSocket')), { once: true });
    });

    const browser = new Cdp(ws);
    await browser.send('Target.setDiscoverTargets', { discover: true });
    const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank' });

    const pageWs = new WebSocket(`ws://127.0.0.1:${port}/devtools/page/${targetId}`);
    await new Promise((res, rej) => {
      pageWs.addEventListener('open', res, { once: true });
      pageWs.addEventListener('error', () => rej(new Error('无法连上页面 WebSocket')), { once: true });
    });

    const cdp = new Cdp(pageWs);
    const report = {
      url: opt.url, expect: opt.expect,
      csp_header: null,
      csp_violations: [],
      console_errors: [],
      inline_ran: null,
      beacon_loaded: null,
      beacon_error: null,
      mainjs_alive: null,
      verdict: null, reasons: [],
    };

    // 主文档响应的 CSP 头 —— 「这次到底有没有策略」的唯一凭据
    let mainRequestId = null;
    cdp.on((msg) => {
      const p = msg.params || {};
      if (msg.method === 'Network.responseReceived') {
        const r = p.response || {};
        if (p.type === 'Document') {
          mainRequestId = p.requestId;
          const h = r.headers || {};
          for (const k of Object.keys(h)) {
            if (k.toLowerCase() === 'content-security-policy') report.csp_header = h[k];
          }
        }
      } else if (msg.method === 'Log.entryAdded') {
        const e = p.entry || {};
        const text = e.text || '';
        if (/content security policy|refused to (load|execute|apply)/i.test(text)) {
          report.csp_violations.push(text);
        } else if (e.level === 'error') {
          report.console_errors.push(text);
        }
      } else if (msg.method === 'Runtime.consoleAPICalled') {
        if (p.type === 'error') {
          const text = (p.args || []).map((x) => x.value || x.description || '').join(' ');
          if (/content security policy|refused to/i.test(text)) report.csp_violations.push(text);
          else report.console_errors.push(text);
        }
      }
    });

    await cdp.send('Network.enable');
    await cdp.send('Log.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.enable');

    await cdp.send('Page.navigate', { url: opt.url });
    // 等主文档真的到（别用固定 sleep 赌）
    const loadDeadline = Date.now() + 20000;
    while (mainRequestId === null && Date.now() < loadDeadline) await sleep(120);
    await sleep(1200);

    // ---- 注入两段脚本，看谁能活下来 ----
    // 注意：Runtime.evaluate 自身不受 CSP 约束（调试器特权），
    // 但它**创建并插入 DOM 的 <script> 元素**要照常过 CSP 检查 —— 这正是我们要测的。
    const inject = await cdp.send('Runtime.evaluate', {
      expression: `(async () => {
        const out = { inline_ran: false, beacon_loaded: false, beacon_error: null };
        // 1) 内联脚本
        const s1 = document.createElement('script');
        s1.textContent = 'window.${INLINE_MARKER} = true;';
        document.head.appendChild(s1);
        // 2) 跨域脚本（真实 beacon 地址）
        const s2 = document.createElement('script');
        s2.src = ${JSON.stringify(BEACON_URL)};
        s2.onload = () => { out.beacon_loaded = true; };
        s2.onerror = () => { out.beacon_error = 'onerror'; };
        document.head.appendChild(s2);
        await new Promise(r => setTimeout(r, 4000));
        out.inline_ran = window.${INLINE_MARKER} === true;
        return out;
      })()`,
      awaitPromise: true, returnByValue: true,
    });
    const r = inject.result && inject.result.value;
    if (r) {
      report.inline_ran = r.inline_ran;
      report.beacon_loaded = r.beacon_loaded;
      report.beacon_error = r.beacon_error;
    }

    // ---- 页面自己的 main.js 在 CSP 下还活着吗 ----
    const alive = await cdp.send('Runtime.evaluate', {
      expression: `(async () => {
        const h = document.getElementById('siteHeader');
        if (!h) return 'no-header';
        window.scrollTo(0, 200);
        await new Promise(r => setTimeout(r, 250));
        return h.classList.contains('is-scrolled') ? 'alive' : 'dead';
      })()`,
      awaitPromise: true, returnByValue: true,
    });
    report.mainjs_alive = alive.result && alive.result.value;

    await sleep(400);

    // ---- 判定 ----
    const hasPolicy = !!report.csp_header;
    const blockedBoth = report.inline_ran === false && report.beacon_loaded === false;

    if (opt.expect === 'blocked') {
      if (!hasPolicy) report.reasons.push('没有 CSP 头 —— 没有策略就谈不上"被拦住"');
      if (report.inline_ran !== false) report.reasons.push('内联脚本竟然执行了');
      if (report.beacon_loaded !== false) report.reasons.push('跨域脚本竟然加载了');
      if (report.csp_violations.length === 0) report.reasons.push('浏览器没报任何 CSP 违规（结果不可信，可能是没策略或探针没生效）');
      if (report.mainjs_alive !== 'alive') report.reasons.push('页面自己的 main.js 被误伤了（is-scrolled 没加上）');
      report.verdict = (hasPolicy && blockedBoth && report.csp_violations.length > 0
                        && report.mainjs_alive === 'alive') ? 'PASS' : 'FAIL';
    } else {
      // 对照组：CSP 关掉时两段脚本应当**都能跑**，否则说明脚本没加载是因为
      // 网络不通/域名失效，而不是因为 CSP —— 那样实验组的"拦住"就是假的。
      if (hasPolicy) report.reasons.push('期望无策略，但响应带了 CSP 头');
      if (report.inline_ran !== true) report.reasons.push('内联脚本没跑起来 —— 对照无效');
      if (report.beacon_loaded !== true) report.reasons.push('跨域脚本没加载 —— 说明该地址本身不通，实验组的结果将不可信');
      report.verdict = (report.inline_ran === true && report.beacon_loaded === true && !hasPolicy)
        ? 'PASS' : 'FAIL';
    }

    // ---- 输出 ----
    // 标记符号跟着 --expect 走：blocked 模式下「脚本没跑」才是好消息，
    // open 模式下正相反。写死成一种会把 PASS 印成 [!!]，误导读者。
    const mark = (good) => (good ? '[OK]' : '[!!]');
    const wantBlocked = opt.expect === 'blocked';
    console.log('=== CSP 探针: ' + opt.url + ' （期望: ' + opt.expect + '）===');
    console.log('[i] Content-Security-Policy 头: ' + (report.csp_header || '(无)'));
    console.log(mark(report.inline_ran === !wantBlocked) + ' 内联脚本执行: '
      + (report.inline_ran === null ? '未知' : report.inline_ran));
    console.log(mark(report.beacon_loaded === !wantBlocked) + ' 跨域脚本(beacon)加载: '
      + (report.beacon_loaded === null ? '未知' : report.beacon_loaded)
      + (report.beacon_error ? '  (' + report.beacon_error + ')' : ''));
    console.log('[i] CSP 违规条数: ' + report.csp_violations.length);
    report.csp_violations.slice(0, 4).forEach((t) => console.log('      · ' + t.slice(0, 200)));
    console.log(mark(report.mainjs_alive === 'alive') + ' 页面自身 main.js: ' + report.mainjs_alive);
    if (report.console_errors.length) {
      console.log('[i] 其他控制台报错: ' + report.console_errors.length);
      report.console_errors.slice(0, 3).forEach((t) => console.log('      · ' + t.slice(0, 160)));
    }
    console.log('>>> ' + report.verdict + (report.reasons.length ? '  ' + report.reasons.join(' / ') : ''));
    if (opt.out) {
      fs.writeFileSync(opt.out, JSON.stringify(report, null, 2));
      console.log('[OK] 报告已写入: ' + opt.out);
    }

    cleanup();
    process.exit(report.verdict === 'PASS' ? 0 : 1);
  } catch (e) {
    cleanup();
    console.error('[X] ' + (e && e.stack || e));
    process.exit(2);
  }
}

main();
