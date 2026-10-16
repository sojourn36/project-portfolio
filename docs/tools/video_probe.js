#!/usr/bin/env node
/**
 * video_probe.js —— 在真实浏览器里验证 <video> 能不能拖动进度条。
 *
 * 为什么需要它
 * ------------
 * 「HTTP 层支持 Range」和「浏览器里进度条能拖」是两件事。
 * curl 拿到 206 + Content-Range 只说明服务器愿意按区间发；
 * 真正要验证的是浏览器**是否真的发起了区间请求**、以及 seek 后
 * currentTime 有没有落到目标位置。
 *
 * 本脚本用 CDP 打开页面，然后：
 *   1. 等 <video> 的 loadedmetadata，读 duration / seekable / readyState
 *   2. 统计该视频收到的 HTTP 状态码（**206 的条数就是 Range 是否被使用的证据**）
 *   3. 执行真实 seek（currentTime = 75%），等 seeked 事件
 *   4. 复核 seek 后的 currentTime 是否真的落到了目标附近
 *
 * 用法
 * ----
 *   node video_probe.js --url <页面URL> [--sel "video"] [--chrome <path>]
 *                       [--wait-ms 3000] [--timeout 60000] [--out report.json]
 *
 * 退出码：0 = 能 seek；1 = 不能 seek 或没有视频；2 = 用法/启动错误。
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function parseArgs(argv) {
  const o = {
    url: null, sel: 'video', chrome: null, waitMs: 3000,
    timeout: 60000, out: null,
  };
  const a = argv.slice(2);
  const next = () => { if (!a.length) { console.error('[X] 参数缺值'); process.exit(2); } return a.shift(); };
  while (a.length) {
    const k = a.shift();
    switch (k) {
      case '--url': o.url = next(); break;
      case '--sel': o.sel = next(); break;
      case '--chrome': o.chrome = next(); break;
      case '--wait-ms': o.waitMs = parseInt(next(), 10); break;
      case '--timeout': o.timeout = parseInt(next(), 10); break;
      case '--out': o.out = next(); break;
      case '-h': case '--help':
        console.log(fs.readFileSync(__filename, 'utf8').split('*/')[0]);
        process.exit(0);
      default:
        if (k.startsWith('--')) { console.error('[X] 未知参数: ' + k); process.exit(2); }
    }
  }
  if (!o.url) { console.error('[X] 缺少 --url'); process.exit(2); }
  return o;
}

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  process.env.LOCALAPPDATA
    ? path.join(process.env.LOCALAPPDATA, 'Google\\Chrome\\Application\\chrome.exe') : '',
  '/usr/bin/google-chrome', '/usr/bin/chromium',
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

class Cdp {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.handlers = [];
    ws.addEventListener('message', (ev) => {
      let msg; try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id != null && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
        else resolve(msg.result);
      } else if (msg.method) { for (const h of this.handlers) h(msg); }
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.has(id)) { this.pending.delete(id); reject(new Error('CDP 超时: ' + method)); }
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

async function main() {
  const opt = parseArgs(process.argv);
  const chrome = findChrome(opt.chrome);
  const port = 9900 + Math.floor(Math.random() * 90);
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'vprobe-'));
  const deadline = Date.now() + opt.timeout;

  const child = spawn(chrome, [
    '--headless=new', '--disable-gpu', '--no-proxy-server', '--hide-scrollbars',
    '--no-first-run', '--no-default-browser-check', '--disable-extensions',
    '--autoplay-policy=no-user-gesture-required', '--mute-audio',
    '--remote-debugging-port=' + port,
    '--user-data-dir=' + userDataDir,
    '--window-size=1280,900', 'about:blank',
  ], { stdio: 'ignore' });

  const cleanup = () => {
    try { child.kill(); } catch { }
    try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch { }
  };

  let browserWs;
  try {
    await waitForPort(port, deadline);
    const ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    browserWs = new WebSocket(ver.webSocketDebuggerUrl);
    await new Promise((res, rej) => {
      browserWs.addEventListener('open', res, { once: true });
      browserWs.addEventListener('error', () => rej(new Error('连不上浏览器')), { once: true });
    });

    const browser = new Cdp(browserWs);
    await browser.send('Target.setDiscoverTargets', { discover: true });
    const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank' });

    const pageWs = new WebSocket(`ws://127.0.0.1:${port}/devtools/page/${targetId}`);
    await new Promise((res, rej) => {
      pageWs.addEventListener('open', res, { once: true });
      pageWs.addEventListener('error', () => rej(new Error('连不上页面')), { once: true });
    });

    const cdp = new Cdp(pageWs);

    // 记录该页面所有媒体请求的状态码 —— 206 的条数就是 Range 被使用的证据
    const mediaResponses = [];
    cdp.on((msg) => {
      if (msg.method !== 'Network.responseReceived') return;
      const r = msg.params.response || {};
      if (/\.(mp4|webm|m4v)(\?|$)/i.test(r.url)) {
        mediaResponses.push({ status: r.status, url: r.url, mimeType: r.mimeType });
      }
    });

    await cdp.send('Runtime.enable');
    await cdp.send('Network.enable');
    await cdp.send('Page.enable');
    await cdp.send('Page.navigate', { url: opt.url });
    await sleep(opt.waitMs);

    // 1) 等元数据就绪并读取基本信息
    const meta = await cdp.send('Runtime.evaluate', {
      expression: `(async () => {
        const v = document.querySelector(${JSON.stringify(opt.sel)});
        if (!v) return { ok: false, reason: '页面上找不到 ' + ${JSON.stringify(opt.sel)} };
        if (v.readyState < 1) {
          await new Promise((res) => {
            const done = () => res();
            v.addEventListener('loadedmetadata', done, { once: true });
            v.addEventListener('error', done, { once: true });
            setTimeout(done, 15000);
          });
        }
        let seekable = [];
        for (let i = 0; i < v.seekable.length; i++) {
          seekable.push([Number(v.seekable.start(i).toFixed(3)),
                         Number(v.seekable.end(i).toFixed(3))]);
        }
        return {
          ok: true,
          duration: Number.isFinite(v.duration) ? Number(v.duration.toFixed(3)) : null,
          readyState: v.readyState,
          networkState: v.networkState,
          seekable,
          currentSrc: v.currentSrc || (v.querySelector('source') || {}).src || '',
          error: v.error ? (v.error.code + ':' + v.error.message) : null,
        };
      })()`,
      awaitPromise: true, returnByValue: true,
    });

    const info = meta.result.value;
    if (!info || !info.ok) {
      console.error('[X] ' + ((info && info.reason) || '读取视频失败'));
      process.exitCode = 1;
      return;
    }

    // 2) 真实 seek 到 75%，等 seeked 事件，复核落点
    const seek = await cdp.send('Runtime.evaluate', {
      expression: `(async () => {
        const v = document.querySelector(${JSON.stringify(opt.sel)});
        if (!Number.isFinite(v.duration)) return { ok: false, reason: 'duration 不可用，无法 seek' };
        const target = Number((v.duration * 0.75).toFixed(3));
        const before = v.currentTime;
        const p = new Promise((res) => {
          let settled = false;
          const done = () => { if (!settled) { settled = true; res(); } };
          v.addEventListener('seeked', done, { once: true });
          setTimeout(done, 15000);
        });
        v.currentTime = target;
        await p;
        return {
          ok: true, target,
          before: Number(before.toFixed(3)),
          after: Number(v.currentTime.toFixed(3)),
          drift: Number(Math.abs(v.currentTime - target).toFixed(3)),
        };
      })()`,
      awaitPromise: true, returnByValue: true,
    });

    const seekRes = seek.result.value;
    await sleep(1200);   // 留时间让 seek 引发的区间请求被记录

    const statuses = mediaResponses.map((m) => m.status);
    const count206 = statuses.filter((s) => s === 206).length;
    const report = {
      url: opt.url,
      video: info,
      seek: seekRes,
      media_requests: mediaResponses,
      http_206_count: count206,
    };

    const canSeek = seekRes && seekRes.ok && seekRes.drift <= 0.5;

    console.log('=== ' + opt.url + ' ===');
    console.log('[i] 视频源: ' + info.currentSrc);
    console.log('[i] duration=' + info.duration + 's  readyState=' + info.readyState
      + '  networkState=' + info.networkState);
    console.log('[i] seekable 区间: ' + JSON.stringify(info.seekable));
    if (info.error) console.log('[!] video.error: ' + info.error);
    console.log('[i] 媒体请求状态码: ' + JSON.stringify(statuses)
      + '   其中 206 = ' + count206 + ' 条');
    if (seekRes && seekRes.ok) {
      console.log('[i] seek: ' + seekRes.before + 's -> 目标 ' + seekRes.target
        + 's -> 实际 ' + seekRes.after + 's（偏差 ' + seekRes.drift + 's）');
    } else {
      console.log('[!] seek 失败: ' + ((seekRes && seekRes.reason) || '未知'));
    }

    const seekableFull = info.seekable.length > 0
      && info.seekable[0][1] >= (info.duration || 0) - 0.5;
    console.log((seekableFull ? '[OK] ' : '[!] ')
      + 'seekable 覆盖到片尾: ' + seekableFull);
    console.log((count206 > 0 ? '[OK] ' : '[!] ')
      + '浏览器确实发出了 206 区间请求: ' + (count206 > 0));
    console.log((canSeek ? '[OK] ' : '[!] ') + '进度条可拖动（seek 落点准确）');

    if (opt.out) fs.writeFileSync(opt.out, JSON.stringify(report, null, 2), 'utf8');
    process.exitCode = (canSeek && seekableFull && count206 > 0) ? 0 : 1;
  } finally {
    try { if (browserWs) browserWs.close(); } catch { }
    cleanup();
  }
}

main().catch((e) => { console.error('[X] ' + (e && e.stack || e)); process.exit(2); });
