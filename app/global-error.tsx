"use client";

import { RecoveryScreen } from "@/components/site/recovery-screen";
import { httpRecoveryDefinitions } from "@/lib/recovery";

export default function GlobalError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  const reference = error.digest ? `AMR-${error.digest.replace(/[^A-Za-z0-9-]/g, "").slice(0, 48).toUpperCase()}` : undefined;
  return <html lang="en-ZA"><body><RecoveryScreen definition={httpRecoveryDefinitions["500"]} reference={reference} /></body></html>;
}

