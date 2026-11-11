import assert from "node:assert/strict";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import routerContext from "next/dist/shared/lib/app-router-context.shared-runtime.js";

const root = fileURLToPath(new URL("..", import.meta.url));
const vite = await createServer({
  root, configFile: false, appType: "custom",
  resolve: { alias: { "@": root } },
  server: { middlewareMode: true },

});
after(async () => { await vite.close(); });
const { SponsorDashboard } = await vite.ssrLoadModule("/components/site/sponsor/sponsor-dashboard.tsx");
const base = {
  sponsor: { name: "Example Sponsor", organisation: "Example Foundation", annual_target: "10000.00" },
  summary: { received: "1234.56", pledged: "0.00", allocated: "500.00", balance: "734.56", students_supported: 1, active_students: 1, current_year_received: "1234.56" },
  currency: "ZAR", as_of: "2026-11-11T12:00:00Z", year: 2026,
  monthly_contributions: Array.from({length:12},(_,i)=>({ month:`2026-${String(i+1).padStart(2,"0")}-01`, amount:i===0?"1234.56":"0.00" })),
  programme_allocations: [],
  learners: [{ id:"fixture-one", learner_label:'Learner <private>', programme:"caps", programme_label:"CAPS", level:"Grade 12", amount:"500.00", status:"active", starts_on:"2026-01-01", ends_on:null, progress_percent:null, progress_updated_at:null }],
  contributions: [{ reference:"TEST-001", amount:"1234.56", status:"received", date:"2026-01-02T12:00:00Z", description:"Synthetic test contribution" }],
  learners_total:1, contributions_total:1, page:1, page_size:20,
};
const render = (props={}) => renderToStaticMarkup(React.createElement(routerContext.AppRouterContext.Provider, { value: { push(){}, replace(){}, refresh(){}, back(){}, forward(){}, prefetch(){} } }, React.createElement(SponsorDashboard, { data:base, ...props })));
const visible = (html) => html.replace(/<style[^>]*>[\s\S]*?<\/style>/g, "");

test("sponsor overview renders real supplied amounts to cents, separate summary cards and authorised links", () => {
  const html=visible(render());
  assert.match(html,/1[\s\u00a0]?234[.,]56/);
  assert.match(html,/Contributions received/);
  assert.match(html,/Students supported/);
  assert.match(html,/Available funding/);
  assert.match(html,/\/sponsor\/statement\?year=2026/);
  assert.match(html,/aria-label="Sponsor navigation"/);
  assert.match(html,/href="#sponsor-content"/);
});

test("learner aliases are escaped and undisclosed progress remains unknown rather than zero", () => {
  const html=visible(render({ initialView:"learners" }));
  assert.match(html,/Learner &lt;private&gt;/);
  assert.doesNotMatch(html,/<private>/);
  assert.match(html,/Not shared/);
  assert.doesNotMatch(html,/<progress/);
  assert.match(html,/Search learners on this page/);
});

test("authorised course progress renders a labelled native progress control", () => {
  const html=visible(render({ initialView:"learners", data:{...base,learners:[{...base.learners[0],progress_percent:62}]} }));
  assert.match(html,/<progress[^>]*max="100"[^>]*value="62"/);
  assert.match(html,/course progress/);
});

test("approval and unavailable states do not invent financial metrics or show another account's data", () => {
  for (const state of ["approval","unavailable"]) {
    const html=visible(render({ data:null, state }));
    assert.match(html,/Contact Amaris/);
    assert.doesNotMatch(html,/Contributions received|1[\s\u00a0]?234[.,]56|Learner &lt;private&gt;|TEST-001/);
    assert.doesNotMatch(html,/Download statement/);
  }
});

test("empty approved accounts show useful empty states without sample learners", () => {
  const html=visible(render({data:{...base,learners:[],contributions:[],monthly_contributions:base.monthly_contributions.map(item=>({...item,amount:"0.00"}))}}));
  assert.match(html,/Your support story starts here/);
  assert.match(html,/Your contributions will appear here/);
  assert.match(html,/A story ready to grow/);
  assert.doesNotMatch(html,/TEST-001|Learner &lt;private&gt;/);
});

test("reports provide a complete-year CSV link and distinguish annual goals from selected report year", () => {
  const html=visible(render({initialView:"reports",data:{...base,year:2025}}));
  assert.match(html,/2025 contribution statement/);
  assert.match(html,/\/sponsor\/statement\?year=2025/);
  assert.match(html,/Your 2026 giving goal/);
  assert.match(html,/spreadsheet-compatible CSV/);
});

test("contribution pagination retains the selected year and view", () => {
  const html=visible(render({initialView:"contributions",data:{...base,page:2,contributions_total:22}}));
  assert.match(html,/Page 2 of 2/);
  assert.match(html,/\/sponsor\?view=contributions&amp;year=2026&amp;page=1/);
});

test("preview sample warning is explicit and does not offer a real statement download", () => {
  const html=visible(render({preview:true}));
  assert.match(html,/fictional sample data/);
  assert.match(html,/href="#preview-statement-note"/);
  assert.doesNotMatch(html,/href="\/sponsor\/statement/);
});
