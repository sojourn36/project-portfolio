#!/usr/bin/env node
/**
 * audit_page.js —— 用 CDP 给一个页面做「体检」，输出机器可读的缺陷清单。
 *
 * 为什么需要它
 * ------------
 * 截图只能证明「看起来还行」。控制台报错、某个图标 404、某张图裂了、
 * 手机宽度下横向溢出 —— 这些在截图里要么看不见，要么容易被忽略。
 * 本脚本把这些全部量化成一份 JSON，便于逐条修。
 *
 * 检查项
 * ------
 *   1. 控制台 error / warning（Runtime.consoleAPICalled）
 *   2. 浏览器日志里的 error（Log.entryAdded，含网络/CSP/混合内容）
 *   3. 请求失败（Network.loadingFailed）与 HTTP >= 400 的响应
 *   4. 未捕获异常（Runtime.exceptionThrown）
 *   5. DOM 体检：
 *      - <img> 缺 alt / alt 为空
 *      - <img> 已加载但 naturalWidth === 0（图裂）
 *      - 视口宽下的横向溢出（scrollWidth > clientWidth），列出具体越界元素
 *      - 无文本的可点击元素缺 aria-label / title（无障碍）
 *
 * 用法
 * ----
 *   node audit_page.js --url <URL> [--width 1440] [--height 1000]
 *                      [--wait-for <css>] [--wait-ms 2500] [--timeout 45000]
 *                      [--out <JSON>] [--chrome <path>]
 *
 * 退出码：0 = 无 error 级问题；1 = 存在 error 级问题；2 = 用法/启动错误。
 * （warning 级不计入退出码，只在报告里列出。）
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

// ---------------------------------------------------------------- 参数解析

function parseArgs(argv) {
  const o = {
    url: null, width: 1440, height: 1000, waitFor: null, waitMs: 2500,
    timeout: 45000, out: null, chrome: null,
  };
  const a = argv.slice(2);
  const next = () => { if (!a.length) { console.error('[X] 参数缺值'); process.exit(2); } return a.shift(); };
  while (a.length) {
    const k = a.shift();
    switch (k) {
      case '--url': o.url = next(); break;
      case '--width': o.width = parseInt(next(), 10); break;
      case '--height': o.height = parseInt(next(), 10); break;
      case '--wait-for': o.waitFor = next(); break;
      case '--wait-ms': o.waitMs = parseInt(next(), 10); break;
      case '--timeout': o.timeout = parseInt(next(), 10); break;
      case '--out': o.out = next(); break;
      case '--chrome': o.chrome = next(); break;
      case '-h': case '--help': o.help = true; break;
      default:
        if (k.startsWith('--')) { console.error('[X] 未知参数: ' + k); process.exit(2); }
    }
  }
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
  if (opt.help || !opt.url) {
    console.log(fs.readFileSync(__filename, 'utf8').split('*/')[0]);
    process.exit(opt.help ? 0 : 2);
  }

  const chrome = findChrome(opt.chrome);
  const port = 9222 + Math.floor(Math.random() * 700);
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-'));
  const deadline = Date.now() + opt.timeout;

  const child = spawn(chrome, [
    '--headless=new', '--disable-gpu', '--no-proxy-server', '--hide-scrollbars',
    '--no-first-run', '--no-default-browser-check', '--disable-extensions',
    '--mute-audio',
    '--remote-debugging-port=' + port,
    '--user-data-dir=' + userDataDir,
    '--window-size=' + opt.width + ',' + opt.height,
    'about:blank',
  ], { stdio: 'ignore' });

  const cleanup = () => {
    try { child.kill(); } catch { }
    try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch { }
  };

  let ws;
  try {
    await waitForPort(port, deadline);

    // 用 Target.createTarget 而不是 /json/new（后者在部分 Chrome 版本需要 PUT）
    const ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    ws = new WebSocket(ver.webSocketDebuggerUrl);
    await new Promise((res, rej) => {
      ws.addEventListener('open', res, { once: true });
      ws.addEventListener('error', () => rej(new Error('无法连上浏览器 WebSocket')), { once: true });
    });

    const browser = new Cdp(ws);
    await browser.send('Target.setDiscoverTargets', { discover: true });
    const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank' });

    const pageWsUrl = `ws://127.0.0.1:${port}/devtools/page/${targetId}`;
    const pageWs = new WebSocket(pageWsUrl);
    await new Promise((res, rej) => {
      pageWs.addEventListener('open', res, { once: true });
      pageWs.addEventListener('error', () => rej(new Error('无法连上页面 WebSocket')), { once: true });
    });

    const cdp = new Cdp(pageWs);
    const report = {
      url: opt.url, viewport: { width: opt.width, height: opt.height },
      console_errors: [], console_warnings: [], log_errors: [],
      request_failures: [], http_errors: [], exceptions: [],
      dom: { images_missing_alt: [], images_broken: [], horizontal_overflow: [],
             unlabeled_controls: [], title: '', text_length: 0 },
    };

    cdp.on((msg) => {
      if (msg.method === 'Runtime.consoleAPICalled') {
        const p = msg.params;
        const text = (p.args || []).map((x) => x.value ?? x.description ?? x.type).join(' ');
        if (p.type === 'error') report.console_errors.push(text);
        else if (p.type === 'warning') report.console_warnings.push(text);
      } else if (msg.method === 'Runtime.exceptionThrown') {
        const d = msg.params.exceptionDetails || {};
        report.exceptions.push(d.exception?.description || d.text || 'unknown');
      } else if (msg.method === 'Log.entryAdded') {
        const e = msg.params.entry || {};
        if (e.level === 'error') {
          report.log_errors.push(`${e.source}: ${e.text}${e.url ? ' @ ' + e.url : ''}`);
        }
      } else if (msg.method === 'Network.loadingFailed') {
        const p = msg.params;
        if (p.canceled) return;                       // 主动取消不算缺陷
        report.request_failures.push(`${p.errorText} (${p.type})`);
      } else if (msg.method === 'Network.responseReceived') {
        const r = msg.params.response || {};
        if (r.status >= 400) report.http_errors.push(`${r.status} ${r.url}`);
      }
    });

    await cdp.send('Runtime.enable');
    await cdp.send('Log.enable');
    await cdp.send('Network.enable');
    await cdp.send('Page.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: opt.width, height: opt.height, deviceScaleFactor: 1, mobile: false,
    });

    await cdp.send('Page.navigate', { url: opt.url });

    // 等到指定选择器出现（按真实时间轮询），再静默一会儿让懒加载图片落地
    if (opt.waitFor) {
      const sels = opt.waitFor.split(',').map((s) => s.trim()).filter(Boolean);
      while (Date.now() < deadline) {
        const r = await cdp.send('Runtime.evaluate', {
          expression: `(${JSON.stringify(sels)}).some(s => document.querySelector(s))`,
          returnByValue: true,
        });
        if (r.result.value === true) break;
        await sleep(250);
      }
    }
    await sleep(opt.waitMs);

    // 滚一遍全页，触发 loading="lazy" 的图片真正发起请求
    await cdp.send('Runtime.evaluate', {
      expression: `(async () => {
        const step = window.innerHeight;
        for (let y = 0; y < document.body.scrollHeight; y += step) {
          window.scrollTo(0, y);
          await new Promise(r => setTimeout(r, 120));
        }
        window.scrollTo(0, 0);
        await new Promise(r => setTimeout(r, 400));
        return true;
      })()`,
      awaitPromise: true, returnByValue: true,
    });
    await sleep(600);

    const dom = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const out = { images_missing_alt: [], images_broken: [],
                      horizontal_overflow: [], unlabeled_controls: [] };

        for (const img of document.images) {
          const src = img.currentSrc || img.src || '(inline)';
          const alt = img.getAttribute('alt');
          if (alt === null || alt.trim() === '') out.images_missing_alt.push(src);
          if (img.complete && img.naturalWidth === 0) out.images_broken.push(src);
        }

        // 横向溢出：先看根元素，再定位具体越界元素
        const vw = document.documentElement.clientWidth;
        const rootOver = document.documentElement.scrollWidth - vw;
        if (rootOver > 0) {
          const guilty = [];
          for (const el of document.querySelectorAll('body *')) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) continue;
            const right = r.right + window.scrollX;
            if (right > vw + 1) {
              guilty.push({
                tag: el.tagName.toLowerCase(),
                cls: (el.className && typeof el.className === 'string')
                     ? el.className.trim().slice(0, 60) : '',
                right: Math.round(right),
                width: Math.round(r.width),
              });
            }
          }
          // 越界最靠右的前 8 个最有诊断价值
          guilty.sort((a, b) => b.right - a.right);
          out.horizontal_overflow = guilty.slice(0, 8);
          out.horizontal_overflow_px = rootOver;
        } else {
          out.horizontal_overflow_px = 0;
        }

        // 无文本的可点击元素必须有 aria-label / title
        const clickable = 'a[href], button, [role="button"]';
        for (const el of document.querySelectorAll(clickable)) {
          const text = (el.innerText || el.textContent || '').trim();
          const hasImgAlt = el.querySelector('img[alt]:not([alt=""])');
          if (text) continue;
          if (hasImgAlt) continue;
          if (el.getAttribute('aria-label') || el.getAttribute('title')) continue;
          if (el.getAttribute('aria-hidden') === 'true') continue;
          out.unlabeled_controls.push(el.outerHTML.slice(0, 120));
        }

        return {
          ...out,
          title: document.title,
          text_length: (document.body.innerText || '').length,
        };
      })()`,
      returnByValue: true,
    });

    Object.assign(report.dom, dom.result.value);

    const hardErrors = report.console_errors.length + report.log_errors.length
      + report.request_failures.length + report.http_errors.length
      + report.exceptions.length + report.dom.images_broken.length;

    if (opt.out) fs.writeFileSync(opt.out, JSON.stringify(report, null, 2), 'utf8');

    // 人读摘要
    const line = (label, arr) => console.log(
      (arr.length ? '[!] ' : '[OK] ') + label + ': ' + arr.length
      + (arr.length ? ' -> ' + JSON.stringify(arr.slice(0, 3)) : ''));
    console.log('=== ' + opt.url + '  @' + opt.width + 'px ===');
    console.log('[i] title: ' + report.dom.title + ' / 正文 ' + report.dom.text_length + ' 字符');
    line('console error', report.console_errors);
    line('console warning', report.console_warnings);
    line('browser log error', report.log_errors);
    line('request failed', report.request_failures);
    line('http >= 400', report.http_errors);
    line('uncaught exception', report.exceptions);
    line('img 缺 alt', report.dom.images_missing_alt);
    line('img 裂图', report.dom.images_broken);
    line('无标签可点击元素', report.dom.unlabeled_controls);
    console.log((report.dom.horizontal_overflow_px > 0 ? '[!] ' : '[OK] ')
      + '横向溢出: ' + report.dom.horizontal_overflow_px + 'px');
    if (report.dom.horizontal_overflow.length) {
      console.log('    越界元素: ' + JSON.stringify(report.dom.horizontal_overflow.slice(0, 5)));
    }
    if (opt.out) console.log('[OK] 报告已写入: ' + opt.out);

    process.exitCode = hardErrors > 0 ? 1 : 0;
  } finally {
    try { if (ws) ws.close(); } catch { }
    cleanup();
  }
}

main().catch((e) => { console.error('[X] ' + (e && e.stack || e)); process.exit(2); });
