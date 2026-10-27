// Renders assets/dia.svg to every PNG Dia ships: `node assets/render-icons.js`
// (needs Playwright's Chromium). Transparent icons for the desktop and the
// browser; on white, with room around the ring, for phones and app stores.
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const svg = fs.readFileSync(path.join(__dirname, "dia.svg"), "utf8");
const out = (p) => path.join(__dirname, "..", p);
const jobs = [];
for (const size of [16, 32, 48, 64, 128, 256, 512]) {
  jobs.push({ file: `src/dia/ui/static/icons/dia-${size}.png`, size, padding: 0, background: "transparent" });
}
jobs.push(
  { file: "src/dia/ui/static/icons/icon-192.png", size: 192, padding: 0, background: "transparent" },
  { file: "src/dia/ui/static/icons/icon-512.png", size: 512, padding: 0, background: "transparent" },
  // maskable: launchers crop to a circle or squircle; keep the ring in the safe zone (80 %)
  { file: "src/dia/ui/static/icons/maskable-192.png", size: 192, padding: 0.14, background: "#ffffff" },
  { file: "src/dia/ui/static/icons/maskable-512.png", size: 512, padding: 0.14, background: "#ffffff" },
  { file: "src/dia/ui/static/icons/apple-touch-icon.png", size: 180, padding: 0.1, background: "#ffffff" },
  { file: "src/dia/ui/static/icons/badge-96.png", size: 96, padding: 0, background: "transparent" },
  { file: "mobile/resources/icon.png", size: 1024, padding: 0.12, background: "#ffffff" },
  { file: "mobile/resources/icon-foreground.png", size: 1024, padding: 0.24, background: "transparent" },
  { file: "mobile/resources/icon-background.png", size: 1024, padding: 0, background: "#ffffff", blank: true },
  { file: "mobile/resources/splash.png", size: 2732, padding: 0.4, background: "#ffffff" },
  { file: "mobile/resources/splash-dark.png", size: 2732, padding: 0.4, background: "#0b0b12" },
);

(async () => {
  const browser = await chromium.launch();
  for (const job of jobs) {
    const page = await browser.newPage({ viewport: { width: job.size, height: job.size } });
    const inner = Math.round(job.size * (1 - 2 * job.padding));
    const body = job.blank ? "" : svg.replace(/width="512" height="512"/, `width="${inner}" height="${inner}"`);
    await page.setContent(
      `<html><body style="margin:0;width:${job.size}px;height:${job.size}px;display:flex;` +
        `align-items:center;justify-content:center;background:${job.background}">${body}</body></html>`,
    );
    fs.mkdirSync(path.dirname(out(job.file)), { recursive: true });
    await page.screenshot({ path: out(job.file), omitBackground: job.background === "transparent" });
    await page.close();
  }
  await browser.close();
  console.log(`rendered ${jobs.length} icons`);
})();
