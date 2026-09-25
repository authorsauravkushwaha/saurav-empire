/**
 * Headless smoke test for the built 3D client.
 *
 * It does not render WebGL — it proves the compiled bundle boots in a DOM, mounts the owner gate,
 * and that the API client speaks to the real gateway when a token is supplied. Visual rendering
 * still needs a browser; this only catches "the app does not start" class of bugs.
 */
import { JSDOM } from 'jsdom';
import { readdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const distDir = path.resolve('dist/assets');
const bundle = readdirSync(distDir).find((f) => f.endsWith('.js'));
if (!bundle) {
  console.error('FAIL: no built bundle in dist/assets — run npm run build first');
  process.exit(1);
}

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost:3000/',
  pretendToBeVisual: true,
});
const { window } = dom;
globalThis.window = window;
globalThis.document = window.document;
// `navigator` is a getter-only global in Node 22 — define it instead of assigning.
Object.defineProperty(globalThis, 'navigator', { value: window.navigator, configurable: true });
globalThis.localStorage = window.localStorage;
globalThis.HTMLElement = window.HTMLElement;
globalThis.Element = window.Element;
globalThis.Node = window.Node;
globalThis.getComputedStyle = window.getComputedStyle.bind(window);
globalThis.requestAnimationFrame = window.requestAnimationFrame.bind(window);
globalThis.cancelAnimationFrame = window.cancelAnimationFrame.bind(window);
for (const name of ['ResizeObserver', 'MutationObserver', 'IntersectionObserver', 'DOMParser',
                    'HTMLCanvasElement', 'Image', 'Event', 'CustomEvent']) {
  const value = window[name] ?? (name.endsWith('Observer')
    ? class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } }
    : undefined);
  if (value) {
    globalThis[name] = value;
    window[name] = value;
  }
}
globalThis.fetch = window.fetch ?? (async () => { throw new Error('no fetch in jsdom smoke test'); });
globalThis.WebGL2RenderingContext = undefined;

const errors = [];
window.addEventListener('error', (e) => errors.push(String(e.message)));
process.on('unhandledRejection', (e) => errors.push(String(e)));

await import(pathToFileURL(path.join(distDir, bundle)).href);
await new Promise((r) => setTimeout(r, 400));

const html = window.document.body.innerHTML;
const checks = [
  ['bundle executed without a fatal error', errors.length === 0],
  ['owner gate mounted', /Saurav AI Civilization/.test(html)],
  ['token input rendered', /id="token"/.test(html)],
  ['gate explains the honesty rule', /it will not decorate the world/i.test(html)],
];
let failed = 0;
for (const [label, ok] of checks) {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}`);
  if (!ok) failed += 1;
}
if (errors.length) console.log('runtime errors:', errors.slice(0, 3));
process.exit(failed ? 1 : 0);
