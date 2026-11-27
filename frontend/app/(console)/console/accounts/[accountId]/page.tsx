'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, Wallet, ShieldCheck, CheckCircle2, History } from 'lucide-react';
import { api } from '@/lib/api';
import { Account, LedgerEntry } from '@/types/api';
import { formatMoney, formatPostingAmount } from '@/lib/format-money';
import { StatusBadge } from '@/components/ui/StatusBadge';

export default function AccountDetailPage() {
  const params = useParams();
  const accountId = params?.accountId as string;

  const [account, setAccount] = useState<Account | null>(null);
  const [postings, setPostings] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadAccount() {
      const [acc, allEntries] = await Promise.all([
        api.getAccount(accountId),
        api.getLedgerEntries(),
      ]);
      setAccount(acc);
      if (acc) {
        setPostings(allEntries.filter((e) => e.account_id === acc.id || e.account_id === acc.account_number));
      }
      setLoading(false);
    }
    loadAccount();
  }, [accountId]);

  if (loading) {
    return <div className="p-8 text-center text-sm text-slate-500">Loading account statement...</div>;
  }

  if (!account) {
    return (
      <div className="bg-white p-8 rounded-xl border border-slate-200 text-center space-y-3">
        <p className="text-slate-600 font-semibold">Account not found</p>
        <Link href="/console/accounts" className="text-xs text-indigo-600 hover:underline">
          Return to accounts directory
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back Link & Header */}
      <div>
        <Link
          href="/console/accounts"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition mb-3"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Accounts
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold font-mono text-slate-900">{account.account_number}</h1>
              <StatusBadge status={account.status} />
            </div>
            <p className="text-slate-500 text-sm mt-0.5">{account.label} • {account.account_type}</p>
          </div>
          <div className="text-right">
            <span className="text-xs uppercase font-semibold text-slate-400">Current Balance</span>
            <div className="text-3xl font-extrabold font-mono text-slate-900">
              {formatMoney(account.balance, account.currency)}
            </div>
          </div>
        </div>
      </div>

      {/* Ledger Postings / Statement Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-600" />
            <div>
              <h2 className="font-bold text-slate-900 text-base">Immutable Ledger Statement</h2>
              <p className="text-xs text-slate-500">Every journal leg posted to this account</p>
            </div>
          </div>
          <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5" /> Reconciled with Balance
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-semibold text-slate-500">
              <tr>
                <th className="p-4">Seq #</th>
                <th className="p-4">Transaction ID</th>
                <th className="p-4">Entry Leg</th>
                <th className="p-4">Timestamp (UTC)</th>
                <th className="p-4 text-right">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono text-xs">
              {postings.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-slate-400 font-sans">
                    No postings recorded for this account yet.
                  </td>
                </tr>
              ) : (
                postings.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50/70 transition">
                    <td className="p-4 text-slate-400">#{p.sequence_id}</td>
                    <td className="p-4 font-bold text-slate-900 font-mono">
                      <Link href={`/console/transfers/${p.transaction_id}`} className="text-indigo-600 hover:underline">
                        {p.transaction_id}
                      </Link>
                    </td>
                    <td className="p-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        p.entry_type === 'DEBIT' ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'
                      }`}>
                        {p.entry_type}
                      </span>
                    </td>
                    <td className="p-4 text-slate-500 font-sans">{new Date(p.created_at).toLocaleString()}</td>
                    <td className={`p-4 text-right font-bold text-sm ${
                      p.entry_type === 'DEBIT' ? 'text-rose-600' : 'text-emerald-600'
                    }`}>
                      {formatPostingAmount(p.amount, p.entry_type, p.currency)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
