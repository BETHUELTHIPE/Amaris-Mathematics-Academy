# Grouped public navigation

The public header uses a compact desktop row and a mobile accordion with the same destinations:

- **Learn:** courses, how it works, pricing, live-class booking.
- **Matric Upgrades:** a prominent direct link, with an adult-learning feature card on mobile.
- **Resources:** announcements, topic-video requests, and additional CMS-managed links.
- **Academy:** about, tutor recruitment, contact, tutor portal.

CMS labels, destinations and new-tab settings are preserved. Account controls continue to be rendered on the server for anonymous, unverified and verified students. All public page navigation remains full-page anchors.

Native details/summary disclosures work without JavaScript. A small client enhancement closes menus on outside pointer interaction, Escape, and a desktop/mobile breakpoint change. Escape returns keyboard focus to the disclosure. Desktop menus close when focus moves away; mobile sections use native accordion grouping so touch targets do not move during activation.

Animations use a brief fade/slide and chevron rotation, disabled for reduced-motion users. Mobile menus scroll within the remaining viewport height. Footer navigation links also have a minimum 24px target height, addressing the mobile application-receipt accessibility check. No backend, authentication or payment changes.

Verification: TypeScript, focused ESLint, navigation and tutor portal contracts, grouping tests (including custom CMS links), Render/Nitro production build, and Chromium checks for desktop and mobile menu operation, keyboard controls, native navigation, responsive geometry, reduced motion and WCAG accessibility.
