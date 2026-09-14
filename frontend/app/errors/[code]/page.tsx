import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { RecoveryPage } from "@/components/site/recovery-page";
import { httpRecoveryDefinitions } from "@/lib/recovery";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Website Recovery", robots: { index: false, follow: false } };

export function generateStaticParams() {
  return Object.keys(httpRecoveryDefinitions).map((code) => ({ code }));
}

export default async function HttpRecoveryPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const definition = httpRecoveryDefinitions[code as keyof typeof httpRecoveryDefinitions];
  if (!definition) notFound();
  return <RecoveryPage definition={definition} />;
}

