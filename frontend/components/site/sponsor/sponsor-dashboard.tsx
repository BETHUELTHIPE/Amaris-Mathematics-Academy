"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpen, Check, ChevronLeft, ChevronRight,
  CircleHelp, FileText, GraduationCap, HeartHandshake, LayoutDashboard, LogOut, Mail,
  Search, ShieldCheck, Sparkles, Target, UsersRound, Wallet, CalendarDays, CircleAlert,
} from "lucide-react";
import { academyBrand } from "@/lib/brand";
import type { SponsorDashboardData, SponsorLearner } from "@/lib/sponsor-api";
import css from "./sponsor-dashboard.css?inline";

type View = "overview" | "learners" | "contributions" | "reports";
const views = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "learners", label: "Sponsored learners", icon: GraduationCap },
  { key: "contributions", label: "Contributions", icon: Wallet },
  { key: "reports", label: "Reports & statements", icon: FileText },
] as const;
const money = (value: string | number) => new Intl.NumberFormat("en-ZA", {
  style: "currency", currency: "ZAR", maximumFractionDigits: 0,
}).format(Number(value));
const exactMoney = (value: string) => new Intl.NumberFormat("en-ZA", {
  style: "currency", currency: "ZAR", minimumFractionDigits: 2,
}).format(Number(value));
const day = (value: string) => new Intl.DateTimeFormat("en-ZA", {
  day: "numeric", month: "short", year: "numeric", timeZone: "Africa/Johannesburg",
}).format(new Date(value));
const label = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

function Status({ status }: { status: string }) {
  return <span className={`sp-status sp-status-${status}`}><span aria-hidden="true" />{label(status)}</span>;
}

function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="sp-empty"><BookOpen size={26} aria-hidden="true" /><h3>{title}</h3><p>{children}</p></div>;
}

function LearnerCard({ learner }: { learner: SponsorLearner }) {
  const initials = learner.learner_label.split(/\s+/).slice(0, 2).map((part) => part[0]).join("");
  return <article className="sp-learner-card">
    <div className="sp-learner-top"><div className="sp-avatar" aria-hidden="true">{initials}</div><Status status={learner.status} /></div>
    <h3>{learner.learner_label}</h3><p>{learner.programme_label} <span aria-hidden="true">·</span> {learner.level}</p>
    <div className="sp-progress-label"><span>Course progress</span><strong>{learner.progress_percent === null ? "Not shared" : `${learner.progress_percent}%`}</strong></div>
    {learner.progress_percent !== null ? <progress max="100" value={learner.progress_percent} aria-label={`${learner.learner_label} course progress`} />
      : <p className="sp-consent-note"><ShieldCheck size={13} aria-hidden="true" />Learner privacy respected</p>}
    <div className="sp-learner-foot"><span>Funding allocated</span><strong>{exactMoney(learner.amount)}</strong></div>
  </article>;
}

export function SponsorDashboard({ data, state = "ready", initialView, signOutAction, preview = false }: {
  data: SponsorDashboardData | null;
  state?: "ready" | "approval" | "unavailable" | "invalid";
  initialView?: string;
  signOutAction?: () => Promise<void>;
  preview?: boolean;
}) {
  const router = useRouter();
  const [view, setView] = useState<View>(views.some((item) => item.key === initialView) ? initialView as View : "overview");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [chartStyle, setChartStyle] = useState<"bars" | "table">("bars");
  const currentYear = Number(new Intl.DateTimeFormat("en", { year: "numeric", timeZone: "Africa/Johannesburg" }).format(data ? new Date(data.as_of) : new Date()));
  const year = data?.year ?? currentYear;
  const target = Number(data?.sponsor.annual_target ?? 0);
  const achieved = Number(data?.summary.current_year_received ?? 0);
  const percent = target > 0 ? Math.min(100, Math.max(0, achieved / target * 100)) : 0;
  const maxContribution = Math.max(1, ...(data?.monthly_contributions.map((item) => Number(item.amount)) ?? []));
  const name = data?.sponsor.name ?? "Sponsor";
  const organisation = data?.sponsor.organisation || "Individual sponsor";
  const filteredLearners = data?.learners.filter((item) => `${item.learner_label} ${item.programme_label} ${item.level}`.toLowerCase().includes(search.toLowerCase()) && (status === "all" || item.status === status)) ?? [];
  const receivedCount = data?.contributions.filter((item) => item.status === "received").length ?? 0;
  const totals = data ? [
    { title: "Contributions received", value: exactMoney(data.summary.received), detail: "Verified funding · all time", icon: Wallet, tone: "green" },
    { title: "Students supported", value: String(data.summary.students_supported), detail: `${data.summary.active_students} currently active`, icon: UsersRound, tone: "blue" },
    { title: "Funding allocated", value: exactMoney(data.summary.allocated), detail: "Active & completed support", icon: GraduationCap, tone: "gold" },
    { title: "Available funding", value: exactMoney(data.summary.balance), detail: Number(data.summary.balance) < 0 ? "Funding gap · contact Amaris" : "Ready for future learning", icon: HeartHandshake, tone: "purple" },
  ] : [];
  const setSection = (next: View) => {
    if (data && data.page > 1) { router.push(`/sponsor?year=${year}&view=${next}`); return; }
    setView(next); setSearch(""); setStatus("all");
  };
  const pagination = (total: number) => data && total > data.page_size ? <nav className="sp-pagination" aria-label={`${view} pages`}>
    <span>Page {data.page} of {Math.ceil(total / data.page_size)} · {total} records</span>
    <div>{data.page > 1 && <Link href={`/sponsor?view=${view}&year=${year}&page=${data.page - 1}`}><ChevronLeft size={16} />Previous</Link>}
      {data.page * data.page_size < total && <Link href={`/sponsor?view=${view}&year=${year}&page=${data.page + 1}`}>Next<ChevronRight size={16} /></Link>}</div>
  </nav> : null;

  const contributions = (compact = false) => <section className="sp-panel sp-contributions">
    <div className="sp-panel-heading"><div><h2>{compact ? "Recent contributions" : "Contribution history"}</h2><p>Recorded funding for {year}. Pledges are separate from received funds.</p></div>
      {compact && <button className="sp-text-button" onClick={() => setSection("contributions")}>View all<ArrowRight size={15} /></button>}</div>
    {data?.contributions.length ? <div className="sp-table-scroll"><table><caption className="sp-sr-only">Your sponsor contributions for {year}</caption><thead><tr><th scope="col">Reference & purpose</th><th scope="col">Date</th><th scope="col">Status</th><th scope="col" className="sp-amount">Amount</th></tr></thead><tbody>
      {data.contributions.slice(0, compact ? 4 : undefined).map((item) => <tr key={item.reference}><th scope="row"><div className="sp-reference"><span className="sp-file-icon"><FileText size={17} /></span><div>{item.reference}<small>{item.description || "Education sponsorship"}</small></div></div></th><td>{day(item.date)}</td><td><Status status={item.status} /></td><td className="sp-amount">{exactMoney(item.amount)}</td></tr>)}
    </tbody></table></div> : <Empty title="Your contributions will appear here">Once Amaris records your first contribution, you can track its status and download a statement.</Empty>}
    {!compact && pagination(data?.contributions_total ?? 0)}
  </section>;

  const chart = <section className="sp-panel sp-chart-panel"><div className="sp-panel-heading"><div><h2>Your giving, over time</h2><p>Contributions received · {year} · ZAR</p></div><div className="sp-segment" aria-label="Contribution display">
    <button aria-pressed={chartStyle === "bars"} onClick={() => setChartStyle("bars")}>Chart</button><button aria-pressed={chartStyle === "table"} onClick={() => setChartStyle("table")}>Table</button></div></div>
    {data && data.monthly_contributions.some((item) => Number(item.amount) > 0) ? chartStyle === "bars" ? <div className="sp-chart" role="img" aria-label={`Monthly contributions received for ${year}. Switch to Table for exact amounts.`}>
      <div className="sp-chart-grid"><span>{money(maxContribution)}</span><span>{money(maxContribution / 2)}</span><span>R0</span></div>
      <div className="sp-bars">{data.monthly_contributions.map((item) => <div className="sp-bar-column" key={item.month}><div className="sp-bar-track"><div className="sp-bar" style={{ height: `${Number(item.amount) / maxContribution * 100}%` }} title={`${new Date(`${item.month}T00:00:00`).toLocaleString("en-ZA", { month: "long" })}: ${exactMoney(item.amount)}`} /></div><span>{new Date(`${item.month}T00:00:00`).toLocaleString("en-ZA", { month: "short" })}</span></div>)}</div>
    </div> : <div className="sp-chart-data"><table><caption className="sp-sr-only">Monthly received contributions</caption><thead><tr><th scope="col">Month</th><th scope="col">Amount received</th></tr></thead><tbody>{data.monthly_contributions.map((item) => <tr key={item.month}><th scope="row">{new Date(`${item.month}T00:00:00`).toLocaleString("en-ZA", { month: "long" })}</th><td>{exactMoney(item.amount)}</td></tr>)}</tbody></table></div>
      : <Empty title="A story ready to grow">Your monthly giving chart will build as contributions are received.</Empty>}
    <div className="sp-chart-footer"><span className="sp-dot" />Received funding<span className="sp-chart-footnote">Pledged and refunded funds excluded</span></div>
  </section>;

  return <div className="sp-workspace"><style dangerouslySetInnerHTML={{ __html: css }} />
    <a className="sp-skip" href="#sponsor-content">Skip to dashboard content</a>
    <aside className="sp-sidebar">
      <Link href="/" className="sp-brand"><span className="sp-logo" style={{ backgroundImage: `url(${academyBrand.logoPath})` }} aria-hidden="true" /><span>Amaris<small>MATHEMATICS ACADEMY</small></span></Link>
      <div className="sp-workspace-label">SPONSOR WORKSPACE</div>
      <nav aria-label="Sponsor navigation">{views.map(({ key, label: title, icon: Icon }) => <button key={key} onClick={() => setSection(key)} aria-current={view === key ? "page" : undefined}><Icon size={19} aria-hidden="true" /><span>{title}</span>{view === key && <span className="sp-nav-dot" />}</button>)}</nav>
      <div className="sp-sidebar-bottom"><div className="sp-help-card"><HeartHandshake size={27} aria-hidden="true" /><h2>Stronger, together.</h2><p>Let’s make your support go further.</p><a href={`${academyBrand.emailHref}?subject=Sponsorship%20support`}>Talk to Amaris<ArrowUpRight size={16} /></a></div><a href={preview ? academyBrand.emailHref : "/contact"} className="sp-help-link"><CircleHelp size={18} />Help & support</a>
        {signOutAction && <form action={signOutAction}><button type="submit" className="sp-help-link"><LogOut size={18} />Sign out</button></form>}
        <div className="sp-sidebar-footer">A little support. A brighter future.</div>
      </div>
    </aside>
    <div className="sp-main"><header className="sp-topbar"><div className="sp-breadcrumb">Sponsor workspace<span>/</span><strong>{views.find((item) => item.key === view)?.label}</strong></div><div className="sp-account"><span className="sp-secure"><ShieldCheck size={14} />Private workspace</span><div className="sp-account-avatar" aria-hidden="true">{name[0]}</div><div><strong>{name}</strong><small>{organisation}</small></div></div></header>
      <main id="sponsor-content" className="sp-content" tabIndex={-1}>
        {preview && <div className="sp-preview" role="status">Design preview · all names, amounts and progress shown here are fictional sample data.</div>}
        <div className="sp-page-heading"><div><p className="sp-eyebrow">INVESTING IN POSSIBILITY</p><h1>{view === "overview" ? `Welcome back, ${name.split(" ")[0]}.` : views.find((item) => item.key === view)?.label}</h1><p>Your support opens doors. See the learning you help make possible.</p></div>{data && <a className="sp-button sp-button-outline" href={preview ? "#preview-statement-note" : `/sponsor/statement?year=${year}`}><ArrowDownToLine size={17} />Download statement</a>}</div>
        {!data ? <section className="sp-panel sp-access-state" role="status"><ShieldCheck size={40} /><h2>{state === "approval" ? "Your sponsor workspace starts here" : state === "invalid" ? "Choose a valid reporting period" : "Your dashboard is temporarily unavailable"}</h2><p>{state === "approval" ? "Sponsor access is approved by Amaris. Contact our team to link your verified account to your sponsorship records." : state === "invalid" ? "Return to the overview to select a valid year and page." : "We could not load your sponsorship records. Please try again shortly or contact our team for help."}</p><div className="sp-actions"><a className="sp-button sp-button-primary" href={academyBrand.emailHref}><Mail size={16} />Contact Amaris</a><Link className="sp-button sp-button-outline" href="/sponsor">Try again</Link></div></section> : <>
          {view === "overview" && <><section className="sp-welcome-banner"><div><span><Sparkles size={15} />Every contribution counts</span><h2>You’re part of someone’s<br className="sp-desktop-break" /> next chapter.</h2><p>From a first lesson to a new level of confidence,<br className="sp-desktop-break" /> your support creates space for learning.</p><button className="sp-button sp-button-primary" onClick={() => setSection("learners")}>Meet your sponsored learners<ArrowRight size={16} /></button></div><div className="sp-banner-art" aria-hidden="true"><div className="sp-art-orbit" /><div className="sp-art-card sp-art-card-back"><BookOpen size={28} /><span>Building confidence</span><div className="sp-art-line" /><div className="sp-art-line short" /></div><div className="sp-art-card sp-art-card-front"><span className="sp-art-icon"><GraduationCap size={30} /></span><strong>Room to grow.</strong><span>One learner. One opportunity.</span><div className="sp-art-check"><Check size={13} />Supported by you</div></div><span className="sp-art-star">✦</span><span className="sp-art-plus">+</span></div></section>
            <section className="sp-metrics" aria-label="All-time sponsorship summary">{totals.map(({ title, value, detail, icon: Icon, tone }) => <article key={title} className="sp-metric"><div className="sp-metric-top"><span>{title}</span><span className={`sp-metric-icon ${tone}`}><Icon size={19} aria-hidden="true" /></span></div><strong>{value}</strong><p>{detail}</p></article>)}</section>
          </>}
          {(view === "overview" || view === "reports") && <><div className="sp-section-toolbar"><div><h2>{view === "reports" ? "Your impact report" : "Your support at a glance"}</h2><p>Clear records. Meaningful progress.</p></div><label className="sp-year-control"><CalendarDays size={16} aria-hidden="true" /><span className="sp-sr-only">Reporting year</span><select aria-label="Reporting year" value={year} disabled={preview} onChange={(event) => { router.push(`/sponsor?year=${event.target.value}&view=${view}`); }}>{Array.from({ length: currentYear - 2019 }, (_, index) => currentYear - index).map((value) => <option key={value} value={value}>{value}</option>)}</select></label></div>
            <div className="sp-report-grid">{chart}<section className="sp-panel sp-goal-panel"><div className="sp-panel-heading"><div><h2>Your {currentYear} giving goal</h2><p>Small steps. Lasting impact.</p></div><Target size={20} aria-hidden="true" /></div><div className="sp-goal-ring" style={{ background: `conic-gradient(#1d6657 ${percent}%, #e9f0ed 0)` }}><div><strong>{target > 0 ? `${Math.round(percent)}%` : "—"}</strong><span>{target > 0 ? "of annual goal" : "Goal not set"}</span></div></div><div className="sp-goal-figures"><strong>{exactMoney(String(achieved))}</strong><span>{target > 0 ? `received of ${exactMoney(String(target))}` : "received this year"}</span></div><p className="sp-goal-note">{target > 0 ? `${money(Math.max(0, target - achieved))} to reach your goal` : "Contact Amaris to set a giving goal that works for you."}</p><a href={`${academyBrand.emailHref}?subject=Sponsorship%20planning`} className="sp-text-button">Plan your next contribution<ArrowRight size={15} /></a></section></div>
          </>}
          {(view === "overview" || view === "learners") && <section className="sp-learners"><div className="sp-section-toolbar"><div><h2>Your sponsored learners</h2><p>Support you can see. Progress shared with permission.</p></div>{view === "overview" && <button className="sp-text-button" onClick={() => setSection("learners")}>View learners<ArrowRight size={15} /></button>}</div>
            {view === "learners" && <div className="sp-filters"><label className="sp-search"><Search size={17} aria-hidden="true" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search learners, programme or level" aria-label="Search learners on this page" /></label><select aria-label="Filter learners by status" value={status} onChange={(event) => setStatus(event.target.value)}>{["all", "active", "planned", "completed", "cancelled"].map((value) => <option key={value} value={value}>{value === "all" ? "All statuses" : label(value)}</option>)}</select></div>}
            {filteredLearners.length ? <div className="sp-learners-grid">{filteredLearners.slice(0, view === "overview" ? 3 : undefined).map((learner) => <LearnerCard key={learner.id} learner={learner} />)}</div> : <section className="sp-panel"><Empty title={data.learners.length ? "No matching learners" : "Your support story starts here"}>{data.learners.length ? "Try another search or status. Filters apply to the current page." : "When Amaris assigns your sponsorship, your learners and funding will appear here."}</Empty></section>}
            {view === "learners" && pagination(data.learners_total)}
          </section>}
          {(view === "overview" || view === "contributions") && contributions(view === "overview")}
          {view === "contributions" && <p className="sp-small-note">{receivedCount} received contributions on this page. All-time totals exclude pledges and refunded contributions.</p>}
          {view === "reports" && <section className="sp-panel sp-statement"><div className="sp-statement-icon"><FileText size={26} /></div><div><h2>{year} contribution statement</h2><p>Download your complete contribution record for this reporting year as a spreadsheet-compatible CSV. Includes received, pledged and refunded records.</p><small>A funding statement; not a tax certificate or payment invoice.</small></div><a className="sp-button sp-button-primary" href={preview ? "#preview-statement-note" : `/sponsor/statement?year=${year}`}><ArrowDownToLine size={17} />Download CSV</a></section>}
          {preview && <p id="preview-statement-note" className="sp-small-note">Statement downloads are available in the authenticated sponsor workspace. This preview contains sample data only.</p>}
          {Number(data.summary.balance) < 0 && <div className="sp-funding-notice"><CircleAlert size={20} /><p>Your allocated support exceeds received funding. Contact Amaris to confirm the funding plan.</p></div>}
          <footer className="sp-footer"><span><ShieldCheck size={14} />Only your sponsorship records · Last updated {day(data.as_of)}</span><a href={academyBrand.emailHref}>Need a hand? We’re here to help<ArrowUpRight size={14} /></a></footer>
        </>}
      </main>
    </div>
  </div>;
}
