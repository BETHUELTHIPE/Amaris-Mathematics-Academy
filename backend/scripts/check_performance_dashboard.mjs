import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { readFile, mkdir } from "node:fs/promises";
import path from "node:path";

const fixture = process.env.PERFORMANCE_UI_FIXTURE;
const evidence = process.env.PERFORMANCE_DASHBOARD_EVIDENCE_DIR;
assert.ok(fixture && evidence, "Provide isolated dependencies and synthetic evidence directory");
const require = createRequire(path.join(fixture, "package.json"));
const { chromium } = require("playwright");
const staticRoot = path.resolve("backend/staticfiles");
const output = path.resolve("artifacts/performance");
await mkdir(output, { recursive:true });
const server = createServer(async (request, response) => {
  const pathname = new URL(request.url, "http://localhost").pathname;
  const target = pathname.startsWith("/static/") ? path.resolve(staticRoot, pathname.slice(8)) : path.join(evidence, pathname === "/email" ? "email.html" : "dashboard.html");
  if(pathname.startsWith("/static/") && !target.startsWith(staticRoot + path.sep)) {response.writeHead(404);response.end();return;}
  const mime = {".css":"text/css",".js":"application/javascript",".png":"image/png",".svg":"image/svg+xml",".woff2":"font/woff2",".woff":"font/woff",".ttf":"font/ttf",".html":"text/html"}[path.extname(target)] || "application/octet-stream";
  try {response.writeHead(200,{"Content-Type":mime});response.end(await readFile(target));}
  catch {response.writeHead(404);response.end();}
});
await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
let browser, page;
try {
  browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
  page=await browser.newPage();
  const base=`http://127.0.0.1:${server.address().port}`;
  await page.route("**/*", route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
  for (const [label,width] of [["mobile",390],["desktop",1280]]) {
    await page.setViewportSize({width,height:1000});
    await page.goto(base);
    for(const heading of ["Most booked tutors","Most requested video topics","Most purchased courses","Video delivery leaders"]) await page.getByRole("heading",{name:heading,exact:true}).waitFor();
    assert.equal(await page.locator(".perf").evaluate(node=>node.getBoundingClientRect().width <= innerWidth),true);
    if (width < 520) assert.equal(await page.locator(".perf-scroll").first().evaluate(node=>node.scrollWidth>node.clientWidth),true,"Tables should scroll inside the card rather than squeeze their text");
    assert.equal(await page.locator(".perf script").count(),0,"Untrusted topic markup must stay escaped text");
    assert.ok(await page.getByRole("link",{name:"Download private letterhead PDF"}).count());
    await page.screenshot({path:path.join(output,`dashboard-${label}.png`),fullPage:true});
    await page.goto(base+"/email");
    await page.getByRole("heading",{name:"Your fortnightly academy performance review"}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth),false);
    await page.screenshot({path:path.join(output,`email-${label}.png`),fullPage:true});
  }
  console.log("PASS actual Django Admin performance HTML and company-letterhead email: mobile/desktop, rankings, PDF link and escaped topic; synthetic records only");
} catch (error) {
  if (page) {
    await page.screenshot({path:path.join(output,"failed.png"),fullPage:true}).catch(()=>{});
    console.log(await page.locator(".perf").evaluate(node=>{
      const values=[];
      for(let element=node;element;element=element.parentElement)values.push({tag:element.tagName,class:element.className,width:element.getBoundingClientRect().width,minWidth:getComputedStyle(element).minWidth});
      return {viewport:innerWidth,ancestors:values};
    }).catch(()=>({error:"No dashboard rendered"})));
  }
  throw error;
} finally {
  if(browser)await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
