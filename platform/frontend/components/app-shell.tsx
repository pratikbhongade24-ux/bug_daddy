import Link from "next/link";
import { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <div className="app-shell__ambient app-shell__ambient--one" />
      <div className="app-shell__ambient app-shell__ambient--two" />
      <header className="site-header">
        <Link className="site-header__brand" href="/">
          <span className="site-header__badge">Bug Daddy</span>
          <h1>Platform</h1>
        </Link>
        <nav className="site-nav">
          <Link href="/">Dashboard</Link>
        </nav>
      </header>
      <main className="site-main">{children}</main>
    </div>
  );
}
