#!/usr/bin/env node
// 헤드리스 Chrome으로 페이지를 찍는 개발용 도구. 의존성 없이 DevTools 프로토콜을 직접 쓴다.
//
// 사용:
//   node site/scripts/screenshot.mjs <url> <out.png> [옵션]
// 옵션:
//   --width <px>     뷰포트 너비 (기본 1440). 600 이하면 모바일로 흉내 낸다.
//   --height <px>    뷰포트 높이 (기본 900)
//   --scale <n>      기기 픽셀 비율 (기본 1)
//   --dark           prefers-color-scheme: dark 로 찍는다
//   --viewport       보이는 영역만 찍는다 (기본은 페이지 전체)
//   --wait <ms>      load 이벤트 뒤 기다리는 시간 (기본 600)
//   --eval <js>      페이지에서 식을 실행해 결과를 JSON으로 출력한다
//   --strict         콘솔 오류나 예외가 있으면 종료 코드 2로 끝낸다
// 환경 변수 CHROME_PATH 로 Chrome 실행 파일을 바꿀 수 있다.

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CHROME =
  process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

function parseArgs(argv) {
  const opts = { width: 1440, height: 900, scale: 1, dark: false, full: true, wait: 600 };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--width') opts.width = Number(argv[++i]);
    else if (a === '--height') opts.height = Number(argv[++i]);
    else if (a === '--scale') opts.scale = Number(argv[++i]);
    else if (a === '--wait') opts.wait = Number(argv[++i]);
    else if (a === '--eval') opts.eval = argv[++i];
    else if (a === '--dark') opts.dark = true;
    else if (a === '--viewport') opts.full = false;
    else if (a === '--strict') opts.strict = true;
    else rest.push(a);
  }
  [opts.url, opts.out] = rest;
  return opts;
}

const opts = parseArgs(process.argv.slice(2));
if (!opts.url || !opts.out) {
  console.error('usage: screenshot.mjs <url> <out.png> [--width n] [--dark] [--viewport] ...');
  process.exit(64);
}

const profile = mkdtempSync(join(tmpdir(), 'shot-'));
const chrome = spawn(
  CHROME,
  [
    '--headless=new',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--hide-scrollbars',
    '--disable-gpu',
    'about:blank',
  ],
  { stdio: ['ignore', 'ignore', 'pipe'] },
);

function cleanup(code) {
  try {
    chrome.kill('SIGKILL');
  } catch {}
  try {
    rmSync(profile, { recursive: true, force: true });
  } catch {}
  process.exit(code);
}

const wsUrl = await new Promise((resolve, reject) => {
  let buf = '';
  const timer = setTimeout(() => reject(new Error('Chrome이 시작되지 않았다')), 20000);
  chrome.stderr.on('data', (d) => {
    buf += d.toString();
    const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) {
      clearTimeout(timer);
      resolve(m[1]);
    }
  });
  chrome.on('exit', () => reject(new Error('Chrome이 일찍 끝났다')));
}).catch((e) => {
  console.error(String(e));
  cleanup(1);
});

const ws = new WebSocket(wsUrl);
await new Promise((resolve) => ws.addEventListener('open', resolve, { once: true }));

let nextId = 1;
const pending = new Map();
const listeners = [];
const problems = [];
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(msg.error.message));
    else resolve(msg.result);
    return;
  }
  if (msg.method === 'Runtime.exceptionThrown') {
    const d = msg.params.exceptionDetails;
    problems.push(`exception: ${d.exception?.description || d.text}`);
  }
  if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error') {
    problems.push(`log: ${msg.params.entry.text} ${msg.params.entry.url || ''}`);
  }
  if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
    problems.push(`console.error: ${msg.params.args.map((a) => a.value ?? a.description).join(' ')}`);
  }
  for (const l of listeners) l(msg);
});

function send(method, params = {}, sessionId) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params, sessionId }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

function waitFor(method, sessionId, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${method} 대기 시간 초과`)), timeoutMs);
    const l = (msg) => {
      if (msg.method === method && msg.sessionId === sessionId) {
        clearTimeout(timer);
        listeners.splice(listeners.indexOf(l), 1);
        resolve(msg.params);
      }
    };
    listeners.push(l);
  });
}

try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  await send('Page.enable', {}, sessionId);
  await send('Runtime.enable', {}, sessionId);
  await send('Log.enable', {}, sessionId);
  await send(
    'Emulation.setDeviceMetricsOverride',
    {
      width: opts.width,
      height: opts.height,
      deviceScaleFactor: opts.scale,
      mobile: opts.width <= 600,
    },
    sessionId,
  );
  await send(
    'Emulation.setEmulatedMedia',
    { features: [{ name: 'prefers-color-scheme', value: opts.dark ? 'dark' : 'light' }] },
    sessionId,
  );
  const loaded = waitFor('Page.loadEventFired', sessionId);
  await send('Page.navigate', { url: opts.url }, sessionId);
  await loaded;
  await new Promise((r) => setTimeout(r, opts.wait));

  if (opts.eval) {
    const res = await send(
      'Runtime.evaluate',
      { expression: opts.eval, returnByValue: true, awaitPromise: true },
      sessionId,
    );
    console.log(JSON.stringify(res.result.value ?? res.result.description ?? null));
  }

  const shot = { format: 'png' };
  if (opts.full) {
    const metrics = await send('Page.getLayoutMetrics', {}, sessionId);
    const size = metrics.cssContentSize || metrics.contentSize;
    shot.captureBeyondViewport = true;
    shot.clip = {
      x: 0,
      y: 0,
      width: opts.width,
      height: Math.min(Math.ceil(size.height), 16000),
      scale: 1,
    };
  }
  const { data } = await send('Page.captureScreenshot', shot, sessionId);
  writeFileSync(opts.out, Buffer.from(data, 'base64'));
  for (const p of problems) console.error(p);
  console.error(`saved ${opts.out}`);
  cleanup(opts.strict && problems.length ? 2 : 0);
} catch (e) {
  console.error(String(e));
  cleanup(1);
}
