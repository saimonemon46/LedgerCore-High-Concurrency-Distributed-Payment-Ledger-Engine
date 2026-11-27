'use client';

import React from 'react';
import { History, Shield, CheckCircle2 } from 'lucide-react';

const LOGS = [
  {
    id: 'aud_0921',
    actor: 'saimonemon46@gmail.com',
    action: 'TRANSFER_EXECUTED',
    target: 'TXN-202611-0091',
    correlation_id: 'corr_9f81a7b',
    timestamp: '2026-11-13T22:15:00Z',
  },
  {
    id: 'aud_0920',
    actor: 'system_reconciliation_worker',
    action: 'RECONCILIATION_COMPLETED',
    target: 'REC-202611-001',
    correlation_id: 'corr_8b11c4d',
    timestamp: '2026-11-13T12:00:02Z',
  },
  {
    id: 'aud_0919',
    actor: 'saimonemon46@gmail.com',
    action: 'API_KEY_CREATED',
    target: 'key_live_001',
    correlation_id: 'corr_77a9821',
    timestamp: '2026-11-01T10:00:00Z',
  },
];

export default function AuditLogPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <History className="w-6 h-6 text-indigo-600" /> Administrative Audit Trail
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Immutable tracking of administrative actions, key creation, role elevation, and reconciliation runs.
          </p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-left text-sm text-slate-700">
          <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-semibold text-slate-500">
            <tr>
              <th className="p-4">Actor</th>
              <th className="p-4">Action</th>
              <th className="p-4">Target Resource</th>
              <th className="p-4">Correlation ID</th>
              <th className="p-4 text-right">Timestamp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs font-mono">
            {LOGS.map((l) => (
              <tr key={l.id} className="hover:bg-slate-50/70 transition">
                <td className="p-4 font-sans font-semibold text-slate-900">{l.actor}</td>
                <td className="p-4">
                  <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-800 font-bold text-[10px]">
                    {l.action}
                  </span>
                </td>
                <td className="p-4 text-slate-600">{l.target}</td>
                <td className="p-4 text-slate-400">{l.correlation_id}</td>
                <td className="p-4 text-right font-sans text-slate-500">
                  {new Date(l.timestamp).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
