import type { Metadata } from "next";
import { DeferredConnectionRecovery } from "@/components/site/deferred-connection-recovery";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Amaris Mathematics Academy", template: "%s | Amaris Mathematics Academy" },
  description: "Structured online mathematics courses for South African school, TVET and university students.",
  icons: {
    icon: "/brand/amaris-academy-icon-192.png",
    shortcut: "/brand/amaris-academy-icon-192.png",
    apple: "/brand/amaris-academy-icon-192.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-ZA">
      <body className="antialiased">
        {children}
        <DeferredConnectionRecovery />
      </body>
    </html>
  );
}
