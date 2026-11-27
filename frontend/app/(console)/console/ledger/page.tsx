'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { BookOpen, Search, ShieldCheck, CheckCircle2 } from 'lucide-react';
import { api } from '@/lib/api';
import { LedgerEntry } from '@/types/api';
import { formatPostingAmount } from '@/lib/format-money';

export default function LedgerExplorerPage() {
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    async function loadLedger() {
      const data = await api.getLedgerEntries();
      setEntries(data);
    }
    loadLedger();
  }, []);

  const filtered = entries.filter(
    (e) =>
      e.account_id.toLowerCase().includes(search.toLowerCase()) ||
      e.transaction_id.toLowerCase().includes(search.toLowerCase()) ||
      e.entry_type.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-indigo-600" /> Immutable Journal Explorer
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Append-only financial records. Database triggers prohibit UPDATE and DELETE operations.
          </p>
        </div>
        <span className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-100 text-emerald-800 flex items-center gap-1.5 w-max">
          <ShieldCheck className="w-4 h-4 text-emerald-600" /> Append-Only Protected
        </span>
      </div>

      {/* Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
        <div className="relative w-full max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search by Account, Transaction ID, or DEBIT/CREDIT..."
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
                <th className="p-4">Seq ID</th>
                <th className="p-4">Transaction ID</th>
                <th className="p-4">Account ID</th>
                <th className="p-4">Entry Leg</th>
                <th className="p-4">Timestamp (UTC)</th>
                <th className="p-4 text-right">Signed Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono text-xs">
              {filtered.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50/70 transition">
                  <td className="p-4 text-slate-400 font-bold">#{e.sequence_id}</td>
                  <td className="p-4 font-bold text-slate-900">
                    <Link href={`/console/transfers/${e.transaction_id}`} className="text-indigo-600 hover:underline">
                      {e.transaction_id}
                    </Link>
                  </td>
                  <td className="p-4 font-semibold text-slate-800">{e.account_id}</td>
                  <td className="p-4">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      e.entry_type === 'DEBIT' ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'
                    }`}>
                      {e.entry_type}
                    </span>
                  </td>
                  <td className="p-4 text-slate-500 font-sans">{new Date(e.created_at).toLocaleString()}</td>
                  <td className={`p-4 text-right font-bold text-sm ${
                    e.entry_type === 'DEBIT' ? 'text-rose-600' : 'text-emerald-600'
                  }`}>
                    {formatPostingAmount(e.amount, e.entry_type, e.currency)}
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
