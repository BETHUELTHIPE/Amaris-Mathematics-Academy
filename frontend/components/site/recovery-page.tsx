import { headers } from "next/headers";
import { RecoveryScreen } from "@/components/site/recovery-screen";
import { createCorrelationReference, type RecoveryDefinition } from "@/lib/recovery";

export async function RecoveryPage({ definition }: { definition: RecoveryDefinition }) {
  const requestHeaders = await headers();
  const suppliedReference = requestHeaders.get("x-amaris-correlation-id");
  const reference = suppliedReference && /^AMR-[A-Z0-9-]{8,64}$/.test(suppliedReference)
    ? suppliedReference
    : createCorrelationReference();

  return <RecoveryScreen definition={definition} reference={reference} />;
}

