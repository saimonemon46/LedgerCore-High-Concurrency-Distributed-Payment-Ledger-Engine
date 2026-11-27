'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRightLeft, PlusCircle, Search } from 'lucide-react';
import { api } from '@/lib/api';
import { Transaction } from '@/types/api';
import { formatMoney } from '@/lib/format-money';
import { StatusBadge } from '@/components/ui/StatusBadge';

export default function TransfersPage() {
  const [transfers, setTransfers] = useState<Transaction[]>([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadTransfers();
  }, []);

  async function loadTransfers() {
    const data = await api.getTransactions();
    setTransfers(data);
  }

  const filtered = transfers.filter(
    (t) =>
      t.id.toLowerCase().includes(search.toLowerCase()) ||
      t.source_account_id.toLowerCase().includes(search.toLowerCase()) ||
      t.destination_account_id.toLowerCase().includes(search.toLowerCase()) ||
      t.idempotency_key.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ArrowRightLeft className="w-6 h-6 text-indigo-600" /> Transfer Pipeline
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Browse and inspect settled, in-flight, and reversed money movements.
          </p>
        </div>
        <Link
          href="/console/transfers/new"
          className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-4 py-2 rounded-lg text-sm transition shadow-sm"
        >
          <PlusCircle className="w-4 h-4" /> New Transfer
        </Link>
      </div>

      {/* Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
        <div className="relative w-full max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search by Transaction ID, Account, or Idempotency Key..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-semibold text-slate-500">
              <tr>
                <th className="p-4">Transaction ID</th>
                <th className="p-4">Route (Src → Dest)</th>
                <th className="p-4">Idempotency Key</th>
                <th className="p-4">Timestamp (UTC)</th>
                <th className="p-4">Status</th>
                <th className="p-4 text-right">Amount</th>
                <th className="p-4 text-right">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50/70 transition">
                  <td className="p-4 font-mono font-bold text-slate-900 text-xs">
                    <Link href={`/console/transfers/${t.id}`} className="hover:text-indigo-600 hover:underline">
                      {t.id}
                    </Link>
                  </td>
                  <td className="p-4 font-mono text-xs text-slate-800">
                    <span className="font-semibold">{t.source_account_id}</span>
                    <span className="text-slate-400 mx-1.5">→</span>
                    <span className="font-semibold">{t.destination_account_id}</span>
                  </td>
                  <td className="p-4 font-mono text-xs text-slate-500 truncate max-w-[140px]" title={t.idempotency_key}>
                    {t.idempotency_key}
                  </td>
                  <td className="p-4 text-xs text-slate-500 font-sans">
                    {new Date(t.created_at).toLocaleString()}
                  </td>
                  <td className="p-4">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="p-4 text-right font-mono font-bold text-slate-900 text-sm">
                    {formatMoney(t.amount, t.currency)}
                  </td>
                  <td className="p-4 text-right">
                    <Link
                      href={`/console/transfers/${t.id}`}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition"
                    >
                      Inspect →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
