'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Terminal, Copy, Check, ShieldCheck, ArrowRight, BookOpen } from 'lucide-react';

export default function DocsPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyCode = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const sampleCurl = `curl -X POST "https://api.ledgercore.internal/api/v1/transfers" \\
  -H "Authorization: Bearer lc_live_8f3a9e..." \\
  -H "Idempotency-Key: 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source_account_id": "ACC-001-NORTHSTAR",
    "destination_account_id": "ACC-002-NORTHSTAR",
    "amount": "750.00",
    "currency": "BDT",
    "reference_note": "Merchant payout settlement"
  }'`;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 sticky top-0 z-50 bg-slate-950/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-sm">
              LC
            </div>
            <span className="font-bold text-base tracking-tight text-white">LedgerCore Developer API</span>
          </Link>
          <div className="flex items-center space-x-4">
            <Link href="/console" className="text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg transition">
              Open Console
            </Link>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-12 space-y-12">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">Developer Reference</span>
          <h1 className="text-3xl font-extrabold text-white mt-1">API Overview & Financial Guarantees</h1>
          <p className="mt-2 text-slate-400 text-sm leading-relaxed">
            LedgerCore exposes an idempotent, tenant-isolated REST API backed by an atomic double-entry journal.
          </p>
        </div>

        {/* Idempotency Section */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
            <ShieldCheck className="w-5 h-5" />
            <span>Strict Idempotency Contract</span>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed">
            All mutating financial endpoints require an <code className="text-indigo-300 font-mono">Idempotency-Key</code> header.
            If a network timeout occurs, clients may safely resend the exact request:
          </p>
          <ul className="list-disc list-inside text-xs text-slate-400 space-y-1">
            <li><strong>First Submission:</strong> Executes double-entry balance adjustment, creates journal entries, and commits atomic transaction.</li>
            <li><strong>Replay with Identical Key & Payload:</strong> Returns original settled transaction result immediately. No second debit/credit occurs.</li>
            <li><strong>Replay with Mismatched Payload:</strong> Rejects with <code className="text-rose-400 font-mono">409 Conflict</code> (payload hash mismatch).</li>
          </ul>
        </div>

        {/* Example cURL */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-white text-sm flex items-center gap-2">
              <Terminal className="w-4 h-4 text-indigo-400" />
              Example: Idempotent Transfer Request
            </h3>
            <button
              onClick={() => copyCode(sampleCurl, 'curl')}
              className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-lg transition"
            >
              {copiedId === 'curl' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              {copiedId === 'curl' ? 'Copied' : 'Copy cURL'}
            </button>
          </div>
          <pre className="bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-xs text-indigo-200 overflow-x-auto leading-relaxed">
            {sampleCurl}
          </pre>
        </div>

        {/* Endpoints Table */}
        <div className="space-y-3">
          <h3 className="font-bold text-white text-sm">Core REST Endpoints</h3>
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden text-xs">
            <table className="w-full text-left">
              <thead className="bg-slate-950/80 text-slate-400 uppercase font-semibold border-b border-slate-800">
                <tr>
                  <th className="p-3.5">Method</th>
                  <th className="p-3.5">Endpoint</th>
                  <th className="p-3.5">Description</th>
                  <th className="p-3.5">Required Header</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-slate-300 font-mono">
                <tr>
                  <td className="p-3.5 text-emerald-400 font-bold">GET</td>
                  <td className="p-3.5">/api/v1/accounts</td>
                  <td className="p-3.5 font-sans">List workspace accounts with current balance</td>
                  <td className="p-3.5 text-slate-500">Authorization</td>
                </tr>
                <tr>
                  <td className="p-3.5 text-indigo-400 font-bold">POST</td>
                  <td className="p-3.5">/api/v1/transfers</td>
                  <td className="p-3.5 font-sans">Execute atomic double-entry transfer</td>
                  <td className="p-3.5 text-indigo-300">Idempotency-Key</td>
                </tr>
                <tr>
                  <td className="p-3.5 text-emerald-400 font-bold">GET</td>
                  <td className="p-3.5">/api/v1/ledger/entries</td>
                  <td className="p-3.5 font-sans">Query immutable journal postings</td>
                  <td className="p-3.5 text-slate-500">Authorization</td>
                </tr>
                <tr>
                  <td className="p-3.5 text-indigo-400 font-bold">POST</td>
                  <td className="p-3.5">/api/v1/audit/reconcile</td>
                  <td className="p-3.5 font-sans">Trigger mathematical reconciliation</td>
                  <td className="p-3.5 text-slate-500">Authorization</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
