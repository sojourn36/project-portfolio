#!/usr/bin/env node
/**
 * measure_thumb_width.js —— 问浏览器要卡片的**真实渲染宽度**，用来定缩略图该多宽。
 *
 * 用法
 * ----
 *     node docs/tools/measure_thumb_width.js [--base http://127.0.0.1:8765]
 *                                            [--chrome <Chrome 路径>]
 *
 * 为什么需要它
 * ------------
 * `make_thumbs` 的默认宽度必须覆盖卡片在 2× 屏上的设备像素数。这个数**推算不出来**：
 *
 *   · `.project-grid` / `.shot-grid` 都是 `auto-fill + minmax`，列宽随视口变化，
 *     还受 `--maxw: 1140px` 封顶 —— 手算容易漏掉断点；
 *   · `.card-cover img` / `.shot-thumb img` 用 `object-fit: cover`，对**宽图是按
 *     高度放大**的（缩放系数是 `max(tw/w, th/h)`，不是按宽度缩）。所以
 *     「源图宽度」要跟 `400 × 宽高比` 比，而不是跟 718 比。
 *
 * 直接问 `getBoundingClientRect` 最省事，也不会骗人。
 *
 * 两个踩过的坑
 * ------------
 *   1. 卡片封面是 `loading="lazy"`，**不先滚一遍**页，`naturalWidth` 就是 0，
 *      会被误读成「图片没加载」。所以下面每页都先滚到底再滚回来。
 *   2. `object-fit: cover` 的语义是「放大到盖满」。第一版按宽度缩，
 *      于是所有宽图都被判成「高度不足」—— 那是模型错了，不是图错了。
 */

const { spawn } = require('child_process');
const http = require('http');
const os = require('os');

const CHROME = process.env.CHROME_PATH
  || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const PAGES = [
  ['首页卡片', '/', '.card-cover img'],
  ['详情页图集', '/project/femnsic-fatigue-optimization/', '.shot-thumb img'],
];
const VIEWPORTS = [
  [1600, 1000, '桌面 1600'],
  [1440, 1000, '桌面 1440'],
  [768, 1000, '平板 768'],
  [390, 844, '手机 390'],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseArgs(argv) {
  const o = { base: 'http://127.0.0.1:8765', chrome: CHROME };
  const a = argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--base') o.base = a[++i];
    else if (a[i] === '--chrome') o.chrome = a[++i];
    else if (a[i] === '-h' || a[i] === '--help') {
      console.log('用法: node measure_thumb_width.js [--base URL] [--chrome PATH]');
      process.exit(0);
    }
  }
  return o;
}

function getJSON(port, path) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port, path, family: 4 }, (res) => {
      let b = '';
      res.on('data', (c) => { b += c; });
      res.on('end', () => { try { resolve(JSON.parse(b)); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}

async function main() {
  const opt = parseArgs(process.argv);
  const port = 9500 + Math.floor(Math.random() * 400);

  const chrome = spawn(opt.chrome, [
    '--headless=new', '--disable-gpu', '--no-proxy-server', '--hide-scrollbars',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${os.tmpdir()}/chrome-measure-${port}`,
    'about:blank',
  ], { stdio: 'ignore' });

  let list;
  for (let i = 0; i < 80; i++) {
    try { list = await getJSON(port, '/json/list'); if (list && list.length) break; }
    catch { /* 还没起来 */ }
    await sleep(250);
  }
  if (!list) throw new Error('Chrome 没起来（检查 --chrome 路径）');
  const target = list.find((t) => t.type === 'page');

  const sock = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    sock.addEventListener('open', res, { once: true });
    sock.addEventListener('error', () => rej(new Error('连不上调试端口')), { once: true });
  });
  let id = 0;
  const pending = new Map();
  sock.addEventListener('message', (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  });
  const send = (method, params = {}) => new Promise((res) => {
    const n = ++id;
    pending.set(n, res);
    sock.send(JSON.stringify({ id: n, method, params }));
  });

  console.log(`基准地址: ${opt.base}\n`);
  await send('Page.enable');
  for (const [vww, vhh, vlabel] of VIEWPORTS) {
    await send('Emulation.setDeviceMetricsOverride', {
      width: vww, height: vhh, deviceScaleFactor: 1, mobile: vww < 500,
    });
    for (const [label, path, sel] of PAGES) {
      await send('Page.navigate', { url: opt.base + path });
      await sleep(900);
      // 先滚一遍触发 loading="lazy"（见文件头的坑 1）
      await send('Runtime.evaluate', {
        expression: `(async () => {
          const step = Math.round(innerHeight * 0.8);
          for (let y = 0; y < document.body.scrollHeight; y += step) {
            scrollTo(0, y);
            await new Promise(r => setTimeout(r, 120));
          }
          scrollTo(0, 0);
          await new Promise(r => setTimeout(r, 600));
        })()`,
        awaitPromise: true,
      });
      await sleep(700);

      const r = await send('Runtime.evaluate', {
        expression: `(() => {
          const el = document.querySelector(${JSON.stringify(sel)});
          if (!el) return null;
          const b = el.getBoundingClientRect();
          return { cssW: Math.round(b.width), cssH: Math.round(b.height),
                   naturalW: el.naturalWidth, naturalH: el.naturalHeight,
                   src: (el.currentSrc || '').split('/media/')[1] || el.currentSrc };
        })()`,
        returnByValue: true,
      });
      const v = r.result && r.result.result && r.result.result.value;
      if (!v) { console.log(`${vlabel} | ${label}: 没找到 ${sel}`); continue; }

      const need2x = v.cssW * 2;
      const ok = v.naturalW >= need2x;
      console.log(
        `${vlabel.padEnd(10)} | ${label.padEnd(6)} | 渲染 ${String(v.cssW).padStart(4)}×${String(v.cssH).padStart(3)}`
        + ` | 2×需 ${String(need2x).padStart(4)}px | 素材 ${String(v.naturalW).padStart(4)}px`
        + ` | ${ok ? '够' : '偏小 ' + (need2x - v.naturalW) + 'px'}`
        + ` | ${v.src}`);
    }
  }

  sock.close();
  chrome.kill();
}

main().catch((e) => { console.error(String(e)); process.exit(1); });
