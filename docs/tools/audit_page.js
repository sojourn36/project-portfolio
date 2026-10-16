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
 *   2. 浏览器日志里的 error（Log.entryAdded，含网络/混合内容）
 *   3. 请求失败（Network.loadingFailed）与 HTTP >= 400 的响应
 *   4. 未捕获异常（Runtime.exceptionThrown）
 *   5. DOM 体检：
 *      - <img> 缺 alt / alt 为空
 *      - <img> 已加载但 naturalWidth === 0（图裂）
 *      - 视口宽下的横向溢出（scrollWidth > clientWidth），列出具体越界元素
 *      - 无文本的可点击元素缺 aria-label / title（无障碍）
 *   6. 页面重量：按 MIME 分类统计真实传输字节，列出最重的 5 个资源
 *
 * 被策略拦下的资源**单独一类，默认不算缺陷**
 * ------------------------------------------
 * 站点加了 CSP 之后，「拦下一个跨域脚本」是**策略在按预期工作**，
 * 不是页面缺陷。如果把它混进 log_errors / request_failures，就会出现
 * 「CSP 生效」和「页面真坏了」在结论上完全一样 —— 站点永远判为失败，
 * 报告就没人看了。
 *
 * 所以按来源分流：
 *   · 跨域被拦 → 计入 blocked_requests / csp_blocked，摘要用 [i] 提示，**不影响退出码**
 *   · 同源被拦 → 说明策略把自己的脚本/样式挡了，是真缺陷，计入 hardErrors
 * 判定「同源」靠从日志文本里抠出被拦资源的 URL 与页面 origin 比对；
 * 被拦请求的 URL 取不到（不会有 responseReceived），因此在
 * Network.requestWillBeSent 时就要把它按 requestId 存下来。
 *
 * 用法
 * ----
 *   node audit_page.js --url <URL> [--width 1440] [--height 1000]
 *                      [--wait-for <css>] [--wait-ms 2500] [--timeout 45000]
 *                      [--out <JSON>] [--no-scroll] [--chrome <path>]
 *
 * --no-scroll 不滚全页。默认会滚一遍以触发 loading="lazy"，使重量统计覆盖整页；
 *             加上它则只量首屏 —— 用来验证懒加载到底有没有真的生效。
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
    timeout: 45000, out: null, chrome: null, scroll: true,
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
      case '--no-scroll': o.scroll = false; break;
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
      // CSP / 其他策略拦下的资源。**不计入缺陷**（见下面的判定），
      // 但必须报出来 —— 拦到同源资源就说明策略把自己的东西挡了。
      csp_blocked: [], blocked_requests: [],
      dom: { images_missing_alt: [], images_broken: [], horizontal_overflow: [],
             unlabeled_controls: [], title: '', text_length: 0 },
      weight: { total_bytes: 0, by_type: {}, heaviest: [] },
    };

    // 传输字节：Network.responseReceived 给类型，loadingFinished 给 encodedDataLength。
    // 按 requestId 关联，才能知道「哪个类型占了多重」。
    const reqMeta = new Map();
    // requestId → URL。被策略拦下的请求**不会有 responseReceived**，
    // 只在 loadingFailed 里给一个 requestId，所以 URL 必须提前在
    // requestWillBeSent 时存下来 —— 否则拦下的到底是谁根本说不清。
    const reqUrl = new Map();

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
          const line = `${e.source}: ${e.text}${e.url ? ' @ ' + e.url : ''}`;
          // CSP 拦下的资源单独归一类。理由：这是**策略在按预期工作**，
          // 不是页面缺陷。混进 log_errors 会让「CSP 生效」和「页面真坏了」
          // 在结论上完全无法区分 —— 站点会永远被判为失败，人就不看了。
          // 真正需要报警的是「被拦的是**同源**资源」（= 把自己的脚本挡了）。
          if (e.source === 'security' || /content security policy/i.test(e.text)) {
            report.csp_blocked.push(line);
          } else {
            report.log_errors.push(line);
          }
        }
      } else if (msg.method === 'Network.loadingFailed') {
        const p = msg.params;
        if (p.canceled) return;                       // 主动取消不算缺陷
        // blockedReason 是 Chrome 直接给的「为什么没发出去」：
        // 'csp' / 'inspector' / 'mixed-content' … 有它就说明请求被策略挡了，
        // 而不是网络或服务器出问题。这比解析错误文本可靠得多。
        if (p.blockedReason) {
          report.blocked_requests.push(
            `${p.blockedReason} ${reqUrl.get(p.requestId) || '(url 未知)'} (${p.type})`);
          return;
        }
        report.request_failures.push(`${p.errorText} (${p.type})`);
      } else if (msg.method === 'Network.requestWillBeSent') {
        reqUrl.set(msg.params.requestId, msg.params.request?.url || '');
      } else if (msg.method === 'Network.responseReceived') {
        const r = msg.params.response || {};
        if (r.status >= 400) report.http_errors.push(`${r.status} ${r.url}`);
        reqMeta.set(msg.params.requestId, {
          url: r.url,
          type: r.mimeType || msg.params.type || 'other',
        });
      } else if (msg.method === 'Network.loadingFinished') {
        const meta = reqMeta.get(msg.params.requestId);
        if (!meta) return;
        const bytes = msg.params.encodedDataLength || 0;
        report.weight.total_bytes += bytes;
        // 只按大类聚合，避免长 MIME 串把表格撑爆
        const group = meta.type.split(';')[0].trim() || 'other';
        report.weight.by_type[group] = (report.weight.by_type[group] || 0) + bytes;
        report.weight.heaviest.push({ url: meta.url, type: group, bytes });
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
    // （--no-scroll 时跳过：用于量首屏真实传输量，验证懒加载是否生效）
    if (opt.scroll) {
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
    }
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

    report.weight.heaviest.sort((a, b) => b.bytes - a.bytes);
    report.weight.heaviest = report.weight.heaviest.slice(0, 5);
    report.weight.total_kb = Math.round(report.weight.total_bytes / 1024);

    // 被策略拦下的资源默认**不算缺陷**：那是策略在按预期工作。
    // 唯一例外是「拦下的是同源资源」—— 那说明策略把自己的脚本/样式挡了，
    // 是真问题。按「同源 / 跨域 / 无法判定」三分流，才能让 CSP 生效与页面真坏区分开。
    //
    // ⚠️ 取 URL 的方式必须区分来源，这里踩过一次假阳性：
    //   日志行的格式是 `<source>: <text> @ <页面URL>`，那个 `@ 页面URL` 后缀是
    //   **页面自己**，不是被拦的资源。用「第一个 http(s) 链接」去取，
    //   对「内联脚本被拦」这类**文本里本来就没有资源 URL** 的记录，
    //   就会抓到页面 URL 从而误判成同源。
    //   正确做法：CSP 记录只认**引号里的** URL（Chrome 报被拦资源时都带引号）；
    //   取不到就老实说「无法判定」，而不是猜。
    const QUOTED_URL = /'(https?:\/\/[^']+)'/;
    const BARE_URL = /https?:\/\/[^\s'")]+/;
    const pageOrigin = (() => { try { return new URL(opt.url).origin; } catch { return null; } })();
    const classify = (entry, kind) => {
      const m = kind === 'csp' ? entry.match(QUOTED_URL) : entry.match(BARE_URL);
      const u = m && (kind === 'csp' ? m[1] : m[0]);
      if (!u || !pageOrigin) return 'unknown';
      return u.startsWith(pageOrigin + '/') ? 'same' : 'cross';
    };
    const buckets = { same: [], cross: [], unknown: [] };
    report.csp_blocked.forEach((e) => buckets[classify(e, 'csp')].push(e));
    report.blocked_requests.forEach((e) => buckets[classify(e, 'req')].push(e));
    const allBlocked = report.csp_blocked.concat(report.blocked_requests);

    const hardErrors = report.console_errors.length + report.log_errors.length
      + report.request_failures.length + report.http_errors.length
      + report.exceptions.length + report.dom.images_broken.length
      + buckets.same.length;

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
    // 被策略拦下的**记录**（不是「资源数」）：日志层与被拦请求层各算一条，
    // 同一个脚本可能同时出现在两处。措辞上不合并、也不叫「资源」，免得夸大。
    console.log((buckets.same.length ? '[!] ' : '[i] ')
      + '被策略拦下的记录: ' + allBlocked.length
      + (allBlocked.length === 0 ? ''
        : '  （跨域 ' + buckets.cross.length
          + ' · 同源 ' + buckets.same.length
          + ' · 来源无法判定 ' + buckets.unknown.length + '）'
          + (buckets.same.length
            ? '  ⚠️ 同源被挡 = 策略把自己的东西拦了，是真缺陷'
            : '  跨域被拦属策略预期行为，不计入缺陷')
          + (buckets.unknown.length
            ? '；「无法判定」多为内联脚本被拦（文本里没有资源 URL），需人工确认是不是自己写的'
            : '')));
    allBlocked.slice(0, 3).forEach((t) => console.log('      · ' + t.slice(0, 180)));
    console.log((report.dom.horizontal_overflow_px > 0 ? '[!] ' : '[OK] ')
      + '横向溢出: ' + report.dom.horizontal_overflow_px + 'px');
    if (report.dom.horizontal_overflow.length) {
      console.log('    越界元素: ' + JSON.stringify(report.dom.horizontal_overflow.slice(0, 5)));
    }

    // 页面重量（含懒加载，因为前面已滚过全页）
    const byType = Object.entries(report.weight.by_type)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}=${(v / 1024).toFixed(0)}KB`);
    console.log('[i] 传输总量: ' + report.weight.total_kb + ' KB  (' + byType.join(', ') + ')');
    if (report.weight.heaviest.length) {
      console.log('    最重的资源:');
      for (const h of report.weight.heaviest) {
        console.log('      ' + (h.bytes / 1024).toFixed(0).padStart(6) + ' KB  '
          + h.url.replace(/^https?:\/\/[^/]+/, ''));
      }
    }
    if (opt.out) console.log('[OK] 报告已写入: ' + opt.out);

    process.exitCode = hardErrors > 0 ? 1 : 0;
  } finally {
    try { if (ws) ws.close(); } catch { }
    cleanup();
  }
}

main().catch((e) => { console.error('[X] ' + (e && e.stack || e)); process.exit(2); });
