import React from 'react';
import { CheckCircle2, ArrowRight } from 'lucide-react';
import { LedgerEntry } from '@/types/api';
import { formatPostingAmount } from '@/lib/format-money';

interface DoubleEntryPostingsProps {
  postings: LedgerEntry[];
  currency?: string;
}

export function DoubleEntryPostings({ postings, currency = 'BDT' }: DoubleEntryPostingsProps) {
  // Financial zero-sum check
  const netSum = postings.reduce((acc, p) => {
    const val = parseFloat(p.amount);
    return acc + (p.entry_type === 'CREDIT' ? val : -val);
  }, 0);

  const isBalanced = Math.abs(netSum) < 0.0001;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="p-4 bg-slate-50 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h3 className="font-bold text-slate-900 text-sm">Double-Entry Journal Postings</h3>
          <p className="text-xs text-slate-500">Atomic signed debit/credit legs recorded in immutable journal</p>
        </div>
        <div className="flex items-center gap-2">
          {isBalanced ? (
            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              Net Sum: 0.00 {currency} (Balanced)
            </span>
          ) : (
            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 flex items-center gap-1">
              Imbalance Detected: {netSum.toFixed(2)} {currency}
            </span>
          )}
        </div>
      </div>

      <div className="divide-y divide-slate-100 font-mono text-xs">
        {postings.map((p, idx) => (
          <div key={p.id || idx} className="p-3.5 flex items-center justify-between hover:bg-slate-50/70 transition">
            <div className="flex items-center gap-3">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
                p.entry_type === 'DEBIT' ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'
              }`}>
                {p.entry_type}
              </span>
              <div>
                <span className="font-bold text-slate-900">{p.account_id}</span>
                <span className="ml-2 text-[11px] text-slate-400">Seq #{p.sequence_id}</span>
              </div>
            </div>
            <div className={`font-bold text-sm ${
              p.entry_type === 'DEBIT' ? 'text-rose-600' : 'text-emerald-600'
            }`}>
              {formatPostingAmount(p.amount, p.entry_type, p.currency || currency)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
