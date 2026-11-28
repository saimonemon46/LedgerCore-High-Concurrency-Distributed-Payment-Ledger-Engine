'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart2,
  Wallet,
  ArrowRightLeft,
  PlusCircle,
  BookOpen,
  Scale,
  Key,
  Webhook,
  History,
  Users,
  Settings,
} from 'lucide-react';

const NAV_SECTIONS = [
  {
    title: 'Financial Core',
    items: [
      { href: '/console', label: 'Dashboard', icon: BarChart2 },
      { href: '/console/accounts', label: 'Accounts', icon: Wallet },
      { href: '/console/transfers', label: 'Transfers', icon: ArrowRightLeft },
      { href: '/console/transfers/new', label: 'New Transfer', icon: PlusCircle },
      { href: '/console/ledger', label: 'Ledger Explorer', icon: BookOpen },
      { href: '/console/reconciliation', label: 'Reconciliation', icon: Scale },
    ],
  },
  {
    title: 'Developer & Ops',
    items: [
      { href: '/console/api-keys', label: 'API Keys', icon: Key },
      { href: '/console/webhooks', label: 'Webhooks', icon: Webhook },
      { href: '/console/audit-log', label: 'Audit Trail', icon: History },
    ],
  },
  {
    title: 'Workspace',
    items: [
      { href: '/console/team', label: 'Team & RBAC', icon: Users },
      { href: '/console/settings', label: 'Settings', icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 bg-slate-900/70 border-r border-slate-800 hidden md:flex flex-col flex-shrink-0 min-h-[calc(100vh-4rem)]">
      <div className="p-4 space-y-6 flex-1">
        {NAV_SECTIONS.map((section, idx) => (
          <div key={idx}>
            <p className="px-3 text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
              {section.title}
            </p>
            <nav className="space-y-1">
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition ${
                      isActive
                        ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 font-semibold'
                        : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-100'
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-400' : 'text-slate-500'}`} />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        ))}
      </div>

      <div className="p-4 border-t border-slate-800 bg-slate-900/90 text-xs text-slate-400">
        <p className="font-semibold text-emerald-400">Financial Invariant Guard</p>
        <p className="mt-1 text-[11px] leading-snug text-slate-400">
          Ensures every debit equals credit + fee — zero money lost or created (৳0.00 drift).
        </p>
      </div>
    </aside>
  );
}
