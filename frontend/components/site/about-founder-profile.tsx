import { Code2, GraduationCap, BriefcaseBusiness } from "lucide-react";

const qualifications = [
  {
    title: "BSc Mathematics & Applied Mathematics",
    institution: "University of South Africa (UNISA)",
    dates: "Completed November 2019",
    description: "A foundation in Mathematics and Applied Mathematics.",
  },
  {
    title: "Data Engineering Course",
    institution: "EXPLOREAI Academy, South Africa",
    dates: "16 January – 30 July 2023",
    description: "Professional training in data engineering, Python, SQL and ETL workflows.",
  },
  {
    title: "BSc Physics",
    institution: "University of Pretoria",
    dates: "2007 · Partially completed",
    description: "University-level Physics studies; the degree was not completed.",
  },
];

const experience = [
  {
    role: "Founder, Managing Director & Head Tutor",
    organisation: "Amaris Mathematics Academy",
    period: "Current",
    detail: "Leads the academic vision and technology development of the tutoring platform.",
  },
  {
    role: "Software Engineer & Cloud Solutions Developer",
    organisation: "Independent practice",
    period: "2025 – present",
    detail: "Python and Django development, PostgreSQL, container deployments and automation.",
  },
  {
    role: "Django Developer",
    organisation: "Audrin Software Solutions",
    period: "Professional experience",
    detail: "Backend application development and software delivery.",
  },
  {
    role: "Data Engineer Intern",
    organisation: "EXPLOREAI",
    period: "August – December 2023",
    detail: "Worked with Python, SQL, ETL, Apache Spark and data engineering projects.",
  },
  {
    role: "Mathematics, Physical Sciences & Mathematical Literacy Lecturer",
    organisation: "Department of Higher Education and Training",
    period: "2008 – 2025",
    detail: "Grade 12 teaching, learning materials, learner support and assessment.",
  },
  {
    role: "Evaluator, Subject Specialist & Team Leader",
    organisation: "Umalusi Quality Council",
    period: "Part-time, from 2014",
    detail: "Academic quality assurance, moderation and subject evaluation.",
  },
  {
    role: "Physics Tutor & Mentor",
    organisation: "University of Pretoria",
    period: "2005 – 2007",
    detail: "Physics tutoring and student mentoring.",
  },
];

const stack = [
  { title: "Frontend", tools: ["Next.js", "React", "TypeScript", "Tailwind CSS", "shadcn/ui"] },
  { title: "Backend & APIs", tools: ["Python", "Django", "Django REST Framework", "Django Channels", "Gunicorn"] },
  { title: "Database & secure files", tools: ["PostgreSQL", "Supabase", "pgvector", "Private storage", "Signed URLs"] },
  { title: "Live cloud & deployment", tools: ["Render", "Docker", "Docker Compose", "Nginx", "GitHub Actions"] },
  { title: "Redis & background processing", tools: ["Redis / Valkey broker", "Celery", "Celery Beat", "Asynchronous notifications", "Scheduled tasks"] },
  { title: "Payments & integrations", tools: ["PayFast", "Zoom", "Google OAuth"] },
  { title: "AI, monitoring & quality", tools: ["LangChain", "KaTeX", "Prometheus", "Grafana", "Flower", "Lighthouse", "Locust / k6"] },
  { title: "AWS architecture & cloud engineering experience", tools: ["Amazon S3", "Amazon ECS Fargate", "Amazon RDS PostgreSQL", "Amazon CloudFront", "AWS CloudFormation", "Amazon CloudWatch", "Amazon SNS", "AWS IAM", "AWS Secrets Manager"] },
];

export function FounderProfile() {
  return (
    <>
      <section id="founder-qualifications" aria-labelledby="founder-qualifications-title" className="bg-white py-20 lg:py-24">
        <div className="mx-auto max-w-7xl px-5 lg:px-8">
          <p className="eyebrow">Education & professional training</p>
          <h2 id="founder-qualifications-title" className="mt-4 max-w-3xl text-3xl font-semibold tracking-[-.04em] text-[#07152d] sm:text-4xl">
            A foundation in Mathematics, Physics and data engineering
          </h2>
          <p className="mt-4 max-w-3xl leading-7 text-[#60708a]">
            Our founder brings together formal Mathematics studies, data engineering training and practical classroom experience.
          </p>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {qualifications.map(({ title, institution, dates, description }) => (
              <article key={title} className="rounded-3xl border border-[#dce4ef] bg-[#f5f7fb] p-6 sm:p-7">
                <GraduationCap aria-hidden="true" className="size-7 text-[#1f5bbd]" />
                <p className="mt-6 text-xs font-bold uppercase tracking-[.12em] text-[#1f5bbd]">{dates}</p>
                <h3 className="mt-3 text-xl font-semibold text-[#07152d]">{title}</h3>
                <p className="mt-2 font-medium text-[#344765]">{institution}</p>
                <p className="mt-4 text-sm leading-7 text-[#60708a]">{description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="founder-experience" aria-labelledby="founder-experience-title" className="bg-[#f5f7fb] py-20 lg:py-24">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 lg:grid-cols-[.75fr_1.25fr] lg:px-8">
          <div>
            <BriefcaseBusiness aria-hidden="true" className="size-8 text-[#1f5bbd]" />
            <p className="eyebrow mt-6">Professional experience</p>
            <h2 id="founder-experience-title" className="mt-4 text-3xl font-semibold tracking-[-.04em] text-[#07152d] sm:text-4xl">
              Teaching, technology and leadership
            </h2>
            <p className="mt-5 leading-8 text-[#60708a]">
              Bethuel has worked across Mathematics education, software engineering and data engineering, with additional
              professional experience in fire detection system inspection, testing and commissioning.
            </p>
          </div>
          <ol className="grid gap-4 sm:grid-cols-2">
            {experience.map(({ role, organisation, period, detail }) => (
              <li key={role} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
                <p className="text-xs font-bold uppercase tracking-[.12em] text-[#1f5bbd]">{period}</p>
                <h3 className="mt-3 text-lg font-semibold leading-snug text-[#07152d]">{role}</h3>
                <p className="mt-2 text-sm font-semibold text-[#344765]">{organisation}</p>
                <p className="mt-3 text-sm leading-7 text-[#60708a]">{detail}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="academy-technology" aria-labelledby="academy-technology-title" className="bg-[#07152d] py-20 text-white lg:py-24">
        <div className="mx-auto max-w-7xl px-5 lg:px-8">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Behind the platform</p>
          <h2 id="academy-technology-title" className="mt-4 max-w-3xl text-3xl font-semibold tracking-[-.04em] sm:text-4xl">
            Technology used to build Amaris Mathematics Academy
          </h2>
          <p className="mt-5 max-w-3xl leading-8 text-white/70">
            Amaris runs on Render and Supabase, with Redis/Valkey supporting its Celery background-task architecture.
            Bethuel has also designed AWS cloud architectures using the services listed below; AWS is not presented as
            the live hosting environment for Amaris. Some AI and workflow integrations are still in development or staging verification.
          </p>
          <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {stack.map(({ title, tools }) => (
              <article key={title} className="rounded-3xl border border-white/15 bg-white/5 p-6 sm:p-7">
                <Code2 aria-hidden="true" className="size-7 text-[#ffcc66]" />
                <h3 className="mt-5 text-xl font-semibold">{title}</h3>
                <ul className="mt-5 flex flex-wrap gap-2">
                  {tools.map((tool) => (
                    <li key={tool} className="rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-sm font-medium text-white/85">
                      {tool}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
          <p className="mt-7 text-sm leading-7 text-white/60">
            Platform safeguards include role-based access, private file delivery and separate staging and production environments.
          </p>
        </div>
      </section>
    </>
  );
}
