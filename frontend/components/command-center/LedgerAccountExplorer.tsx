'use client';

import React from 'react';
import { Wallet, BookOpen, Lock, CheckCircle2 } from 'lucide-react';
import { Account, Transaction } from '@/types/api';
import { formatMoney } from '@/lib/format-money';
import { useDemoGuide } from '@/components/layout/DemoGuideContext';

interface LedgerAccountExplorerProps {
  accounts: Account[];
  transactions: Transaction[];
}

export function LedgerAccountExplorer({
  accounts,
  transactions,
}: LedgerAccountExplorerProps) {
  const { demoGuide } = useDemoGuide();

  return (
    <section className="space-y-4">
      {demoGuide && (
        <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-xs">
          <span className="font-mono font-bold text-indigo-300 bg-indigo-500/20 px-2 py-0.5 rounded">
            Step 4: Inspect Ledger
          </span>
          <span className="text-slate-300">
            Verify updated account balances and immutable debit/credit/fee journal rows.
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Left: Accounts Panel (4 cols) */}
      <div className="lg:col-span-4 bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden flex flex-col">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <Wallet className="w-4 h-4 text-indigo-400" />
              Accounts Panel
            </h2>
            <p className="text-[11px] text-slate-400 mt-0.5">
              User, Merchant &amp; Fee accounts
            </p>
          </div>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            {accounts.length} total
          </span>
        </div>

        <div className="divide-y divide-slate-800/80 overflow-y-auto max-h-[380px]">
          {accounts.map((acc) => {
            const isFrozen = acc.status !== 'ACTIVE';
            return (
              <div
                key={acc.id}
                className="p-3.5 hover:bg-slate-800/40 transition flex items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-white truncate">
                      {acc.label}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                        isFrozen
                          ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                          : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                      }`}
                    >
                      {isFrozen ? <Lock className="w-2.5 h-2.5" /> : <CheckCircle2 className="w-2.5 h-2.5" />}
                      {acc.status}
                    </span>
                  </div>
                  <p className="text-[11px] font-mono text-slate-500 truncate mt-0.5">
                    {acc.account_number} · {acc.account_type}
                  </p>
                </div>

                <div className="text-right flex-shrink-0">
                  <p className="text-sm font-mono font-bold text-white">
                    {formatMoney(acc.balance, acc.currency)}
                  </p>
                  <p className="text-[10px] font-mono text-slate-500">{acc.currency}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right: Double-Entry Journal Table (8 cols) */}
      <div className="lg:col-span-8 bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden flex flex-col">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-emerald-400" />
              Double-Entry Journal Table
            </h2>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Immutable debit, credit &amp; fee postings with correlation IDs
            </p>
          </div>
          <span className="text-[11px] font-mono text-emerald-400">
            ∑ = 0.00 Enforced
          </span>
        </div>

        <div className="overflow-x-auto max-h-[380px]">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/80 border-b border-slate-800 text-[11px] uppercase font-semibold text-slate-400 sticky top-0">
              <tr>
                <th className="p-3">Transfer ID</th>
                <th className="p-3">Debit Entry</th>
                <th className="p-3">Credit Entry</th>
                <th className="p-3">Fee Entry</th>
                <th className="p-3">Correlation ID</th>
                <th className="p-3 text-right">State</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 font-mono">
              {transactions.slice(0, 12).map((tx) => {
                const amt = parseFloat(tx.amount) || 0;
                const fee = parseFloat(tx.fee_amount) || 0;
                const netCredit = Math.max(0, amt - fee);
                const corrId = tx.idempotency_key.slice(0, 14);
                return (
                  <tr key={tx.id} className="hover:bg-slate-800/40 transition">
                    <td className="p-3 text-slate-200 font-semibold">
                      {tx.id.slice(0, 14)}
                    </td>
                    <td className="p-3 text-rose-400">
                      -{formatMoney(amt.toFixed(2), tx.currency)}
                    </td>
                    <td className="p-3 text-emerald-400">
                      +{formatMoney(netCredit.toFixed(2), tx.currency)}
                    </td>
                    <td className="p-3 text-amber-400">
                      +{formatMoney(fee.toFixed(2), tx.currency)}
                    </td>
                    <td className="p-3 text-slate-400 text-[11px]">{corrId}</td>
                    <td className="p-3 text-right">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                        PENDING → {tx.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      </div>
    </section>
  );
}
