'use client';

import React from 'react';
import { Settings, Shield, Building, Database } from 'lucide-react';

export default function SettingsPage() {
  return (
    <div className="space-y-6 max-w-4xl">
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
          <Settings className="w-6 h-6 text-indigo-600" /> Workspace Settings
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Configure tenant boundaries, supported currency exponents, and security defaults.
        </p>
      </div>

      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <h2 className="font-bold text-slate-900 text-base flex items-center gap-2">
          <Building className="w-5 h-5 text-indigo-600" />
          Workspace Profile
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div>
            <label className="block font-bold uppercase text-slate-500 mb-1">Tenant Name</label>
            <input
              type="text"
              readOnly
              value="Northstar Demo Payments"
              className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 font-semibold text-slate-800"
            />
          </div>

          <div>
            <label className="block font-bold uppercase text-slate-500 mb-1">Tenant ID</label>
            <input
              type="text"
              readOnly
              value="ten_northstar_01"
              className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 font-mono text-slate-600"
            />
          </div>

          <div>
            <label className="block font-bold uppercase text-slate-500 mb-1">Primary Settlement Currency</label>
            <input
              type="text"
              readOnly
              value="BDT (৳) — Minor Unit 2 Exponent"
              className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 font-mono text-slate-800"
            />
          </div>

          <div>
            <label className="block font-bold uppercase text-slate-500 mb-1">Database Row-Lock Timeout</label>
            <input
              type="text"
              readOnly
              value="5,000 ms (PostgreSQL Lock Timeout)"
              className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 font-mono text-slate-800"
            />
          </div>
        </div>
      </div>

      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-3">
        <h2 className="font-bold text-slate-900 text-base flex items-center gap-2">
          <Shield className="w-5 h-5 text-emerald-600" />
          Financial Security Enforcement
        </h2>
        <div className="text-xs text-slate-600 space-y-2 leading-relaxed">
          <p>
            • <strong>Canonical Lock Ordering:</strong> Strictly enforced by the core domain engine before any database read or mutation.
          </p>
          <p>
            • <strong>Negative Balance Prevention:</strong> Debits exceeding available balance are rejected at both domain model and SQL check constraint levels.
          </p>
          <p>
            • <strong>Journal Immutability:</strong> Updates and Deletions against <code className="font-mono text-indigo-700">ledger_entries</code> are blocked by database trigger.
          </p>
        </div>
      </div>
    </div>
  );
}
