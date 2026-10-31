import Link from "next/link";
import {
  Bell,
  BookOpen,
  CreditCard,
  GitBranch,
  LayoutDashboard,
  LibraryBig,
  UserRound,
} from "lucide-react";

export type DashboardSection = "overview" | "orders" | "notifications" | "library";

const items = [
  { key: "overview", label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { key: "courses", label: "My courses", href: "/dashboard#my-courses", icon: BookOpen },
  { key: "library", label: "Library", href: "/dashboard/library", icon: LibraryBig },
  { key: "workflows", label: "My workflows", href: "/dashboard#my-workflows", icon: GitBranch },
  { key: "orders", label: "Orders & payments", href: "/dashboard/orders", icon: CreditCard },
  { key: "notifications", label: "Notifications", href: "/dashboard/notifications", icon: Bell },
  { key: "profile", label: "Profile & security", href: "/reset-password", icon: UserRound },
] as const;

export function DashboardNavigation({ active }: { active: DashboardSection }) {
  return <aside className="h-fit min-w-0 rounded-2xl border border-[#dce4ef] bg-white p-3 lg:sticky lg:top-32">
    <nav className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-1 lg:gap-1" aria-label="Dashboard navigation">
      {items.map(({ key, label, href, icon: Icon }) => {
        const isActive = key === active;
        return <Link
          key={key}
          href={href}
          aria-current={isActive ? "page" : undefined}
          className={`flex min-h-12 min-w-0 items-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd] lg:gap-3 lg:px-4 ${isActive ? "bg-[#0b2a5b] text-white" : "text-[#31537e] hover:bg-[#edf3ff] focus-visible:bg-[#edf3ff]"}`}
        >
          <Icon aria-hidden="true" className="size-4 shrink-0" />
          <span className="min-w-0 break-words">{label}</span>
        </Link>;
      })}
    </nav>
  </aside>;
}
