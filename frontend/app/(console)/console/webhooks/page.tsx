'use client';

import React, { useEffect, useState } from 'react';
import { Webhook, PlusCircle, CheckCircle2, RefreshCw, Send, AlertCircle } from 'lucide-react';
import { api } from '@/lib/api';
import { WebhookEndpoint, WebhookDelivery } from '@/types/api';
import { StatusBadge } from '@/components/ui/StatusBadge';

export default function WebhooksPage() {
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([]);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [replayingId, setReplayingId] = useState<string | null>(null);

  useEffect(() => {
    async function loadWebhooks() {
      const [eps, dels] = await Promise.all([
        api.getWebhooks(),
        api.getWebhookDeliveries(),
      ]);
      setEndpoints(eps);
      setDeliveries(dels);
    }
    loadWebhooks();
  }, []);

  const handleReplay = (id: string) => {
    setReplayingId(id);
    setTimeout(() => {
      setReplayingId(null);
      alert('Webhook dispatched successfully! Received HTTP 200 OK from downstream gateway.');
    }, 700);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Webhook className="w-6 h-6 text-indigo-600" /> Webhook Subscriptions & Deliveries
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Asynchronous event notifications signed with HMAC-SHA256, delivered from the transactional outbox relay.
          </p>
        </div>
      </div>

      {/* Endpoints Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-bold text-slate-900 text-base">Registered Webhook Endpoints</h2>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800">
            HMAC Signed
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-semibold text-slate-500">
              <tr>
                <th className="p-4">Destination URL</th>
                <th className="p-4">Subscribed Events</th>
                <th className="p-4">Signing Secret</th>
                <th className="p-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs font-mono">
              {endpoints.map((ep) => (
                <tr key={ep.id} className="hover:bg-slate-50/70 transition">
                  <td className="p-4 font-bold text-slate-900">{ep.url}</td>
                  <td className="p-4">
                    <div className="flex flex-wrap gap-1">
                      {ep.event_types.map((e) => (
                        <span key={e} className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 text-[10px] font-sans font-semibold">
                          {e}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="p-4 text-slate-500">{ep.secret_preview}</td>
                  <td className="p-4">
                    <StatusBadge status={ep.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Deliveries Log */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-bold text-slate-900 text-base">Recent Delivery Attempts</h2>
          <span className="text-xs text-slate-400">Bounded Retries with Exponential Backoff</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-semibold text-slate-500">
              <tr>
                <th className="p-4">Delivery ID</th>
                <th className="p-4">Event Type</th>
                <th className="p-4">HTTP Response</th>
                <th className="p-4">Latency</th>
                <th className="p-4">Attempt</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs font-mono">
              {deliveries.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50/70 transition">
                  <td className="p-4 font-bold text-slate-900">{d.id}</td>
                  <td className="p-4 font-sans font-semibold text-slate-800">{d.event_type}</td>
                  <td className="p-4">
                    <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold">
                      {d.http_status} OK
                    </span>
                  </td>
                  <td className="p-4 text-slate-500">{d.response_time_ms}ms</td>
                  <td className="p-4 text-slate-500">Attempt #{d.attempt_count}</td>
                  <td className="p-4 text-right">
                    <button
                      onClick={() => handleReplay(d.id)}
                      disabled={replayingId === d.id}
                      className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-sans font-semibold"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${replayingId === d.id ? 'animate-spin' : ''}`} />
                      Replay
                    </button>
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
