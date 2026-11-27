'use client';

import React, { useEffect, useState } from 'react';
import { Key, PlusCircle, Copy, Check, ShieldAlert, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import { ApiKeyRecord } from '@/types/api';
import { Modal } from '@/components/ui/Modal';

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [scopes, setScopes] = useState<string[]>(['transfers:write', 'accounts:read']);
  const [createdKey, setCreatedKey] = useState<ApiKeyRecord | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    loadKeys();
  }, []);

  async function loadKeys() {
    const data = await api.getApiKeys();
    setKeys(data);
  }

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    const newKey = await api.createApiKey(keyName, scopes);
    setCreatedKey(newKey);
    setKeyName('');
    loadKeys();
  };

  const handleCopy = (secret: string) => {
    navigator.clipboard.writeText(secret);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRevoke = async (id: string) => {
    if (confirm('Are you sure you want to revoke this API credential?')) {
      await api.revokeApiKey(id);
      loadKeys();
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Key className="w-6 h-6 text-indigo-600" /> Merchant API Credentials
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Manage high-entropy API keys for machine-to-machine financial integration.
          </p>
        </div>
        <button
          onClick={() => {
            setCreatedKey(null);
            setShowModal(true);
          }}
          className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-4 py-2 rounded-lg text-sm transition shadow-sm"
        >
          <PlusCircle className="w-4 h-4" /> Issue API Key
        </button>
      </div>

      {/* Keys Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-semibold text-slate-500">
              <tr>
                <th className="p-4">Name / Client</th>
                <th className="p-4">Key Prefix</th>
                <th className="p-4">Authorized Scopes</th>
                <th className="p-4">Last Used</th>
                <th className="p-4">Status</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {keys.map((k) => (
                <tr key={k.id} className="hover:bg-slate-50/70 transition">
                  <td className="p-4 font-bold text-slate-900">{k.name}</td>
                  <td className="p-4 font-mono font-bold text-slate-800">{k.key_prefix}</td>
                  <td className="p-4">
                    <div className="flex flex-wrap gap-1">
                      {k.scopes.map((s) => (
                        <span key={s} className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[10px]">
                          {s}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="p-4 text-slate-500 font-mono">
                    {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'Never'}
                  </td>
                  <td className="p-4">
                    {k.is_revoked ? (
                      <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800 font-bold text-[10px]">
                        REVOKED
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold text-[10px]">
                        ACTIVE
                      </span>
                    )}
                  </td>
                  <td className="p-4 text-right">
                    {!k.is_revoked && (
                      <button
                        onClick={() => handleRevoke(k.id)}
                        className="text-xs text-rose-600 hover:text-rose-800 font-semibold"
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal */}
      <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Issue Merchant API Key">
        {createdKey ? (
          <div className="space-y-4">
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 space-y-2">
              <div className="flex items-center gap-2 font-bold text-amber-950">
                <ShieldAlert className="w-4 h-4 text-amber-600" />
                <span>Save Your Secret Now</span>
              </div>
              <p>
                This secret will never be displayed again. If lost, you must revoke this key and issue a new one.
              </p>
            </div>

            <div className="p-3 bg-slate-900 rounded-lg flex items-center justify-between text-xs font-mono text-emerald-400">
              <span className="truncate pr-2">{createdKey.secret_preview}</span>
              <button
                onClick={() => handleCopy(createdKey.secret_preview || '')}
                className="bg-slate-800 hover:bg-slate-700 text-white p-1.5 rounded transition flex-shrink-0"
              >
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs rounded-lg transition"
              >
                I have securely stored the secret
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleCreateKey} className="space-y-4">
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
                Client / Key Name
              </label>
              <input
                type="text"
                required
                placeholder="e.g. Backend Microservice Relay"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
                Authorized Permissions
              </label>
              <div className="space-y-2 text-xs text-slate-700">
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked readOnly className="rounded text-indigo-600" />
                  <span>transfers:write (Execute fund transfers)</span>
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked readOnly className="rounded text-indigo-600" />
                  <span>accounts:read (Query account balances)</span>
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked readOnly className="rounded text-indigo-600" />
                  <span>ledger:read (Access double-entry journal)</span>
                </label>
              </div>
            </div>

            <div className="pt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition"
              >
                Generate Key
              </button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
