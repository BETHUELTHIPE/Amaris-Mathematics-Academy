import type { Metadata } from "next";
import { ConnectionRecovery } from "@/components/site/connection-recovery";
import { DashboardRealUserVitals } from "@/components/site/dashboard-real-user-vitals";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Amaris Mathematics Academy", template: "%s | Amaris Mathematics Academy" },
  description: "Structured online mathematics courses for South African school, TVET and university students.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-ZA">
      <head>
        <script src="/header-navigation.js" defer />
      </head>
      <body className="antialiased">
        {children}
        <ConnectionRecovery />
        <DashboardRealUserVitals />
      </body>
    </html>
  );
}
