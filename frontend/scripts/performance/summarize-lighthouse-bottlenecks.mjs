import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const folder = process.argv[2] || ".lighthouseci/mobile";
const names = (await readdir(folder)).filter((name) => /^(home|courses|contact)-[123]\.json$/.test(name)).sort();
if (!names.length) {
  console.log("No mobile Lighthouse JSON reports found; diagnosis unavailable.");
  process.exit(0);
}
const audits = [
  "first-contentful-paint", "largest-contentful-paint", "total-blocking-time",
  "speed-index", "cumulative-layout-shift", "bootup-time",
  "mainthread-work-breakdown", "script-treemap-data", "unused-javascript",
  "long-tasks", "third-party-summary", "network-requests"
];
const bytes = (n) => typeof n === "number" ? (n / 1024).toFixed(1) + " KiB" : "-";
const ms = (n) => typeof n === "number" ? Math.round(n) + " ms" : "-";
function topItems(report, id, key, max=8) {
  const items = report.audits?.[id]?.details?.items;
  if (!Array.isArray(items)) return [];
  return [...items]
    .sort((a,b) => (b[key] || 0)-(a[key] || 0))
    .slice(0,max)
    .map(x => ({source: String(x.url || x.entity?.name || x.group || x.node?.snippet || x.source || "").slice(0,145),
      value:x[key], bytes:x.totalBytes, wasted:x.wastedBytes,
      duration:x.duration, mainThreadTime:x.mainThreadTime}));
}
console.log("## Mobile Lighthouse JS execution / blocking diagnosis");
for(const name of names) {
  const report = JSON.parse(await readFile(path.join(folder,name),"utf8"));
  const a=report.audits || {};
  const v=(id)=>a[id]?.numericValue;
  console.log(`\n### ${name}: score ${Math.round((report.categories?.performance?.score||0)*100)} / 100`);
  console.log(`FCP=${ms(v("first-contentful-paint"))} LCP=${ms(v("largest-contentful-paint"))} TBT=${ms(v("total-blocking-time"))} SI=${ms(v("speed-index"))} CLS=${v("cumulative-layout-shift")?.toFixed(4) ?? "-"}`);
  console.log(`Script execution (bootup-time)=${ms(v("bootup-time"))} Main-thread work=${ms(v("mainthread-work-breakdown"))}`);
  for (const [id, key] of [["bootup-time","total"],["mainthread-work-breakdown","duration"],
                            ["long-tasks","duration"],["unused-javascript","wastedBytes"]]) {
    const items=topItems(report,id,key,7);
    if(items.length) console.log(id,JSON.stringify(items));
  }
  const req=a["network-requests"]?.details?.items;
  if(Array.isArray(req)){
    const js=req.filter(x=>/javascript|\.js(\?|$)/i.test(x.mimeType||x.url||""))
      .sort((a,b)=>(b.transferSize||0)-(a.transferSize||0)).slice(0,7);
    console.log("js-network",JSON.stringify(js.map(x=>({url:String(x.url).slice(0,130),transfer:bytes(x.transferSize),resource:bytes(x.resourceSize)}))));
  }
}
