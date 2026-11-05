/** Public qualification structure, acknowledged to SAQA; checked 20 October 2026. */
export const aiQualification = {
  title: "Occupational Certificate: Artificial Intelligence Software Developer",
  saqaId: "118792",
  curriculumCode: "251201-002-00-00",
  level: 5,
  credits: 209,
  checked: "20 October 2026",
  sources: {
    saqa: "https://regqs.saqa.org.za/showQualification.php?id=118792",
    qcto: "https://www.qcto.org.za/full---part-registered-qualifications.html",
  },
} as const;

type CurriculumModule = { code: string; title: string; level: number; credits: number };
type CurriculumGroup = {
  id: string;
  title: string;
  subtitle: string;
  credits: number;
  modules: CurriculumModule[];
};

export const aiCurriculum: CurriculumGroup[] = [
  {
    id: "knowledge", title: "Knowledge modules", subtitle: "Understand the ideas behind intelligent software.", credits: 86,
    modules: [
      { code: "251201-002-00-KM-01", title: "Overview of Artificial Intelligence", level: 4, credits: 2 },
      { code: "251201-002-00-KM-02", title: "Introduction to Mathematics and Statistics", level: 4, credits: 10 },
      { code: "251201-002-00-KM-03", title: "Analytical Thinking and Problem Solving", level: 4, credits: 3 },
      { code: "251201-002-00-KM-04", title: "Data, Databases and Data Visualisation", level: 4, credits: 8 },
      { code: "251201-002-00-KM-05", title: "Computing Theory", level: 4, credits: 8 },
      { code: "251201-002-00-KM-06", title: "Introduction to Artificial Intelligence, Machine Learning, Deep Learning", level: 4, credits: 5 },
      { code: "251201-002-00-KM-07", title: "Artificial Intelligence", level: 5, credits: 12 },
      { code: "251201-002-00-KM-08", title: "Machine Learning", level: 5, credits: 16 },
      { code: "251201-002-00-KM-09", title: "Deep Learning", level: 5, credits: 16 },
      { code: "251201-002-00-KM-10", title: "Introduction to Governance, Legislation and Ethics", level: 4, credits: 1 },
      { code: "251201-002-00-KM-11", title: "Fundamentals of Design Thinking and Innovation", level: 4, credits: 1 },
      { code: "251201-002-00-KM-12", title: "4IR and Future Skills", level: 4, credits: 4 },
    ],
  },
  {
    id: "practical", title: "Practical skills modules", subtitle: "Turn understanding into working AI solutions.", credits: 63,
    modules: [
      { code: "251201-002-00-PM-01", title: "Mathematics and Statistics for Programming", level: 4, credits: 8 },
      { code: "251201-002-00-PM-02", title: "Problem Definition, Analytical Thinking and Decision-Making", level: 4, credits: 2 },
      { code: "251201-002-00-PM-03", title: "Access, Analyse and Visualise Structured Data Using Spreadsheets", level: 4, credits: 4 },
      { code: "251201-002-00-PM-04", title: "Use SQL to Communicate with a Database", level: 5, credits: 4 },
      { code: "251201-002-00-PM-05", title: "Build a simple AI solution using Python", level: 5, credits: 8 },
      { code: "251201-002-00-PM-06", title: "Use Python Data Scraping to Populate Database Table in SQL", level: 5, credits: 4 },
      { code: "251201-002-00-PM-07", title: "Use Machine Learning to Build an AI solution in Python", level: 5, credits: 6 },
      { code: "251201-002-00-PM-08", title: "Use Deep Learning to Build an AI Neural Network Architecture in Python", level: 5, credits: 10 },
      { code: "251201-002-00-PM-09", title: "Use Deep Learning to Build an AI Neural Network Architecture in TensorFlow", level: 5, credits: 10 },
      { code: "251201-002-00-PM-10", title: "Function Ethically and Effectively as a Member of a Multidisciplinary Team", level: 4, credits: 3 },
      { code: "251201-002-00-PM-11", title: "Participate in a Design Thinking for Innovation Workshop", level: 4, credits: 4 },
    ],
  },
  {
    id: "workplace", title: "Work experience modules", subtitle: "Apply, test and improve AI in a workplace context.", credits: 60,
    modules: [
      { code: "251201-002-00-WM-01", title: "AI Solution Design Interpretation and Development", level: 5, credits: 20 },
      { code: "251201-002-00-WM-02", title: "AI Solution Performance Testing", level: 5, credits: 20 },
      { code: "251201-002-00-WM-03", title: "AI Solution Deployment, Modification and Improvement", level: 5, credits: 20 },
    ],
  },
];
