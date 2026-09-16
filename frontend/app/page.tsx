import Link from "next/link";
import { ArrowRight, BarChart3, BookOpenCheck, Check, CirclePlay, GraduationCap, ShieldCheck, Sigma, Target } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { formatRand } from "@/lib/courses";
import { getManagedCourses } from "@/lib/cms";

export default async function Home() {
  const courses = await getManagedCourses();
  const featured = courses.filter((course) => course.featured);
  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#0a1b36]">
      <Header />
      <section className="relative isolate overflow-hidden bg-[#07152d] text-white">
        {/* Direct delivery avoids the Vinext image optimizer path while keeping the LCP image discoverable in the initial HTML. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/amaris-math-hero.webp" alt="A student working through mathematics in a focused study environment" width={1600} height={900} fetchPriority="high" loading="eager" decoding="sync" className="absolute inset-0 h-full w-full object-cover object-[62%_center] opacity-90" />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,#07152d_0%,rgba(7,21,45,.95)_34%,rgba(7,21,45,.66)_54%,rgba(7,21,45,.04)_100%)]" />
        <div className="graph-paper absolute inset-0 opacity-15" />
        <div className="relative mx-auto grid min-h-[690px] max-w-7xl items-center px-5 py-20 lg:px-8">
          <div className="max-w-2xl">
            <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/8 px-4 py-2 text-sm text-white/80 backdrop-blur"><span className="size-2 rounded-full bg-[#ffcc66]" /> Mathematics for school, TVET & university</div>
            <h1 className="text-5xl font-semibold leading-[1.02] tracking-[-0.055em] sm:text-6xl lg:text-[5.4rem]">Master mathematics,<br /><span className="text-[#ffcc66]">one clear step</span> at a time.</h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-white/70">Structured lessons, worked examples and deliberate practice—built to turn uncertainty into confident problem-solving.</p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link href="/courses" prefetch={false} className="inline-flex items-center justify-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3.5 font-bold text-[#07152d] transition hover:bg-[#ffd780]">Browse courses <ArrowRight className="size-4" /></Link>
              <Link href="/how-it-works" prefetch={false} className="inline-flex items-center justify-center gap-2 rounded-full border border-white/25 bg-white/8 px-6 py-3.5 font-semibold text-white backdrop-blur transition hover:bg-white/15"><CirclePlay className="size-4" /> See how it works</Link>
            </div>
            <div className="mt-10 flex flex-wrap gap-x-6 gap-y-3 text-sm text-white/65"><span className="flex items-center gap-2"><Check className="size-4 text-[#ffcc66]" /> Learn at your pace</span><span className="flex items-center gap-2"><Check className="size-4 text-[#ffcc66]" /> Track every lesson</span><span className="flex items-center gap-2"><Check className="size-4 text-[#ffcc66]" /> Secure PayFast checkout</span></div>
          </div>
        </div>
      </section>

      <section className="relative z-10 mx-auto -mt-9 max-w-7xl px-5 lg:px-8" aria-label="Platform highlights">
        <div className="grid divide-y divide-[#dce4ef] overflow-hidden rounded-3xl border border-[#dce4ef] bg-white shadow-[0_22px_70px_rgba(7,21,45,.12)] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {[["6","focused programmes","A concise catalogue without distractions"],["220+","guided lessons","Clear explanations and deliberate practice"],["3","learning pathways","School, TVET and university mathematics"]].map(([value,label,description]) => <div key={label} className="p-6 sm:p-7"><div className="text-3xl font-bold tracking-tight text-[#0b2a5b]">{value}</div><div className="mt-1 font-semibold">{label}</div><div className="mt-2 text-sm leading-6 text-[#60708a]">{description}</div></div>)}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-24 lg:px-8">
        <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end"><div><p className="eyebrow">Featured courses</p><h2 className="section-title mt-3">Choose the next result<br />you want to earn.</h2></div><Link href="/courses" prefetch={false} className="inline-flex items-center gap-2 font-bold text-[#1f5bbd]">View all mathematics courses <ArrowRight className="size-4" /></Link></div>
        <div className="mt-10 grid gap-5 lg:grid-cols-3">{featured.map((course, index) => <article key={course.slug} className="group flex min-h-[360px] flex-col rounded-3xl border border-[#dce4ef] bg-white p-7 shadow-[0_20px_55px_rgba(7,21,45,.055)] transition hover:-translate-y-1 hover:shadow-[0_25px_70px_rgba(7,21,45,.1)]"><div className="flex items-center justify-between"><span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">{course.curriculum}</span><span className="text-sm font-semibold text-[#60708a]">0{index+1}</span></div><h3 className="mt-10 text-3xl font-semibold leading-tight tracking-[-0.035em]">{course.title}</h3><p className="mt-4 text-sm leading-7 text-[#60708a]">{course.description}</p><div className="mt-auto flex items-end justify-between pt-8"><div><p className="text-xs text-[#60708a]">{course.lessons} lessons · {course.hours} hours</p><p className="mt-1 text-2xl font-bold">{formatRand(course.price)}</p></div><Link href={`/courses/${course.slug}`} prefetch={false} className="grid size-12 place-items-center rounded-full bg-[#0b2a5b] text-white transition group-hover:bg-[#2767d8]" aria-label={`View ${course.title}`}><ArrowRight className="size-5" /></Link></div></article>)}</div>
      </section>

      <section className="overflow-hidden bg-white py-24">
        <div className="mx-auto grid max-w-7xl gap-14 px-5 lg:grid-cols-[.9fr_1.1fr] lg:items-center lg:px-8">
          <div><p className="eyebrow">Built for progress</p><h2 className="section-title mt-3">Know what to learn next.</h2><p className="mt-6 max-w-lg text-base leading-8 text-[#60708a]">Your learning path stays simple: watch a focused explanation, work through examples, practise independently and see exactly where to continue.</p><Link href="/register" prefetch={false} className="mt-8 inline-flex items-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3.5 font-bold text-white">Create your student profile <ArrowRight className="size-4" /></Link></div>
          <div className="relative rounded-[2rem] bg-[#0b2a5b] p-5 text-white shadow-[0_30px_90px_rgba(7,21,45,.2)] sm:p-8"><div className="absolute -right-20 -top-20 size-56 rounded-full bg-[#2767d8]/35 blur-3xl" /><div className="relative flex items-center justify-between border-b border-white/12 pb-6"><div><p className="text-sm text-white/55">Your learning plan</p><h3 className="mt-1 text-2xl font-semibold">Grade 12 Mathematics</h3></div><span className="rounded-full bg-[#20a68a]/20 px-3 py-1.5 text-xs font-bold text-[#6ee7c6]">On track</span></div><div className="relative mt-7 grid gap-4 sm:grid-cols-2"><div className="rounded-2xl bg-white/8 p-5"><BarChart3 className="size-5 text-[#ffcc66]" /><p className="mt-5 text-3xl font-bold">68%</p><p className="mt-1 text-sm text-white/55">Course completed</p><div className="mt-5 h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full w-[68%] rounded-full bg-[#ffcc66]" /></div></div><div className="rounded-2xl bg-white/8 p-5"><Target className="size-5 text-[#6ee7c6]" /><p className="mt-5 text-lg font-semibold">Differential calculus</p><p className="mt-1 text-sm text-white/55">Next recommended topic</p><Link href="/dashboard" prefetch={false} className="mt-5 inline-block rounded-full bg-white px-4 py-2 text-sm font-bold text-[#0b2a5b]">Continue lesson</Link></div></div><div className="relative mt-4 rounded-2xl border border-white/10 bg-[#07152d]/60 p-5"><div className="flex items-center gap-4"><div className="grid size-11 place-items-center rounded-xl bg-[#2767d8]"><Sigma className="size-5" /></div><div className="flex-1"><div className="flex justify-between gap-4 text-sm"><span>Weekly goal</span><span className="font-semibold">4 of 5 lessons</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full w-4/5 rounded-full bg-[#2767d8]" /></div></div></div></div></div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-24 lg:px-8">
        <div className="text-center"><p className="eyebrow">A clearer way to learn</p><h2 className="section-title mt-3">From registration to real progress.</h2></div>
        <div className="mt-14 grid gap-5 md:grid-cols-3">{[[GraduationCap,"01","Choose your level","Find the mathematics pathway that matches your curriculum, grade and goal."],[ShieldCheck,"02","Enrol securely","Create your profile first, then complete payment through PayFast or Google Pay."],[BookOpenCheck,"03","Learn and measure","Continue from where you stopped, complete practice and see your progress grow."]].map(([Icon,number,title,copy]) => {const C = Icon as typeof GraduationCap; return <div key={title as string} className="rounded-3xl border border-[#dce4ef] bg-white p-7"><div className="flex items-center justify-between"><span className="grid size-12 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><C className="size-6" /></span><span className="font-mono text-sm text-[#60708a]">{number as string}</span></div><h3 className="mt-8 text-2xl font-semibold">{title as string}</h3><p className="mt-3 text-sm leading-7 text-[#60708a]">{copy as string}</p></div>})}</div>
      </section>

      <section className="px-5 pb-24 lg:px-8"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-8 overflow-hidden rounded-[2rem] bg-[#ffcc66] p-8 sm:p-12 lg:flex-row lg:items-center"><div><p className="text-sm font-bold uppercase tracking-[.16em] text-[#0b2a5b]">Start where you are</p><h2 className="mt-3 max-w-2xl text-4xl font-semibold leading-tight tracking-[-.04em] text-[#07152d] sm:text-5xl">Your next mathematics breakthrough starts with one lesson.</h2></div><Link href="/courses" prefetch={false} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-full bg-[#07152d] px-7 py-4 font-bold text-white">Explore courses <ArrowRight className="size-4" /></Link></div></section>
      <Footer />
    </main>
  );
}
