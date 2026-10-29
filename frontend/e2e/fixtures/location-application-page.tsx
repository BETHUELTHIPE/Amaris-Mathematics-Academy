// Copied into app/location-test-fixture/page.tsx only by the browser CI job.
// Never included in a release checkout or deployment artifact.
import { ApplicationForm } from "@/components/tutor/application-form";
import { initialLocation } from "@/lib/location-server";
export default async function LocationApplicationFixture() {
  return <main className="mx-auto max-w-3xl p-5"><h1>Tutor application test fixture</h1><ApplicationForm name="Synthetic Applicant" email="synthetic@example.test" location={await initialLocation()} /></main>;
}
