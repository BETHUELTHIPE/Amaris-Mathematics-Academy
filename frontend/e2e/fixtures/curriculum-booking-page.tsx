// Installed only in isolated CI builds; no authentication bypass is deployed.
import { LiveClassBookingFilters } from "@/app/book-online-live-class/live-class-booking-filters";
import { VideoRequestForm } from "@/components/site/video-request-form";
import { TutorSlotFields } from "@/components/tutor/slot-fields";
import type { TutorSlot } from "@/lib/tutor-api";

const existing: TutorSlot = { id: 1, programme: "ieb", subject: "mathematics", level: "Grade 11", starts_at: "2027-02-01T13:00:00Z", ends_at: "2027-02-01T15:00:00Z", duration_hours: 2, zoom_join_url: "https://zoom.example.test/j/synthetic", is_active: true, price: "500.00", reserved: false, editable: true };

export default function CurriculumFixture() {
  return <main className="mx-auto max-w-5xl space-y-10 p-5">
    <h1>Isolated booking curriculum checks</h1>
    <section id="live"><h2>Live booking</h2><LiveClassBookingFilters initialProgramme="" initialSubject="" initialLevel="" initialTopic="" offeredLevels={[]} tutors={[{ id: 101, name: "Synthetic Day Tutor" }, { id: 102, name: "Synthetic Night Tutor" }]} /></section>
    <section id="video"><h2>Video request</h2><VideoRequestForm packages={[{ value: "chapter_topic", label: "Chapter or topic video", amount: "450.00", currency: "ZAR" }]} /></section>
    <section id="create-slot"><h2>Create availability</h2><form><TutorSlotFields /></form></section>
    <section id="edit-slot"><h2>Edit availability</h2><form><TutorSlotFields slot={existing} /></form></section>
  </main>;
}
