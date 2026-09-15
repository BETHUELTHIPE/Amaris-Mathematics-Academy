import type { Metadata } from "next";
import { ConnectionRecovery } from "@/components/site/connection-recovery";
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
      <body className="antialiased">{children}<ConnectionRecovery /></body>
    </html>
  );
}
