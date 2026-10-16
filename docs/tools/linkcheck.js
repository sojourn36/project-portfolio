#!/usr/bin/env node
/**
 * linkcheck.js —— 从一个根地址出发，BFS 爬同源 HTML 页面，逐个报状态码。
 *
 * 为什么需要它
 * ------------
 * 单页截图 + 单页体检只能证明「我打开过的那一页没问题」。
 * README 里公开写了「分类筛选、项目翻页都能真点」这类话，
 * 那就必须把每一个可达页面都真的点一遍，而不是抽查两页就宣称全通。
 *
 * 只爬 HTML 文档（同源、跳过 /static/ /media/ 这类二进制资源 ——
 * 那些由页面的子资源加载来覆盖，audit_page.js 已经在做）。
 *
 * 用法
 * ----
 *   node linkcheck.js --root https://example.com/ [--max 60] [--out report.json]
 *
 * 退出码：0 = 所有页面 2xx/3xx；1 = 存在 4xx/5xx 或请求失败。
 */
'use strict';

const fs = require('fs');

function parseArgs(argv) {
  const o = { root: null, max: 60, out: null, timeout: 20000 };
  const a = argv.slice(2);
  const next = () => a.shift();
  while (a.length) {
    const k = a.shift();
    switch (k) {
      case '--root': o.root = next(); break;
      case '--max': o.max = parseInt(next(), 10); break;
      case '--out': o.out = next(); break;
      case '--timeout': o.timeout = parseInt(next(), 10); break;
      case '-h': case '--help':
        console.log(fs.readFileSync(__filename, 'utf8').split('*/')[0]);
        process.exit(0);
      default:
        if (k.startsWith('--')) { console.error('[X] 未知参数: ' + k); process.exit(2); }
    }
  }
  if (!o.root) { console.error('[X] 缺少 --root'); process.exit(2); }
  return o;
}

/** 从 HTML 里抽出所有 href，转成绝对地址，滤掉非 HTML 资源与站外链接。 */
function extractLinks(html, baseUrl) {
  const base = new URL(baseUrl);
  const out = new Set();
  // ⚠️ 字符类里**不要**排除 '#'。写成 [^"'#]+ 会让 "?category=x#projects"
  //    这类「带片段的真链接」整条匹配失败（因为闭合引号前是 #），
  //    于是筛选器链接被静默丢掉 —— 实测本站 4 个分类链接全被漏掉。
  //    正确做法：先连片段一起捕获，再把片段丢掉。
  const re = /href\s*=\s*["']([^"']+)["']/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    const raw = m[1].trim();
    if (!raw || raw.startsWith('#')) continue;                // 纯页内锚点不跟
    if (raw.startsWith('mailto:') || raw.startsWith('tel:')
        || raw.startsWith('javascript:') || raw.startsWith('data:')) continue;
    let u;
    try { u = new URL(raw, base); } catch { continue; }
    if (u.origin !== base.origin) continue;                  // 站外不跟
    if (/\.(png|jpe?g|gif|svg|webp|ico|css|js|mp4|webm|woff2?|ttf|txt|xml|json)$/i
        .test(u.pathname)) continue;                          // 非 HTML 文档
    u.hash = '';
    out.add(u.href);
  }
  return [...out];
}

async function fetchPage(url, timeout) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(url, {
      redirect: 'follow', signal: ctrl.signal,
      headers: { 'user-agent': 'linkcheck.js (+portfolio verification)' },
    });
    const ct = res.headers.get('content-type') || '';
    const body = ct.includes('text/html') ? await res.text() : '';
    return { status: res.status, finalUrl: res.url, contentType: ct, body };
  } catch (e) {
    return { status: 0, error: e.name === 'AbortError' ? 'timeout' : String(e.message || e), body: '' };
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  const opt = parseArgs(process.argv);
  const root = new URL(opt.root);
  const seen = new Map();          // url -> record
  const queue = [root.href];
  const results = [];

  while (queue.length && results.length < opt.max) {
    const url = queue.shift();
    if (seen.has(url)) continue;
    seen.set(url, true);

    const r = await fetchPage(url, opt.timeout);
    const rec = {
      url,
      status: r.status,
      final_url: r.finalUrl !== url ? r.finalUrl : undefined,
      content_type: r.contentType || undefined,
      bytes: r.body ? Buffer.byteLength(r.body, 'utf8') : undefined,
      error: r.error,
      title: (r.body.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [, ''])[1].trim() || undefined,
      links_found: 0,
    };

    if (r.body) {
      const links = extractLinks(r.body, r.finalUrl || url);
      rec.links_found = links.length;
      for (const l of links) if (!seen.has(l)) queue.push(l);
    }
    results.push(rec);
  }

  const bad = results.filter((r) => r.status === 0 || r.status >= 400);
  const line = (r) => `  ${String(r.status).padStart(3)}  ${String(r.bytes ?? '-').padStart(7)}B  ${r.url}`
    + (r.title ? `\n         「${r.title}」` : '')
    + (r.error ? `\n         ERR ${r.error}` : '');

  console.log('=== 爬取 ' + root.href + ' 共 ' + results.length + ' 个 HTML 页面 ===');
  for (const r of results) console.log(line(r));
  console.log(bad.length
    ? `[!] ${bad.length} 个页面有问题`
    : `[OK] 全部 ${results.length} 个页面均为 2xx/3xx`);
  if (queue.length) console.log(`[i] 达到 --max ${opt.max} 上限，仍有 ${queue.length} 个链接未访问`);

  if (opt.out) fs.writeFileSync(opt.out, JSON.stringify(results, null, 2), 'utf8');
  process.exitCode = bad.length ? 1 : 0;
}

main().catch((e) => { console.error('[X] ' + (e && e.stack || e)); process.exit(2); });
