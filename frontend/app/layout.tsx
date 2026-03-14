import "./globals.css";
import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClawFlow",
  description: "Natural-language automation intake for the OpenClaw ecosystem"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main className="app-shell">
          <header className="site-header">
            <div>
              <p className="eyebrow">OpenClaw User Entry</p>
              <h1 style={{ margin: "4px 0 0 0" }}>ClawFlow</h1>
            </div>
            <nav className="site-nav">
              <Link href="/">Run Request</Link>
              <Link href="/console">Console</Link>
              <Link href="/operations">Operations</Link>
              <Link href="/runs">Run Audit</Link>
              <Link href="/workflows">Workflow Lab</Link>
            </nav>
          </header>
          {children}
        </main>
      </body>
    </html>
  );
}
