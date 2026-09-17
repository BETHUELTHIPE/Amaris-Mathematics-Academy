import pa11y from "pa11y";

const urls = [
  "http://127.0.0.1:3000/",
  "http://127.0.0.1:3000/courses",
  "http://127.0.0.1:3000/contact",
  "http://127.0.0.1:3000/login",
  "http://127.0.0.1:3000/register",
];

let failed = false;
for (const url of urls) {
  try {
    const result = await pa11y(url, {
      standard: "WCAG2AA",
      timeout: 30_000,
      wait: 1_000,
      runners: ["axe", "htmlcs"],
      chromeLaunchConfig: {
        args: ["--no-sandbox", "--disable-dev-shm-usage"],
      },
    });
    const errors = result.issues.filter((issue) => issue.type === "error");
    if (errors.length) {
      failed = true;
      console.error(`Accessibility FAIL ${url}: ${errors.length} error(s)`);
      for (const issue of errors.slice(0, 20)) {
        const selector = issue.selector ? ` selector=${issue.selector}` : "";
        const context = issue.context ? ` context=${String(issue.context).replace(/\s+/g, " ").slice(0, 240)}` : "";
        console.error(`- ${issue.code}: ${issue.message}${selector}${context}`);
      }
    } else {
      console.log(`Accessibility PASS ${url}`);
    }
  } catch (error) {
    failed = true;
    console.error(`Accessibility technical failure ${url}:`, error);
  }
}

if (failed) process.exit(1);
