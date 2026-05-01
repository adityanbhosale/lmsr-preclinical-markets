'use client';

/**
 * Docs layout — Stripe/Vercel-style left sidebar with collapsible sections.
 *
 * Wraps every page under app/(docs)/* but doesn't affect the URL — the
 * parens make this a Next.js route group. So app/(docs)/page.mdx still
 * renders at /, app/(docs)/architecture/page.mdx renders at /architecture,
 * etc.
 *
 * The trade UI at /markets is a sibling route OUTSIDE this layout and
 * gets the default app/layout.tsx treatment (no docs chrome).
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

type NavItem = {
  title: string;
  href?: string;
  children?: NavItem[];
};

const NAV: NavItem[] = [
  { title: 'Overview', href: '/' },
  {
    title: 'Architecture',
    children: [
      { title: 'Overview', href: '/architecture' },
      { title: 'Regulatory Split', href: '/architecture/regulatory-split' },
      { title: 'Settlement Stack', href: '/architecture/settlement-stack' },
    ],
  },
  {
    title: 'Layer 1 — ERC-3643 SPV',
    children: [
      { title: 'Overview', href: '/layer-1' },
      { title: 'ERC-3643 / T-REX', href: '/layer-1/erc-3643' },
      { title: 'Milestone Tokens', href: '/layer-1/milestone-tokens' },
      { title: 'Deployment', href: '/layer-1/deployment' },
    ],
  },
  {
    title: 'Layer 2 — LS-LMSR AMM',
    children: [
      { title: 'Overview', href: '/layer-2' },
      { title: 'LS-LMSR', href: '/layer-2/ls-lmsr' },
      { title: 'ABMM Seeding', href: '/layer-2/abmm' },
      { title: 'Deployment', href: '/layer-2/deployment' },
    ],
  },
  {
    title: 'CCTP Bridge',
    children: [
      { title: 'Overview', href: '/cctp' },
      { title: 'Outbound — Sepolia → Base', href: '/cctp/outbound' },
      { title: 'Return — Base → Sepolia', href: '/cctp/return' },
    ],
  },
  {
    title: 'Mechanism Design',
    children: [
      { title: 'Overview', href: '/mechanism' },
      { title: 'Retreat Function', href: '/mechanism/retreat-function' },
      { title: 'Backtests', href: '/mechanism/backtests' },
    ],
  },
  { title: 'Deployment Coordinates', href: '/deployment' },
  { title: 'Roadmap', href: '/roadmap'}
];

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <Sidebar pathname={pathname} />
      <main className="flex-1 px-8 py-12 max-w-3xl mx-auto">
        <article className="prose prose-neutral max-w-none prose-headings:font-semibold prose-h1:text-3xl prose-h1:tracking-tight prose-h2:text-xl prose-h2:mt-12 prose-h2:mb-4 prose-h3:text-lg prose-h3:mt-8 prose-p:leading-relaxed prose-pre:bg-neutral-50 prose-pre:border prose-pre:border-neutral-200 prose-code:text-[0.85em] prose-code:font-mono prose-code:before:content-none prose-code:after:content-none prose-table:text-sm">
          {children}
        </article>
      </main>
    </div>
  );
}

function Sidebar({ pathname }: { pathname: string }) {
  return (
    <aside className="w-72 shrink-0 border-r border-neutral-200 px-6 py-10 sticky top-0 h-screen overflow-y-auto">
      <Link href="/" className="block mb-8">
        <div className="text-sm font-semibold tracking-tight">
          Dual-Layer Biotech Liquidity
        </div>
        <div className="text-xs text-neutral-500 mt-0.5">
          ERC-3643 SPV × LS-LMSR
        </div>
      </Link>

      <nav className="space-y-1">
        {NAV.map((item) => (
          <NavSection key={item.title} item={item} pathname={pathname} />
        ))}
      </nav>

      <div className="mt-10 pt-6 border-t border-neutral-200">
        <Link
          href="/markets"
          className="block text-sm font-medium text-neutral-700 hover:text-black transition-colors"
        >
          Live Markets ↗
        </Link>
        <a
          href="https://github.com/adityanbhosale/lmsr-preclinical-markets"
          target="_blank"
          rel="noopener noreferrer"
          className="block text-sm text-neutral-500 hover:text-black transition-colors mt-2"
        >
          GitHub ↗
        </a>
      </div>
    </aside>
  );
}

function NavSection({ item, pathname }: { item: NavItem; pathname: string }) {
  const hasChildren = item.children && item.children.length > 0;

  // Auto-expand sections containing the current page.
  const containsActive =
    hasChildren && item.children!.some((c) => c.href === pathname);
  const [expanded, setExpanded] = useState(containsActive);

  if (!hasChildren) {
    const isActive = pathname === item.href;
    return (
      <Link
        href={item.href!}
        className={`block py-1.5 px-2 text-sm rounded transition-colors ${
          isActive
            ? 'bg-neutral-100 text-black font-medium'
            : 'text-neutral-600 hover:text-black hover:bg-neutral-50'
        }`}
      >
        {item.title}
      </Link>
    );
  }

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between py-1.5 px-2 text-sm font-medium text-neutral-700 hover:text-black hover:bg-neutral-50 rounded transition-colors"
      >
        <span>{item.title}</span>
        <span
          className={`text-xs text-neutral-400 transition-transform ${
            expanded ? 'rotate-90' : ''
          }`}
        >
          ›
        </span>
      </button>
      {expanded && (
        <div className="ml-3 mt-1 mb-2 border-l border-neutral-200 pl-3 space-y-0.5">
          {item.children!.map((child) => {
            const isActive = pathname === child.href;
            return (
              <Link
                key={child.href}
                href={child.href!}
                className={`block py-1 px-2 text-sm rounded transition-colors ${
                  isActive
                    ? 'bg-neutral-100 text-black font-medium'
                    : 'text-neutral-500 hover:text-black hover:bg-neutral-50'
                }`}
              >
                {child.title}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
