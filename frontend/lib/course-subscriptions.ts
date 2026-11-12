export type CourseSubscriptionPlan = {
  slug: "4-months" | "8-months";
  months: 4 | 8;
  title: string;
  description: string;
  focus: string;
};

export const courseSubscriptionPlans: readonly CourseSubscriptionPlan[] = [
  {
    slug: "4-months",
    months: 4,
    title: "Build your foundation",
    description: "A focused study period for a semester, revision goal or a fresh start in mathematics.",
    focus: "A focused learning goal",
  },
  {
    slug: "8-months",
    months: 8,
    title: "Keep your momentum",
    description: "A longer study period for steady practice, deeper understanding and ongoing revision.",
    focus: "A longer learning journey",
  },
];

export function getCourseSubscriptionPlan(slug: string) {
  return courseSubscriptionPlans.find((plan) => plan.slug === slug);
}

export function subscriptionRequestMessage(
  plan: CourseSubscriptionPlan,
  course: { title: string; curriculum: string; level: string },
) {
  return [
    `I would like to request a ${plan.months}-month course subscription.`,
    `Course: ${course.title}`,
    `Curriculum: ${course.curriculum}`,
    `Level: ${course.level}`,
    "",
    "Please confirm the total price in ZAR, included course content, access start and end dates, payment options and renewal terms before I pay.",
  ].join("\n");
}
