import type { StudentIdentity } from "@/lib/auth";

type AccountDetails = Pick<StudentIdentity, "displayName" | "email">;

/**
 * Reuse the same private signed-in identity design across student and tutor
 * dashboards. The parent server page obtains identity from authenticated,
 * email-verified Supabase user records, never from URL or form fields.
 */
export function DashboardAccountIdentity({
  identity,
  role,
}: {
  identity: AccountDetails;
  role: "Student" | "Tutor";
}) {
  return (
    <section
      aria-label="Signed-in account"
      className="min-w-0 max-w-full rounded-2xl border border-[#cad9ee] bg-[#edf3ff] px-4 py-3 text-left text-[#0b2a5b]"
    >
      <p className="text-xs font-bold uppercase tracking-[.12em]">Signed in as · {role}</p>
      <p className="mt-1 text-base font-bold leading-6 [overflow-wrap:anywhere]">{identity.displayName}</p>
      <p className="mt-1 text-sm font-medium leading-5 [overflow-wrap:anywhere]">{identity.email}</p>
    </section>
  );
}
