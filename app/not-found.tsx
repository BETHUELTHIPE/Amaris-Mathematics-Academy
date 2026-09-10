import { RecoveryPage } from "@/components/site/recovery-page";
import { httpRecoveryDefinitions } from "@/lib/recovery";

export default function NotFound() {
  return <RecoveryPage definition={httpRecoveryDefinitions["404"]} />;
}

