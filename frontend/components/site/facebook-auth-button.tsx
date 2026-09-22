import Link from "next/link";
import { facebookAuthAction } from "@/app/auth/actions";

export function FacebookAuthButton({
  label,
  next = "/dashboard",
}: {
  label: string;
  next?: string;
}) {
  return (
    <div className="grid gap-3">
      <form action={facebookAuthAction}>
        <input type="hidden" name="next" value={next} />
        <button
          type="submit"
          className="flex min-h-12 w-full items-center justify-center gap-3 rounded-full border border-[#cbd6e5] bg-white px-6 py-3 font-bold text-[#263852] shadow-sm transition hover:border-[#aebed3] hover:bg-[#f8fafc] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1f5bbd] focus-visible:ring-offset-2"
        >
          <FacebookMark />
          {label}
        </button>
      </form>
      <p className="text-center text-xs leading-5 text-[#718096]">
        By continuing with Facebook, you agree to the{" "}
        <Link href="/terms" className="font-semibold text-[#1f5bbd] underline">Terms</Link>
        {" "}and{" "}
        <Link href="/privacy" className="font-semibold text-[#1f5bbd] underline">Privacy Policy</Link>.
      </p>
    </div>
  );
}

function FacebookMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5">
      <path fill="#1877F2" d="M24 12.07C24 5.41 18.63 0 12 0S0 5.41 0 12.07C0 18.09 4.39 23.08 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.03 1.79-4.7 4.53-4.7 1.31 0 2.68.24 2.68.24v2.96h-1.51c-1.49 0-1.95.93-1.95 1.89v2.27h3.32l-.53 3.49h-2.79V24C19.61 23.08 24 18.09 24 12.07Z" />
    </svg>
  );
}
