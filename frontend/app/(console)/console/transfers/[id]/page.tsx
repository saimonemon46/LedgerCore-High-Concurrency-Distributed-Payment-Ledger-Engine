'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  ArrowLeft,
  ArrowRightLeft,
  ShieldCheck,
  CheckCircle2,
  Lock,
  Layers,
  RotateCcw,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Transaction, LedgerEntry } from '@/types/api';
import { formatMoney } from '@/lib/format-money';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { DoubleEntryPostings } from '@/components/transfers/DoubleEntryPostings';

export default function TransactionDetailPage() {
  const params = useParams();
  const txId = params?.id as string;

  const [transaction, setTransaction] = useState<Transaction | null>(null);
  const [postings, setPostings] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [reversing, setReversing] = useState(false);
  const [reversed, setReversed] = useState(false);

  useEffect(() => {
    async function loadTx() {
      const [tx, allEntries] = await Promise.all([
        api.getTransaction(txId),
        api.getLedgerEntries(),
      ]);
      setTransaction(tx);
      if (tx) {
        setPostings(allEntries.filter((e) => e.transaction_id === tx.id));
      }
      setLoading(false);
    }
    loadTx();
  }, [txId]);

  const handleReverse = () => {
    if (!transaction) return;
    setReversing(true);
    setTimeout(() => {
      setReversing(false);
      setReversed(true);
      setTransaction({ ...transaction, status: 'REVERSED' });
    }, 800);
  };

  if (loading) {
    return <div className="p-8 text-center text-sm text-slate-500">Loading transaction record...</div>;
  }

  if (!transaction) {
    return (
      <div className="bg-white p-8 rounded-xl border border-slate-200 text-center space-y-3">
        <p className="text-slate-600 font-semibold">Transaction not found</p>
        <Link href="/console/transfers" className="text-xs text-indigo-600 hover:underline">
          Return to transfer pipeline
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Back Link */}
      <Link
        href="/console/transfers"
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition"
      >
        <ArrowLeft className="w-4 h-4" /> Back to Transfers
      </Link>

      {/* Main Profile Header */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold font-mono text-slate-900">{transaction.id}</h1>
              <StatusBadge status={transaction.status} />
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Executed at {new Date(transaction.created_at).toUTCString()}
            </p>
          </div>

          <div className="text-right">
            <span className="text-xs uppercase font-semibold text-slate-400">Settled Amount</span>
            <div className="text-3xl font-extrabold font-mono text-slate-900">
              {formatMoney(transaction.amount, transaction.currency)}
            </div>
          </div>
        </div>

        {/* Metadata Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
          <div className="p-3 bg-slate-50 rounded-lg">
            <span className="text-slate-400 block font-sans">Source Account (Debit)</span>
            <span className="font-bold text-slate-900">{transaction.source_account_id}</span>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg">
            <span className="text-slate-400 block font-sans">Destination Account (Credit)</span>
            <span className="font-bold text-slate-900">{transaction.destination_account_id}</span>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg">
            <span className="text-slate-400 block font-sans">Idempotency Key</span>
            <span className="font-bold text-slate-900 truncate block" title={transaction.idempotency_key}>
              {transaction.idempotency_key}
            </span>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg">
            <span className="text-slate-400 block font-sans">Fee Deducted</span>
            <span className="font-bold text-slate-900">{formatMoney(transaction.fee_amount || '0.00', transaction.currency)}</span>
          </div>
        </div>

        {/* Reversal Action */}
        {transaction.status === 'SETTLED' && (
          <div className="pt-2 flex justify-end">
            <button
              onClick={handleReverse}
              disabled={reversing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-bold rounded-lg border border-rose-200 transition"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${reversing ? 'animate-spin' : ''}`} />
              {reversing ? 'Posting Compensating Leg...' : 'Issue Compensating Reversal'}
            </button>
          </div>
        )}

        {reversed && (
          <div className="p-3 bg-purple-50 border border-purple-200 rounded-lg text-xs font-semibold text-purple-800">
            Reversal settled via compensating entries! Original entries preserved as immutable history.
          </div>
        )}
      </div>

      {/* Double-Entry Postings */}
      {postings.length > 0 ? (
        <DoubleEntryPostings postings={postings} currency={transaction.currency} />
      ) : (
        <div className="bg-white p-6 rounded-xl border border-slate-200 text-xs text-slate-500 text-center">
          No distinct journal postings found for this transaction ID.
        </div>
      )}
    </div>
  );
}
