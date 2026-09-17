import type { Metadata } from "next";
import { ConnectionRecovery } from "@/components/site/connection-recovery";
import globalStyles from "./globals.css?inline";

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
        {/*
          Keep the complete generated stylesheet in the initial document.
          The CSS is small once compressed, and inlining removes the extra
          render-blocking stylesheet round trip that Lighthouse measured at
          roughly 470 ms on the public pages.
        */}
        <style id="amaris-global-styles" dangerouslySetInnerHTML={{ __html: globalStyles }} />
      </head>
      <body className="antialiased">
        {children}
        <ConnectionRecovery />
      </body>
    </html>
  );
}
