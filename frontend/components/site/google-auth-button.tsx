import Link from "next/link";
import { googleAuthAction } from "@/app/auth/actions";

export function GoogleAuthButton({
  label,
  next = "/dashboard",
}: {
  label: string;
  next?: string;
}) {
  return (
    <div className="grid gap-3">
      <form action={googleAuthAction}>
        <input type="hidden" name="next" value={next} />
        <button
          type="submit"
          className="flex min-h-12 w-full items-center justify-center gap-3 rounded-full border border-[#cbd6e5] bg-white px-6 py-3 font-bold text-[#263852] shadow-sm transition hover:border-[#aebed3] hover:bg-[#f8fafc] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1f5bbd] focus-visible:ring-offset-2"
        >
          <GoogleMark />
          {label}
        </button>
      </form>
      <p className="text-center text-xs leading-5 text-[#60708a]">
        By continuing with Google, you agree to the{" "}
        <Link href="/terms" className="font-semibold text-[#1f5bbd] underline">Terms</Link>
        {" "}and{" "}
        <Link href="/privacy" className="font-semibold text-[#1f5bbd] underline">Privacy Policy</Link>.
      </p>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5">
      <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.04H12v3.86h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.24c1.9-1.75 2.98-4.33 2.98-7.34Z" />
      <path fill="#34A853" d="M12 22c2.7 0 4.97-.9 6.63-2.43l-3.24-2.5c-.9.6-2.05.96-3.39.96-2.61 0-4.82-1.76-5.61-4.13H3.04v2.59A10 10 0 0 0 12 22Z" />
      <path fill="#FBBC05" d="M6.39 13.9A6 6 0 0 1 6.08 12c0-.66.11-1.3.31-1.9V7.51H3.04A10 10 0 0 0 2 12c0 1.61.39 3.14 1.04 4.49l3.35-2.59Z" />
      <path fill="#EA4335" d="M12 5.97c1.47 0 2.79.51 3.83 1.5l2.87-2.88A9.63 9.63 0 0 0 12 2a10 10 0 0 0-8.96 5.51l3.35 2.59C7.18 7.73 9.39 5.97 12 5.97Z" />
    </svg>
  );
}
