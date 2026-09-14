export type Course = {
  slug: string;
  title: string;
  level: string;
  curriculum: string;
  price: number;
  lessons: number;
  hours: number;
  description: string;
  outcomes: string[];
  modules: string[];
  featured?: boolean;
};

export const courses: Course[] = [
  {
    slug: "caps-grade-12-mathematics",
    title: "CAPS Grade 12 Mathematics",
    level: "Grade 12",
    curriculum: "CAPS",
    price: 950,
    lessons: 42,
    hours: 28,
    description: "A focused matric programme covering algebra, functions, calculus, geometry and exam technique.",
    outcomes: ["Solve exam-standard problems confidently", "Interpret functions and graphs", "Build a reliable revision routine"],
    modules: ["Algebra & equations", "Functions & graphs", "Differential calculus", "Analytical geometry", "Euclidean geometry", "Probability"],
    featured: true,
  },
  {
    slug: "mathematical-literacy-grade-12",
    title: "Mathematical Literacy Grade 12",
    level: "Grade 12",
    curriculum: "CAPS",
    price: 750,
    lessons: 34,
    hours: 22,
    description: "Practical, visual lessons for finance, measurement, maps, data handling and examination readiness.",
    outcomes: ["Use mathematics in real contexts", "Read tables and graphs accurately", "Answer multi-step exam questions"],
    modules: ["Finance", "Measurement", "Maps & scale", "Data handling", "Probability", "Exam practice"],
    featured: true,
  },
  {
    slug: "tvet-engineering-mathematics-n4",
    title: "Engineering Mathematics N4",
    level: "TVET N4",
    curriculum: "NATED",
    price: 850,
    lessons: 38,
    hours: 25,
    description: "A structured N4 pathway from algebra and trigonometry to complex numbers and introductory calculus.",
    outcomes: ["Manipulate engineering formulae", "Apply trigonometric methods", "Prepare for NATED assessments"],
    modules: ["Algebra", "Trigonometry", "Complex numbers", "Functions", "Differentiation", "Integration"],
    featured: true,
  },
  {
    slug: "university-calculus-foundations",
    title: "University Calculus Foundations",
    level: "University",
    curriculum: "Higher Education",
    price: 1200,
    lessons: 46,
    hours: 32,
    description: "Build the conceptual and procedural foundation needed for first-year limits, derivatives and integrals.",
    outcomes: ["Reason with limits", "Differentiate common functions", "Model change with integrals"],
    modules: ["Functions review", "Limits", "Continuity", "Derivatives", "Applications", "Integrals"],
  },
  {
    slug: "linear-algebra-essentials",
    title: "Linear Algebra Essentials",
    level: "University",
    curriculum: "Higher Education",
    price: 1100,
    lessons: 36,
    hours: 24,
    description: "A clear visual route through vectors, matrices, systems, transformations and eigenvalues.",
    outcomes: ["Solve linear systems", "Understand matrix transformations", "Work with eigenvalues and eigenvectors"],
    modules: ["Vectors", "Matrices", "Linear systems", "Vector spaces", "Transformations", "Eigenvalues"],
  },
  {
    slug: "algebra-recovery-programme",
    title: "Algebra Recovery Programme",
    level: "Grades 9–11",
    curriculum: "CAPS / IEB",
    price: 450,
    lessons: 24,
    hours: 14,
    description: "Repair the algebra gaps that block progress in senior mathematics, with short lessons and deliberate practice.",
    outcomes: ["Simplify expressions accurately", "Solve equations step by step", "Work confidently with exponents"],
    modules: ["Number skills", "Expressions", "Equations", "Exponents", "Factorisation", "Word problems"],
  },
];

export function getCourse(slug: string) {
  return courses.find((course) => course.slug === slug);
}

export const formatRand = (value: number) =>
  new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR", maximumFractionDigits: 0 }).format(value);
