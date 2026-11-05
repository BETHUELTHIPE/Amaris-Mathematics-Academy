/** The public, shareable address for Amaris's support page.
 * Keep this independent of browser location, which may be a staging URL or
 * contain private query parameters. Safe in React Server and Client Components.
 */
export const PUBLIC_SUPPORT_URL =
  "https://amaris-mathematics-academy-live-students.onrender.com/support-our-project";

export const SUPPORT_SHARE_TITLE = "Support Our Project | Amaris Mathematics Academy";
export const SUPPORT_SHARE_MESSAGE =
  "Help Amaris Mathematics Academy reach more South African learners. Explore ways to sponsor a learner or support the education project.";

export const SUPPORT_WHATSAPP_URL =
  "https://wa.me/?text=" + encodeURIComponent(SUPPORT_SHARE_MESSAGE + " " + PUBLIC_SUPPORT_URL);
