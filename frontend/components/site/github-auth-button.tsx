import Link from "next/link";
import { githubAuthAction } from "@/app/auth/actions";

export function GitHubAuthButton({
  label,
  next = "/dashboard",
}: {
  label: string;
  next?: string;
}) {
  return (
    <div className="grid gap-3">
      <form action={githubAuthAction}>
        <input type="hidden" name="next" value={next} />
        <button
          type="submit"
          className="flex min-h-12 w-full items-center justify-center gap-3 rounded-full border border-[#cbd6e5] bg-white px-6 py-3 font-bold text-[#263852] shadow-sm transition hover:border-[#aebed3] hover:bg-[#f8fafc] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1f5bbd] focus-visible:ring-offset-2"
        >
          <GitHubMark />
          {label}
        </button>
      </form>
      <p className="text-center text-xs leading-5 text-[#60708a]">
        By continuing with GitHub, you agree to the{" "}
        <Link href="/terms" className="font-semibold text-[#1f5bbd] underline">Terms</Link>
        {" "}and{" "}
        <Link href="/privacy" className="font-semibold text-[#1f5bbd] underline">Privacy Policy</Link>.
      </p>
    </div>
  );
}

function GitHubMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5">
      <path fill="#181717" d="M12 .7a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.22c-3.21.7-3.89-1.38-3.89-1.38-.52-1.35-1.28-1.7-1.28-1.7-1.05-.73.08-.71.08-.71 1.16.08 1.77 1.2 1.77 1.2 1.03 1.78 2.7 1.27 3.36.97.1-.75.4-1.27.73-1.56-2.56-.3-5.25-1.29-5.25-5.76 0-1.27.45-2.31 1.19-3.12-.12-.3-.52-1.49.11-3.11 0 0 .97-.31 3.18 1.19a10.95 10.95 0 0 1 5.79 0c2.2-1.5 3.17-1.19 3.17-1.19.63 1.62.23 2.81.12 3.11.74.81 1.18 1.85 1.18 3.12 0 4.48-2.7 5.46-5.27 5.75.42.36.78 1.08.78 2.18v3.23c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" />
    </svg>
  );
}
