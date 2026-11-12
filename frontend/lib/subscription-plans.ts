export const subscriptionPlans = [
  { slug: "4-months", months: 4, price: 3800, title: "Four months of focus", description: "Build your foundations with weekly tutor support and courses in your chosen curriculum." },
  { slug: "8-months", months: 8, price: 7600, title: "Eight months of progress", description: "Keep a steady learning rhythm, with more time to revisit topics and prepare for assessments." },
] as const;
export const subscriptionSupport = {
  sessionsPerWeek: 2,
  minutesPerSession: 120,
  weeklySessions: "Two 2-hour one-to-one Zoom sessions every week",
  weeklyTotal: "4 hours of one-to-one tutor support per week",
  scheduling: "After payment is verified, contact the academy with your subscription reference to arrange your included sessions.",
  sessions: [
    { title: "Understand it", description: "Bring the concept that has you stuck. Work through the method with your tutor and ask your questions." },
    { title: "Put it into practice", description: "Apply the method to questions, review mistakes with your tutor and prepare your next steps." },
  ],
} as const;
export const subscriptionCurricula = [
  { value: "caps", label: "CAPS", description: "South African school curriculum" },
  { value: "ieb", label: "IEB", description: "Independent school curriculum" },
  { value: "nated", label: "TVET NATED", description: "NATED mathematics programmes" },
  { value: "ncv", label: "TVET NC(V)", description: "National Certificate (Vocational)" },
  { value: "university", label: "University / UNISA", description: "University mathematics courses" },
] as const;
export function subscriptionPlan(slug: string) { return subscriptionPlans.find(plan => plan.slug === slug); }
export function subscriptionCurriculum(value: string) { return subscriptionCurricula.find(curriculum => curriculum.value === value); }
export function subscriptionPrice(price: number) { return `R${price.toLocaleString("en-ZA").replace(/\s/g, ",")}`; }
