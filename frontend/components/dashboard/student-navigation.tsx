import Link from "next/link";
import { Bell, BookOpen, CreditCard, LayoutDashboard, UserRound } from "lucide-react";

export type StudentDashboardPath =
  | "/dashboard"
  | "/dashboard/courses"
  | "/dashboard/orders"
  | "/dashboard/notifications"
  | "/dashboard/profile";

const items = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "My courses", href: "/dashboard/courses", icon: BookOpen },
  { label: "Orders & payments", href: "/dashboard/orders", icon: CreditCard },
  { label: "Notifications", href: "/dashboard/notifications", icon: Bell },
  { label: "Profile & security", href: "/dashboard/profile", icon: UserRound },
] as const;

export function StudentDashboardNavigation({ currentPath }: { currentPath: StudentDashboardPath }) {
  return (
    <aside className="h-fit rounded-2xl border border-[#dce4ef] bg-white p-3">
      <nav className="grid gap-1" aria-label="Dashboard navigation">
        {items.map(({ label, href, icon: Icon }) => {
          const active = currentPath === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-11 items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd] ${active ? "bg-[#0b2a5b] text-white" : "text-[#36506f] hover:bg-[#edf3ff]"}`}
            >
              <Icon className="size-4 shrink-0" aria-hidden="true" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
