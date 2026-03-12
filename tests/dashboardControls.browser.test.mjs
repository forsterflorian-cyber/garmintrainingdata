import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

const REPO_ROOT = path.resolve(fileURLToPath(new URL("..", import.meta.url)));

test("range changes show the loading overlay and mode changes refresh helper copy", async (t) => {
  const browserExecutablePath = await resolveBrowserExecutablePath();
  if (!browserExecutablePath) {
    t.skip("Chrome or Edge not available for browser integration test.");
    return;
  }

  const server = http.createServer(async (request, response) => {
    try {
      const requestPath = new URL(request.url, "http://127.0.0.1").pathname;
      const relativePath = requestPath === "/" ? "/tests/fixtures/dashboard-controls.html" : requestPath;
      const safePath = path.normalize(relativePath).replace(/^([/\\])+/, "");
      const filePath = path.join(REPO_ROOT, safePath);
      if (!filePath.startsWith(REPO_ROOT)) {
        response.writeHead(403);
        response.end("Forbidden");
        return;
      }

      const content = await fs.readFile(filePath);
      response.writeHead(200, { "Content-Type": contentTypeFor(filePath) });
      response.end(content);
    } catch (_error) {
      response.writeHead(404);
      response.end("Not found");
    }
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;

  const browser = await chromium.launch({
    executablePath: browserExecutablePath,
    headless: true,
  });

  try {
    const page = await browser.newPage();
    await page.goto(`${baseUrl}/tests/fixtures/dashboard-controls.html`);

    const overlay = page.locator("#dashboardLoadingOverlay");
    const rangeSelect = page.locator("#rangeSelect");
    const modeSelect = page.locator("#modeSelect");
    const modeHelp = page.locator("#modeHelpText");

    assert.equal(await overlay.isHidden(), true);
    assert.match(await modeHelp.textContent(), /Hybrid: Balanced endurance and strength training/);

    await rangeSelect.selectOption("84");
    await page.waitForFunction(() => !document.getElementById("dashboardLoadingOverlay").hidden);
    assert.equal(await overlay.isVisible(), true);
    await page.waitForFunction(() => document.getElementById("dashboardLoadingOverlay").hidden);
    assert.equal(await page.locator("#loadStatus").textContent(), "Loaded range");

    await modeSelect.selectOption("bike");
    await page.waitForFunction(() => !document.getElementById("dashboardLoadingOverlay").hidden);
    assert.match(await modeHelp.textContent(), /Bike: Cycling-focused training/);
    await page.waitForFunction(() => document.getElementById("dashboardLoadingOverlay").hidden);
    assert.equal(await page.locator("#loadStatus").textContent(), "Loaded mode");
  } finally {
    await browser.close();
    await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
  }
});

async function resolveBrowserExecutablePath() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROME_EXECUTABLE,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch (_error) {
      // Try the next browser candidate.
    }
  }
  return null;
}

function contentTypeFor(filePath) {
  switch (path.extname(filePath).toLowerCase()) {
    case ".html":
      return "text/html; charset=utf-8";
    case ".js":
    case ".mjs":
      return "application/javascript; charset=utf-8";
    case ".css":
      return "text/css; charset=utf-8";
    default:
      return "text/plain; charset=utf-8";
  }
}
