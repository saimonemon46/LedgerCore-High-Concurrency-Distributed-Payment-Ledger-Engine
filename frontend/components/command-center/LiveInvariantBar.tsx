'use client';

import React from 'react';
import { ShieldCheck, Activity, Zap, Clock, Layers, RefreshCw } from 'lucide-react';
import { TelemetrySummary } from '@/types/api';
import { useDemoGuide } from '@/components/layout/DemoGuideContext';

interface LiveInvariantBarProps {
  telemetry: TelemetrySummary;
  driftAmount: string;
  isAuditing: boolean;
  onRunAudit: () => void;
}

export function LiveInvariantBar({
  telemetry,
  driftAmount,
  isAuditing,
  onRunAudit,
}: LiveInvariantBarProps) {
  const { demoGuide } = useDemoGuide();
  const isZeroDrift = parseFloat(driftAmount) === 0;
  const breakerColor =
    telemetry.circuit_breaker_state === 'CLOSED'
      ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
      : telemetry.circuit_breaker_state === 'HALF_OPEN'
      ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
      : 'text-rose-400 bg-rose-500/10 border-rose-500/30';

  return (
    <section className="space-y-4">
      {demoGuide && (
        <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-xs">
          <span className="font-mono font-bold text-indigo-300 bg-indigo-500/20 px-2 py-0.5 rounded">
            Step 1: Verify Invariant
          </span>
          <span className="text-slate-300">
            Confirm ∑ Debits == ∑ Credits (৳0.00 drift) before running load.
          </span>
        </div>
      )}

      {/* Balance Conservation Banner */}
      <div
        className={`rounded-xl border p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 transition ${
          isZeroDrift
            ? 'bg-emerald-950/40 border-emerald-500/40 shadow-[0_0_24px_rgba(16,185,129,0.08)]'
            : 'bg-rose-950/40 border-rose-500/40'
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center border ${
              isZeroDrift
                ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                : 'bg-rose-500/15 border-rose-500/30 text-rose-400'
            }`}
          >
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                Double-Entry Invariant Verified
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                LIVE
              </span>
            </div>
            <p className="font-mono text-base sm:text-lg font-bold text-white mt-0.5">
              ∑ Debits == ∑ Credits <span className="text-slate-500 mx-1.5">|</span>{' '}
              <span className={isZeroDrift ? 'text-emerald-400' : 'text-rose-400'}>
                Drift: ৳{driftAmount}
              </span>
            </p>
            <p className="text-xs text-slate-400 mt-1">
              Ensures every debit equals credit + fee — zero money lost or created (৳0.00 drift).
            </p>
          </div>
        </div>

        <button
          onClick={onRunAudit}
          disabled={isAuditing}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 transition self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-emerald-400 ${isAuditing ? 'animate-spin' : ''}`} />
          {isAuditing ? 'Reconciling...' : 'Verify Zero Drift'}
        </button>
      </div>

      {/* 4 Live Telemetry Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>Current TPS / RPS</span>
            <Zap className="w-4 h-4 text-indigo-400" />
          </div>
          <p className="mt-2 text-2xl font-mono font-bold text-white">
            {telemetry.rps.toFixed(1)} <span className="text-xs font-normal text-slate-400">req/s</span>
          </p>
          <p className="mt-1 text-[11px] text-slate-500 font-mono">
            {telemetry.transfers_settled_total} settled · {telemetry.transfers_failed_total} rejected
          </p>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>Circuit Breaker Status</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className={`px-2.5 py-1 rounded-md font-mono text-sm font-bold border ${breakerColor}`}>
              {telemetry.circuit_breaker_state}
            </span>
          </div>
          <p className="mt-1.5 text-[11px] text-slate-500">
            3-state sliding-window fault guard
          </p>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>Outbox Queue Lag</span>
            <Layers className="w-4 h-4 text-cyan-400" />
          </div>
          <p className="mt-2 text-2xl font-mono font-bold text-white">
            {telemetry.outbox_lag}{' '}
            <span className="text-xs font-normal text-slate-400">events</span>
          </p>
          <p className="mt-1 text-[11px] text-emerald-400/90">
            SKIP LOCKED transactional relay
          </p>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>P95 Latency</span>
            <Clock className="w-4 h-4 text-amber-400" />
          </div>
          <p className="mt-2 text-2xl font-mono font-bold text-white">
            {telemetry.p95_latency_ms.toFixed(2)}{' '}
            <span className="text-xs font-normal text-slate-400">ms</span>
          </p>
          <p className="mt-1 text-[11px] text-slate-500 font-mono">
            429 Rate Limits: {telemetry.rate_limit_rejections_total}
          </p>
        </div>
      </div>
    </section>
  );
}
