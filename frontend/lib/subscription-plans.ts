export const subscriptionPlans = [
  { slug: "4-months", months: 4, price: 3800, title: "Four months of focus", description: "Build a consistent study routine for the term ahead." },
  { slug: "8-months", months: 8, price: 7600, title: "Eight months of progress", description: "Give yourself more time to learn, practise and prepare." },
] as const;
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
