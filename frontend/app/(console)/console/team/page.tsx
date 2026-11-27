'use client';

import React from 'react';
import { Users, Shield, PlusCircle, UserCheck } from 'lucide-react';

const MEMBERS = [
  {
    id: 'usr_01',
    name: 'Saimon Hasan Emon',
    email: 'saimonemon46@gmail.com',
    role: 'Workspace Owner',
    status: 'ACTIVE',
    last_active: 'Just now',
  },
  {
    id: 'usr_02',
    name: 'Finance Compliance Lead',
    email: 'compliance@northstar.internal',
    role: 'Auditor',
    status: 'ACTIVE',
    last_active: '2 hours ago',
  },
  {
    id: 'usr_03',
    name: 'Automated Operations Bot',
    email: 'ops-worker@northstar.internal',
    role: 'Service Worker',
    status: 'ACTIVE',
    last_active: '5 minutes ago',
  },
];

export default function TeamPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Users className="w-6 h-6 text-indigo-600" /> Team & Access Control (RBAC)
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Enforce role boundaries. Auditors have strict read-only access to accounts and journals.
          </p>
        </div>
        <button className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-4 py-2 rounded-lg text-sm transition shadow-sm">
          <PlusCircle className="w-4 h-4" /> Invite Member
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-left text-sm text-slate-700">
          <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-semibold text-slate-500">
            <tr>
              <th className="p-4">Member Name</th>
              <th className="p-4">Assigned Role</th>
              <th className="p-4">Status</th>
              <th className="p-4">Last Activity</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs">
            {MEMBERS.map((m) => (
              <tr key={m.id} className="hover:bg-slate-50/70 transition">
                <td className="p-4">
                  <div className="font-bold text-slate-900">{m.name}</div>
                  <div className="text-slate-400 font-mono text-[11px]">{m.email}</div>
                </td>
                <td className="p-4">
                  <span className={`px-2.5 py-1 rounded-full font-semibold ${
                    m.role === 'Workspace Owner'
                      ? 'bg-indigo-100 text-indigo-800'
                      : m.role === 'Auditor'
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-slate-100 text-slate-700'
                  }`}>
                    {m.role}
                  </span>
                </td>
                <td className="p-4">
                  <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold text-[10px]">
                    {m.status}
                  </span>
                </td>
                <td className="p-4 text-slate-500">{m.last_active}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
