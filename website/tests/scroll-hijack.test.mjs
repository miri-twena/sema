// Regression coverage for the scroll-hijack bug: the product carousel's autoplay timer used
// to call scrollIntoView({ block: 'nearest' }) on a slide, which -- because "nearest" still
// scrolls the page when the target is completely out of the viewport -- dragged the whole
// page back up to the carousel every 5s while the user scrolled toward #bookform. Fixed in
// components/home/carousel/ProductCarousel.tsx (autoplay now scrolls the carousel's own
// track element only, via a new autoAdvanceTrack(), never the document).
//
// A second, smaller-magnitude version of the same failure mode -- the browser's scroll
// anchoring reacting to layout-affecting height changes from timer-driven state, in
// components sitting above the viewport -- was fixed in HowItWorksStepper.tsx (border-width
// toggle -> constant border + inset box-shadow; tabpanel min-height -> fixed height),
// ProactiveFeed.tsx (alert text now reserves a constant 2-line box), and HeroDemoCard.tsx
// (answer block stays mounted via visibility:hidden instead of unmounting while typing).
// See the "RULE:" comments at each timer site under components/home/**.
//
// Run against the static export: `npm run build && node --test tests/scroll-hijack.test.mjs`.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { createStaticServer } from '../scripts/serve-static.mjs';

const PORT = 4319;
const BASE_URL = `http://localhost:${PORT}`;
const IDLE_MS = 20_000; // >= 3 carousel/stepper ticks (5s each), >= 2 feed cycles (7s), >= 1 full hero demo-loop cycle (~10s)
const DRIFT_TOLERANCE_PX = 2;

/** @type {import('http').Server} */
let server;
/** @type {import('playwright').Browser} */
let browser;

before(async () => {
  server = createStaticServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(PORT, resolve);
  });
  browser = await chromium.launch();
});

after(async () => {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
});

/**
 * Nothing that runs on a timer may move focus or scroll (see the rule comments at each timer
 * site under components/home/**). Instrument scrollIntoView/focus before any app code runs
 * so assertions can target the mechanism directly, not just the resulting scroll position.
 */
async function instrumentScrollAndFocus(page) {
  await page.addInitScript(() => {
    window.__sivLog = [];
    window.__focusLog = [];
    const origSiv = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (...args) {
      window.__sivLog.push({ t: Date.now(), tag: this.tagName, arg: args[0] });
      return origSiv.apply(this, args);
    };
    const origFocus = HTMLElement.prototype.focus;
    HTMLElement.prototype.focus = function (...args) {
      window.__focusLog.push({ t: Date.now(), tag: this.tagName });
      return origFocus.apply(this, args);
    };
  });
}

async function readLogs(page) {
  return page.evaluate(() => ({ siv: window.__sivLog, focus: window.__focusLog }));
}

/** Scrolls down toward `#bookform` in small steps, like a user steadily scrolling would. */
async function scrollSteadilyTowardBookform(page) {
  await page.evaluate(async () => {
    const target = document.getElementById('bookform');
    const targetTop = target ? target.getBoundingClientRect().top + window.scrollY - 200 : document.body.scrollHeight;
    const start = window.scrollY;
    const steps = 24;
    for (let i = 1; i <= steps; i++) {
      window.scrollTo({ top: start + ((targetTop - start) * i) / steps, behavior: 'instant' });
      await new Promise((r) => setTimeout(r, 40));
    }
  });
}

for (const { label, path } of [
  { label: 'en', path: '/' },
  { label: 'he', path: '/he/' },
]) {
  test(`idle scroll near #bookform stays put while timers keep animating (${label})`, { timeout: 40_000 }, async () => {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    try {
      await instrumentScrollAndFocus(page);
      await page.goto(`${BASE_URL}${path}`, { waitUntil: 'networkidle' });

      await scrollSteadilyTowardBookform(page);

      const y0 = await page.evaluate(() => window.scrollY);
      assert.ok(y0 > 500, `sanity check: page should have scrolled down substantially, got scrollY=${y0}`);

      await page.waitForTimeout(IDLE_MS);

      const y1 = await page.evaluate(() => window.scrollY);
      assert.ok(
        Math.abs(y1 - y0) <= DRIFT_TOLERANCE_PX,
        `scrollY drifted from ${y0} to ${y1} (>${DRIFT_TOLERANCE_PX}px) while idle`,
      );

      const { siv, focus } = await readLogs(page);
      assert.deepEqual(siv, [], `no scrollIntoView() should fire from a timer while idle, got: ${JSON.stringify(siv)}`);
      assert.deepEqual(focus, [], `no focus() should fire from a timer while idle, got: ${JSON.stringify(focus)}`);
    } finally {
      await page.close();
    }
  });
}

test('idle scroll with the product carousel in view stays put', { timeout: 40_000 }, async () => {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  try {
    await instrumentScrollAndFocus(page);
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    await page.locator('[data-screen-label="Product showcase"]').scrollIntoViewIfNeeded();
    const y0 = await page.evaluate(() => window.scrollY);

    await page.waitForTimeout(IDLE_MS);

    const y1 = await page.evaluate(() => window.scrollY);
    assert.ok(
      Math.abs(y1 - y0) <= DRIFT_TOLERANCE_PX,
      `scrollY drifted from ${y0} to ${y1} (>${DRIFT_TOLERANCE_PX}px) while idle with the carousel in view`,
    );

    // The carousel's own dots/arrows legitimately call scrollIntoView from user clicks, but
    // this test never clicks anything -- any scrollIntoView call recorded here would have to
    // be autoplay-driven, which is exactly the regression this guards against.
    const { focus } = await readLogs(page);
    assert.deepEqual(focus, [], `no focus() should fire from a timer while idle, got: ${JSON.stringify(focus)}`);
  } finally {
    await page.close();
  }
});

test('anchor navigation ("See how it works") still scrolls to #how', { timeout: 20_000 }, async () => {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  try {
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    const before_ = await page.evaluate(() => window.scrollY);

    await page.getByRole('link', { name: /see how it works/i }).click();

    await assertEventually(
      async () => (await page.evaluate(() => window.scrollY)) > before_ + 300,
      'clicking "See how it works" should scroll the page down toward #how',
    );
    await waitForScrollToSettle(page); // smooth-scroll animation may still be in flight

    const howTop = await page.evaluate(() => document.getElementById('how')?.getBoundingClientRect().top ?? -9999);
    assert.ok(howTop >= -2 && howTop < 50, `#how should have scrolled to near the top of the viewport, got top=${howTop}`);
  } finally {
    await page.close();
  }
});

test('anchor navigation from the header nav applies the sticky-header offset', { timeout: 20_000 }, async () => {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  try {
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    await page.evaluate(() => window.scrollTo({ top: 50, behavior: 'instant' }));

    await page.locator('header a[href="#how"]').click();

    await assertEventually(async () => {
      const top = await page.evaluate(() => document.getElementById('how')?.getBoundingClientRect().top ?? -9999);
      return top < 90;
    }, 'clicking the header\'s "how" nav link should scroll #how near the top');
    await waitForScrollToSettle(page); // smooth-scroll animation may still be in flight

    const howTop = await page.evaluate(() => document.getElementById('how')?.getBoundingClientRect().top ?? -9999);
    assert.ok(howTop > 50, `expected the sticky-header offset (~78px), not flush-to-top, got top=${howTop}`);
  } finally {
    await page.close();
  }
});

/** Waits until window.scrollY stops changing between consecutive polls (CSS `scroll-behavior:
 *  smooth` means a scroll triggered by a click is still animating for a while afterwards). */
async function waitForScrollToSettle(page, { interval = 100, stableReadsRequired = 3, timeout = 5000 } = {}) {
  const start = Date.now();
  let last = await page.evaluate(() => window.scrollY);
  let stableReads = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, interval));
    const cur = await page.evaluate(() => window.scrollY);
    if (cur === last) {
      stableReads += 1;
      if (stableReads >= stableReadsRequired) return;
    } else {
      stableReads = 0;
      last = cur;
    }
    if (Date.now() - start > timeout) return; // best effort -- proceed and let the assertion fail with a clear message
  }
}

async function assertEventually(check, message, { timeout = 5000, interval = 100 } = {}) {
  const start = Date.now();
  for (;;) {
    if (await check()) return;
    if (Date.now() - start > timeout) {
      assert.fail(`${message} (timed out after ${timeout}ms)`);
    }
    await new Promise((r) => setTimeout(r, interval));
  }
}
