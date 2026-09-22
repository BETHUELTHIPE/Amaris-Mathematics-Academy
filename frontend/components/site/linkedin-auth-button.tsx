import Link from "next/link";
import { linkedInAuthAction } from "@/app/auth/actions";

export function LinkedInAuthButton({
  label,
  next = "/dashboard",
}: {
  label: string;
  next?: string;
}) {
  return (
    <div className="grid gap-3">
      <form action={linkedInAuthAction}>
        <input type="hidden" name="next" value={next} />
        <button
          type="submit"
          className="flex min-h-12 w-full items-center justify-center gap-3 rounded-full border border-[#cbd6e5] bg-white px-6 py-3 font-bold text-[#263852] shadow-sm transition hover:border-[#aebed3] hover:bg-[#f8fafc] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1f5bbd] focus-visible:ring-offset-2"
        >
          <LinkedInMark />
          {label}
        </button>
      </form>
      <p className="text-center text-xs leading-5 text-[#60708a]">
        By continuing with LinkedIn, you agree to the{" "}
        <Link href="/terms" className="font-semibold text-[#1f5bbd] underline">Terms</Link>
        {" "}and{" "}
        <Link href="/privacy" className="font-semibold text-[#1f5bbd] underline">Privacy Policy</Link>.
      </p>
    </div>
  );
}

function LinkedInMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5">
      <path fill="#0A66C2" d="M20.45 20.45h-3.56v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V8.98h3.42v1.57h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.29ZM5.32 7.41a2.07 2.07 0 1 1 0-4.14 2.07 2.07 0 0 1 0 4.14ZM7.1 20.45H3.54V8.98H7.1v11.47Z" />
    </svg>
  );
}
