'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ArrowRightLeft,
  ArrowRight,
  ShieldCheck,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Lock,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Account, Transaction } from '@/types/api';
import { formatMoney } from '@/lib/format-money';
import { IdempotencyAlert } from '@/components/ui/IdempotencyAlert';
import { DoubleEntryPostings } from '@/components/transfers/DoubleEntryPostings';

export default function NewTransferPage() {
  const router = useRouter();

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [sourceId, setSourceId] = useState('');
  const [destId, setDestId] = useState('');
  const [amount, setAmount] = useState('750.00');
  const [reference, setReference] = useState('Sandbox Merchant Settlement');
  const [idempotencyKey, setIdempotencyKey] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ transaction: Transaction; replayed: boolean } | null>(null);

  useEffect(() => {
    async function loadAccounts() {
      const accs = await api.getAccounts();
      setAccounts(accs);
      if (accs.length >= 2) {
        setSourceId(accs[0].id);
        setDestId(accs[1].id);
      }
      generateNewKey();
    }
    loadAccounts();
  }, []);

  const generateNewKey = () => {
    const key = `idem_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    setIdempotencyKey(key);
  };

  const handleTransfer = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);

    if (sourceId === destId) {
      setError('Source and Destination account cannot be the same');
      return;
    }

    try {
      setSubmitting(true);
      const res = await api.executeTransfer({
        source_account_id: sourceId,
        destination_account_id: destId,
        amount,
        idempotency_key: idempotencyKey,
        reference_note: reference,
      });
      setResult(res);

      // Refresh accounts in background
      const updated = await api.getAccounts();
      setAccounts(updated);
    } catch (err: any) {
      setError(err.message || 'Transfer failed');
    } finally {
      setSubmitting(false);
    }
  };

  const srcAcc = accounts.find((a) => a.id === sourceId);
  const destAcc = accounts.find((a) => a.id === destId);

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Top Header */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
          <ArrowRightLeft className="w-6 h-6 text-indigo-600" /> Execute Idempotent Transfer
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Initiate double-entry transfer with deterministic row-locking and idempotency key protection.
        </p>
      </div>

      {/* Transfer Form Card */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <form onSubmit={handleTransfer} className="space-y-5">
          {error && (
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs font-semibold text-rose-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Account Route Selection */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
                Source Account (Debit)
              </label>
              <select
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs font-mono font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.account_number} — {a.label} ({formatMoney(a.balance, a.currency)})
                  </option>
                ))}
              </select>
              {srcAcc && (
                <p className="text-[11px] text-slate-400 mt-1">
                  Available: <span className="font-mono font-bold text-slate-700">{formatMoney(srcAcc.balance, srcAcc.currency)}</span>
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
                Destination Account (Credit)
              </label>
              <select
                value={destId}
                onChange={(e) => setDestId(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs font-mono font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.account_number} — {a.label} ({formatMoney(a.balance, a.currency)})
                  </option>
                ))}
              </select>
              {destAcc && (
                <p className="text-[11px] text-slate-400 mt-1">
                  Balance: <span className="font-mono font-bold text-slate-700">{formatMoney(destAcc.balance, destAcc.currency)}</span>
                </p>
              )}
            </div>
          </div>

          {/* Amount & Reference */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
                Transfer Amount (BDT ৳)
              </label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-base font-mono font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <p className="text-[11px] text-slate-400 mt-1">Platform fee: ৳0.00 (Zero-Fee Sandbox tier)</p>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
                Reference / Narrative Note
              </label>
              <input
                type="text"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          {/* Idempotency Key Control */}
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-indigo-600" />
                Idempotency-Key Header
              </label>
              <button
                type="button"
                onClick={generateNewKey}
                className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1 transition"
              >
                <RefreshCw className="w-3 h-3" /> Generate Fresh Key
              </button>
            </div>
            <input
              type="text"
              required
              value={idempotencyKey}
              onChange={(e) => setIdempotencyKey(e.target.value)}
              className="w-full bg-white border border-slate-200 rounded-lg p-2 font-mono text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <p className="text-[11px] text-slate-500 leading-relaxed">
              <strong>Recruiter Demo Tip:</strong> Click &quot;Execute Transfer&quot; to commit. Then click it again with the exact same key to observe safe replay with zero double charges!
            </p>
          </div>

          {/* Action Buttons */}
          <div className="pt-2 flex items-center justify-end gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-6 py-2.5 rounded-lg shadow-sm transition disabled:opacity-50 text-sm"
            >
              {submitting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Acquiring Locks & Posting...
                </>
              ) : (
                <>
                  Execute Transfer
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Result Display */}
      {result && (
        <div className="space-y-4 animate-fade-in">
          {result.replayed ? (
            <IdempotencyAlert
              idempotencyKey={result.transaction.idempotency_key}
              transactionId={result.transaction.id}
            />
          ) : (
            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-xs font-semibold text-emerald-800 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>
                Transfer committed atomically! Transaction ID: <strong className="font-mono">{result.transaction.id}</strong>.
              </span>
            </div>
          )}

          {result.transaction.postings && result.transaction.postings.length > 0 && (
            <DoubleEntryPostings postings={result.transaction.postings} currency={result.transaction.currency} />
          )}
        </div>
      )}
    </div>
  );
}
