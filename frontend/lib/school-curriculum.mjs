/** Booking chapter guides, paraphrased from DBE CAPS. See docs/school-booking-curriculum.md. */
export const SCHOOL_GRADES = ["Grade 7", "Grade 8", "Grade 9", "Grade 10", "Grade 11", "Grade 12"];
export const CUSTOM_CHOICE = "__custom__";

/** @type {Record<string, {title: string, chapters: string[]}[]>} */
const mathematics = {
  "Grade 7": [
    { title: "Numbers and operations", chapters: ["Whole-number calculations", "Integers", "Powers and roots", "Common fractions", "Decimals and percentages", "Ratios, rates and financial problems"] },
    { title: "Patterns and algebra", chapters: ["Number and shape patterns", "Input-output relationships", "Algebraic expressions", "Number sentences and equations", "Interpreting and drawing graphs"] },
    { title: "Geometry and measurement", chapters: ["Geometric constructions", "Lines, angles and 2D shapes", "3D objects", "Transformations", "Area and perimeter", "Volume and surface area"] },
    { title: "Data and chance", chapters: ["Collecting, displaying and summarising data", "Probability"] },
  ],
  "Grade 8": [
    { title: "Numbers and operations", chapters: ["Whole numbers, ratios and rates", "Integer calculations", "Exponents and scientific notation", "Fractions, decimals and percentages", "Financial calculations"] },
    { title: "Patterns and algebra", chapters: ["Numeric and geometric patterns", "Functions and relationships", "Expanding and simplifying expressions", "Linear equations", "Graphs and coordinates"] },
    { title: "Geometry and measurement", chapters: ["Constructions and angle relationships", "Triangles and quadrilaterals", "Pythagoras' theorem", "Transformations on the coordinate plane", "3D geometry", "Perimeter and area, including circles", "Volume and surface area of prisms"] },
    { title: "Data and chance", chapters: ["Data collection and statistical summaries", "Graphs, interpretation and bias", "Probability and outcomes"] },
  ],
  "Grade 9": [
    { title: "Numbers and operations", chapters: ["Real numbers and financial contexts", "Integers, fractions and decimals", "Exponent laws and scientific notation"] },
    { title: "Patterns and algebra", chapters: ["Sequences and pattern rules", "Functions and relationships", "Algebraic expansion and factorisation", "Simplifying algebraic fractions", "Equations and problem solving", "Straight-line graphs"] },
    { title: "Geometry and measurement", chapters: ["Constructions and geometric reasoning", "Triangle and quadrilateral properties", "Congruence and similarity", "Pythagoras' theorem and applications", "Transformations and scale factors", "3D objects", "Perimeter and area", "Surface area, volume and cylinders"] },
    { title: "Data and chance", chapters: ["Comparing and interpreting data sets", "Statistical graphs and summaries", "Probability in context"] },
  ],
  "Grade 10": [
    { title: "Algebra and functions", chapters: ["Algebraic expressions and factorisation", "Exponents and number systems", "Equations and inequalities", "Linear number patterns", "Linear, quadratic, hyperbolic and exponential functions"] },
    { title: "Geometry and trigonometry", chapters: ["Trigonometric ratios and 2D problems", "Trigonometric graphs", "Coordinate geometry: distance, midpoint and gradient", "Euclidean geometry: triangles and quadrilaterals", "Measurement of 3D solids"] },
    { title: "Finance, statistics and probability", chapters: ["Simple and compound growth", "Statistics and data displays", "Probability, Venn diagrams and sample spaces"] },
  ],
  "Grade 11": [
    { title: "Algebra and functions", chapters: ["Rational exponents and surds", "Quadratic equations and inequalities", "Quadratic number patterns", "Function graphs and transformations"] },
    { title: "Geometry and trigonometry", chapters: ["Trig identities, reduction and equations", "Trigonometric graphs and transformations", "Sine rule, cosine rule and triangle area", "Coordinate geometry and line inclination", "Circle geometry, tangents and proofs", "Measurement and composite solids"] },
    { title: "Finance, statistics and probability", chapters: ["Compound growth and depreciation", "Statistics: spread, variance and standard deviation", "Probability: dependent and independent events"] },
  ],
  "Grade 12": [
    { title: "Algebra and functions", chapters: ["Sequences and series", "Inverse functions and logarithms", "Function graphs and interpretation", "Algebra, equations and inequalities revision"] },
    { title: "Calculus", chapters: ["Limits and differentiation from first principles", "Differentiation rules", "Cubic graphs and rates of change", "Optimisation problems"] },
    { title: "Geometry and trigonometry", chapters: ["Compound-angle and double-angle identities", "Trigonometric equations and applications", "Coordinate geometry: circles and tangents", "Euclidean geometry: proportionality and similarity"] },
    { title: "Finance, statistics and probability", chapters: ["Annuities, investments and loan repayments", "Regression and correlation", "Counting principles and probability"] },
  ],
};

/** @type {Record<string, {title: string, chapters: string[]}[]>} */
const literacy = {
  "Grade 10": [
    { title: "Practical foundations", chapters: ["Numbers, units, percentages and ratios in context", "Tables, relationships and graphs"] },
    { title: "Applications", chapters: ["Financial documents and household budgets", "Income, expenditure and tariffs", "Measurement and unit conversions", "Perimeter, area and volume in context", "Maps, scale and floor plans", "Collecting and representing data", "Chance and everyday probability"] },
  ],
  "Grade 11": [
    { title: "Practical foundations", chapters: ["Contextual calculations and relationships", "Comparing graphs and break-even points"] },
    { title: "Applications", chapters: ["Tariffs, budgets and financial statements", "Interest, banking, loans and inflation", "Tax and deductions", "Measurement, time and conversions", "Scale, plans and models", "Statistical summaries and data interpretation", "Probability in everyday contexts"] },
  ],
  "Grade 12": [
    { title: "Practical foundations", chapters: ["Integrated calculations, tables and graphs", "Comparing costs and break-even analysis"] },
    { title: "Applications", chapters: ["Personal income tax and financial documents", "Banking, credit, investments and inflation", "Exchange rates", "Measurement, packing and construction", "Maps, plans, models and travel schedules", "Data analysis, graphs and critical interpretation", "Probability, risk and misleading claims"] },
  ],
};

/** @param {string} programme */
export function isSchoolProgramme(programme) { return programme === "caps" || programme === "ieb"; }

/** @param {string} programme @param {string} subject @param {string} level */
export function getCurriculumTopics(programme, subject, level) {
  if (!isSchoolProgramme(programme)) return [];
  return (subject === "mathematics" ? mathematics : subject === "mathematical_literacy" ? literacy : {})[level] ?? [];
}

/** Native forms and multipart requests keep the existing backend field names. @param {FormData} form @param {boolean} [includeTopic] */
export function resolveCurriculumFields(form, includeTopic = true) {
  const read = (/** @type {string} */ key) => String(form.get(key) ?? "").trim();
  const programme = read("programme");
  const subject = read("subject");
  const level = read("level") === CUSTOM_CHOICE ? read("customLevel") : read("level");
  const topic = read("topic") === CUSTOM_CHOICE ? read("customTopic") : read("topic");
  if (!programme || !subject || !level || level.length > 80) throw new Error("Choose your programme, subject and grade or level.");
  if (isSchoolProgramme(programme) && subject === "mathematical_literacy" && ["Grade 7", "Grade 8", "Grade 9"].includes(level)) {
    throw new Error("Choose Mathematics for Grades 7–9. Mathematical Literacy is offered in Grades 10–12.");
  }
  if (includeTopic && (topic.length < 2 || topic.length > 180)) throw new Error("Choose a topic or enter your chapter, assignment or exam question (2–180 characters).");
  return { programme, subject, level, topic };
}
