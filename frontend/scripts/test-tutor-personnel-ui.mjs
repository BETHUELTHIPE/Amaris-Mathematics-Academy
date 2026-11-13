import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const root = path.resolve(frontend, "..");
const fixture = process.env.TUTOR_UI_FIXTURE;
assert.ok(fixture, "Provide the isolated UI fixture directory");
const require = createRequire(path.join(fixture, "package.json"));
const { chromium } = require("playwright");
const esbuild = require("esbuild");
const component = path.join(frontend, "components/tutor/personnel-forms.tsx");
const letterhead = path.join(frontend, "components/documents/brand-letterhead.tsx");
await writeFile(path.join(fixture, "image.tsx"), 'export default function Image({unoptimized,...props}){return <img {...props}/>;}');
await writeFile(path.join(fixture, "entry.tsx"), `import {createRoot} from "react-dom/client";import {TutorPersonnelForms} from ${JSON.stringify(component)};createRoot(document.getElementById("root")).render(<main className="mx-auto max-w-4xl px-4 py-8"><p className="mb-5 text-sm">Tutor workspace - synthetic test data</p><TutorPersonnelForms/></main>);`);
await writeFile(path.join(fixture, "input.css"), `@import "tailwindcss";@source "./entry.tsx";@source ${JSON.stringify(component)};@source ${JSON.stringify(letterhead)};body{font-family:Arial,sans-serif;background:#f5f7fb;color:#07152d}.letterhead-accent{height:5px;background:linear-gradient(to right,#07152d 58%,#1f5bbd 58%,#1f5bbd 82%,#ffcc66 82%)}.eyebrow{color:#1f5bbd;font-size:12px;font-weight:bold;text-transform:uppercase}`);
esbuild.buildSync({ entryPoints: [path.join(fixture, "entry.tsx")], outfile: path.join(fixture, "bundle.js"), bundle: true, format: "esm", jsx: "automatic", nodePaths: [path.join(fixture, "node_modules")], alias: { "@/components/documents/brand-letterhead": letterhead, "@/lib/brand": path.join(frontend,"lib/brand.ts"), "next/image": path.join(fixture,"image.tsx") } });
execFileSync(path.join(fixture,"node_modules/.bin/tailwindcss"), ["-i", path.join(fixture,"input.css"), "-o",path.join(fixture,"style.css")]);
const html = '<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Personnel forms fixture</title><link href="/style.css" rel="stylesheet"></head><body><div id="root"></div><script type="module" src="/bundle.js"></script></body></html>';
const server = createServer(async (request,response) => {
  const file = { "/": ["text/html",html], "/bundle.js": ["text/javascript",await readFile(path.join(fixture,"bundle.js"))], "/style.css": ["text/css",await readFile(path.join(fixture,"style.css"))] }[request.url];
  if (!file) { response.writeHead(404);response.end();return; }
  response.writeHead(200,{"Content-Type":file[0]});response.end(file[1]);
});
await new Promise(resolve => server.listen(0,"127.0.0.1",resolve));
let browser, page;
try {
  browser=await chromium.launch({ headless:true, args:["--no-sandbox"] });
  page=await browser.newPage({viewport:{width:390,height:844}});
  const forms=[];
  const submissions=[];
  await page.route("**/brand/amaris-academy-icon-192.png", route=>route.fulfill({path:path.join(frontend,"public/brand/amaris-academy-icon-192.png"),contentType:"image/png"}));
  await page.route("**/api/tutor/forms**", async route=>{
    if(route.request().method()==="GET") return route.fulfill({json:{results:forms,page:1,has_more:false}});
    const data=route.request().postDataJSON();submissions.push(data);
    if(submissions.length===1) return route.abort("failed");
    const saved={id: data.kind==="leave"?"11111111-1111-4111-8111-111111111111":"22222222-2222-4222-8222-222222222222",kind:data.kind,form_type:data.kind==="leave"?"Leave application":"Withdrawal / resignation notice",created_at:"2026-11-13T07:00:00Z",status:"Submitted for review",review_notes:"",reviewed_at:null,details:{...data,calendar_days:"3"}};
    forms.unshift(saved);await route.fulfill({status:201,json:saved});
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.getByText("Your submitted leave and resignation forms will be saved here.").waitFor();
  await page.getByLabel("Leave type",{exact:true}).selectOption("study");
  await page.getByLabel("First day of leave",{exact:true}).fill("2026-12-01");
  await page.getByLabel("Last day of leave",{exact:true}).fill("2026-12-03");
  async function completeShared(){
    await page.getByLabel("Reason",{exact:true}).fill("Preparing for final examinations.");
    await page.getByLabel("Affected lessons and handover plan").fill("No lessons are affected during this period.");
    await page.getByLabel("Contact number",{exact:true}).fill("0712345678");
    await page.getByLabel("Full name as typed signature",{exact:true}).fill("Synthetic Tutor");
    await page.getByRole("checkbox").check();
  }
  await completeShared();
  await page.getByRole("button",{name:"Submit leave application",exact:true}).click();
  await page.getByRole("alert").waitFor();
  await page.getByRole("button",{name:"Submit leave application",exact:true}).click();
  await page.getByRole("status").filter({hasText:"leave application is saved"}).waitFor();
  assert.equal(submissions[0].idempotency_key,submissions[1].idempotency_key);
  await page.getByRole("link",{name:"Download letterhead PDF"}).waitFor();
  assert.equal(await page.getByLabel("Reason",{exact:true}).inputValue(),"");
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await mkdir(path.join(root,"artifacts"),{recursive:true});
  await page.screenshot({path:path.join(root,"artifacts/tutor-personnel-ui-leave-mobile.png"),fullPage:true});
  await page.getByRole("button",{name:"Withdrawal / resignation",exact:true}).click();
  await page.getByLabel("Proposed last teaching day",{exact:true}).fill("2026-12-31");
  await completeShared();
  await page.getByRole("button",{name:"Submit resignation notice",exact:true}).click();
  await page.getByRole("status").filter({hasText:"resignation notice is saved"}).waitFor();
  assert.equal(submissions.length,3);
  assert.notEqual(submissions[2].idempotency_key,submissions[1].idempotency_key);
  assert.equal(await page.getByRole("link",{name:"Download letterhead PDF"}).count(),2);
  assert.equal(await page.getByLabel("Leave type",{exact:true}).count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(root,"artifacts/tutor-personnel-ui-resignation-mobile.png"),fullPage:true});
  await page.setViewportSize({width:1280,height:1000});
  await page.screenshot({path:path.join(root,"artifacts/tutor-personnel-ui-desktop.png"),fullPage:true});
  console.log("PASS actual personnel forms and letterhead: leave/resignation, mobile/desktop, retry key retention, saved history, PDF links and no mobile overflow; synthetic backend only");
} catch(error){
  await mkdir(path.join(root,"artifacts"),{recursive:true});
  if(page)await page.screenshot({path:path.join(root,"artifacts/tutor-personnel-ui-failed.png"),fullPage:true}).catch(()=>{});
  throw error;
} finally{
  if(browser)await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
