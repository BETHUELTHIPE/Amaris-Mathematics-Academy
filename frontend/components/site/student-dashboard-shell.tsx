import type { ReactNode } from "react";
import { DashboardNavigation, type DashboardSection } from "@/components/site/dashboard-navigation";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";

type StudentDashboardShellProps = {
  active: DashboardSection;
  title: string;
  description: string;
  headerAside?: ReactNode;
  children: ReactNode;
};

export function StudentDashboardShell({
  active,
  title,
  description,
  headerAside,
  children,
}: StudentDashboardShellProps) {
  return <main className="min-h-screen min-w-0 bg-[#f5f7fb]">
    <Header />
    <section className="border-b border-[#dce4ef] bg-white">
      <div className="mx-auto flex max-w-7xl min-w-0 flex-col justify-between gap-5 px-4 py-8 sm:px-5 sm:py-10 md:flex-row md:items-end lg:px-8">
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Student dashboard</p>
          <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-[-.045em] [overflow-wrap:anywhere] sm:text-4xl lg:text-5xl">{title}</h1>
          <p className="mt-3 max-w-2xl text-[#60708a]">{description}</p>
        </div>
        {headerAside}
      </div>
    </section>
    <section className="mx-auto grid max-w-7xl min-w-0 gap-5 px-4 py-6 sm:px-5 sm:py-10 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)] lg:gap-7 lg:px-8">
      <DashboardNavigation active={active} />
      <div className="min-w-0">{children}</div>
    </section>
    <Footer />
  </main>;
}
