import { initialLocation } from "@/lib/location-server";
import type { LocationValues } from "@/lib/location-data";
import type { Metadata } from "next";
import Link from "next/link";
import { GraduationCap, FileCheck2, ShieldCheck, ArrowRight } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getStudentIdentity } from "@/lib/auth";
import { applicationRequest, type TutorApplication } from "@/lib/tutor-applications";
import { ApplicationForm } from "@/components/tutor/application-form";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Become an Amaris tutor",
  description: "Apply to tutor at Amaris Mathematics Academy. Register, verify your email and submit your qualifications for academy review.",
};
const statuses = { submitted: "Application received", reviewing: "Under review", shortlisted: "Shortlisted", closed: "Review completed" };

export default async function TutorRecruitment({ searchParams }: { searchParams: Promise<{ error?: string } & Partial<LocationValues>> }) {
  const identity = await getStudentIdentity();
  const params = await searchParams;
  const { error } = params;
  const location = await initialLocation(params);
  let application: TutorApplication | null = null;
  let unavailable = false;
  if (identity?.emailVerified) {
    try {
      const response = await applicationRequest();
      if (!response.ok) unavailable = true;
      else application = ((await response.json()) as { application: TutorApplication | null }).application;
    } catch { unavailable = true; }
  }
  return <main className="min-h-screen bg-[#f5f7fb] text-[#07152d]">
    <Header />
    <section className="bg-[#07152d] text-white"><div className="mx-auto grid max-w-6xl gap-10 px-5 py-14 lg:grid-cols-[1.2fr_.8fr] lg:px-8 lg:py-20"><div><span className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/20 px-4 py-2 text-xs font-bold uppercase tracking-[.15em] text-[#ffcc66]"><GraduationCap className="size-4" /> Tutor opportunities</span><h1 className="max-w-2xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">Share your knowledge.<br />Become an Amaris tutor.</h1><p className="mt-6 max-w-xl text-lg leading-8 text-white/80">Help school, TVET and university learners build confidence. Tell us what you can teach and submit your qualifications for our recruitment team to review.</p>{!identity?.emailVerified && <div className="mt-8 flex flex-wrap gap-4"><Link href="/tutor/register" className="inline-flex min-h-12 items-center gap-3 rounded-full bg-[#ffcc66] px-6 py-3 font-bold text-[#07152d]">Register to apply<ArrowRight className="size-4" /></Link><Link href="/tutor/apply/login" className="inline-flex min-h-12 items-center rounded-full border border-white/40 px-6 py-3 font-semibold text-white">Already registered? Sign in</Link></div>}</div><aside className="self-center rounded-3xl border border-white/15 bg-white/5 p-7"><h2 className="text-xl font-semibold">Prepare your application</h2><ul className="mt-5 grid gap-5 text-sm leading-7 text-white/85"><li className="flex gap-3"><FileCheck2 className="mt-1 size-5 shrink-0 text-[#ffcc66]" /><span>Your relevant academic or teaching qualifications and awarding institution.</span></li><li className="flex gap-3"><GraduationCap className="mt-1 size-5 shrink-0 text-[#ffcc66]" /><span>Subjects, programmes, grades or modules you can teach, plus your experience and availability.</span></li><li className="flex gap-3"><ShieldCheck className="mt-1 size-5 shrink-0 text-[#ffcc66]" /><span>Clear PDF or image copies of qualifications. Your uploads stay private.</span></li></ul></aside></div></section>
    <div className="mx-auto max-w-6xl px-5 py-12 lg:px-8">
      <ol aria-label="Application steps" className="mb-12 grid gap-4 sm:grid-cols-3">{[["01", "Register and verify", "Create an account and confirm your email, or sign in with your existing account."], ["02", "Apply with qualifications", "Complete your teaching profile and upload your qualification documents."], ["03", "Receive acknowledgement", "Get an application reference and an email acknowledgement. Return here to track review."]].map(([number, title, detail]) => <li key={number} className="rounded-2xl border border-[#dce4ef] bg-white p-6"><p className="text-sm font-bold text-[#1f5bbd]">{number}</p><h2 className="mt-3 text-lg font-semibold">{title}</h2><p className="mt-3 text-sm leading-7 text-[#60708a]">{detail}</p></li>)}</ol>
      <div className="mx-auto max-w-3xl">
        {error && <p role="alert" className="mb-6 rounded-xl border border-red-200 bg-red-50 p-5 text-red-900">{error}</p>}
        {unavailable ? <section role="alert" className="rounded-3xl border border-[#dce4ef] bg-white p-8"><h2 className="text-2xl font-semibold">Application service temporarily unavailable</h2><p className="mt-4 leading-7 text-[#60708a]">We could not load your application. Please retry shortly. You do not need to register again.</p><Link href="/tutor/apply" className="mt-5 inline-block font-bold text-[#1f5bbd] underline">Try again</Link></section>
          : application ? <section id="application-status" className="rounded-3xl border border-[#b4dccd] bg-white p-7 sm:p-10"><p className="eyebrow">Your tutor application</p><h2 className="mt-4 text-3xl font-semibold">{statuses[application.status] || "Application received"}</h2><p className="mt-5 leading-7 text-[#52617a]">Thank you. Your application and qualification documents have been received. Your reference is <strong className="break-all text-[#07152d]">{application.reference}</strong>.</p><p className="mt-4 text-sm leading-7 text-[#60708a]">Submitted {new Date(application.submitted_at).toLocaleString("en-ZA", { timeZone: "Africa/Johannesburg" })} (SAST).</p><p className="mt-4 rounded-xl bg-[#f5f7fb] p-4 text-sm leading-7">{application.acknowledgement_sent_at ? "Your acknowledgement email has been sent. Check your inbox and spam folder." : "Your acknowledgement email is queued. Your application is saved even while email delivery is pending."}</p>{!application.acknowledgement_sent_at && <form action="/api/tutor-applications" method="post" encType="multipart/form-data" className="mt-4"><input type="hidden" name="_action" value="retry-email" /><button type="submit" className="min-h-11 rounded-full border border-[#cbd6e5] px-5 py-2 font-semibold text-[#1f5bbd]">Retry acknowledgement email</button><p className="mt-2 text-xs leading-6 text-[#60708a]">Retries are limited while the mail service recovers. Your saved application will not be duplicated.</p></form>}<h3 className="mt-7 font-semibold">Your submitted qualifications</h3><ul className="mt-4 grid gap-3">{application.documents.map(document => <li key={document.id}><a href={`/api/tutor-applications/documents/${document.id}`} className="break-words font-semibold text-[#1f5bbd] underline">{document.original_name}</a></li>)}</ul><p className="mt-7 text-sm leading-7 text-[#60708a]">The academy reviews applications manually. This acknowledgement is not an offer or teaching approval. For a correction or a question about your application, <Link href="/contact" className="font-semibold text-[#1f5bbd] underline">contact us</Link> and quote your reference.</p><Link href="/tutor/apply" className="mt-5 inline-block font-semibold text-[#1f5bbd] underline">Refresh application status</Link></section>
          : identity?.emailVerified ? <section className="rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-10"><h2 className="mb-7 text-3xl font-semibold tracking-tight">Your tutor application</h2><ApplicationForm name={identity.displayName} email={identity.email} location={location} /></section>
          : <section className="rounded-3xl border border-[#dce4ef] bg-white p-8 text-center"><h2 className="text-2xl font-semibold">Ready to introduce yourself?</h2><p className="mt-4 leading-7 text-[#60708a]">Register or sign in before completing your private application. Already approved as a tutor? Use the <Link href="/tutor/login" className="font-semibold text-[#1f5bbd] underline">tutor portal</Link>.</p><Link href="/tutor/register" className="mt-6 inline-flex min-h-12 items-center rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white">Start your application</Link></section>}
        <section id="recruitment-privacy" className="mt-8 rounded-2xl border border-[#dce4ef] p-6"><h2 className="font-semibold">Recruitment privacy notice</h2><p className="mt-3 text-sm leading-7 text-[#60708a]">Amaris uses your verified account, application details, ID, CV, Matric certificate, academic records, tertiary certificate and additional document to check your identity and qualifications and to assess your suitability for tutoring. These sensitive files are held privately and are accessible only to you and authorised recruitment administrators. They are never included in recruitment acknowledgement emails. They are not published or attached to acknowledgement emails. Applications are reviewed by people; registration does not grant tutor access. For access, correction, withdrawal or deletion requests, <Link href="/contact" className="font-semibold text-[#1f5bbd] underline">contact the academy</Link>. See our <Link href="/privacy" className="font-semibold text-[#1f5bbd] underline">Privacy Policy</Link>.</p></section>
      </div>
    </div><Footer />
  </main>;
}
