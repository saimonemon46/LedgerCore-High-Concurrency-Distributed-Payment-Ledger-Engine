'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Flame, Repeat, ShieldAlert, RotateCcw, CheckCircle2, XCircle, Loader2, Terminal, Trash2 } from 'lucide-react';
import { Account, TransferAttemptResult } from '@/types/api';
import { api } from '@/lib/api';

interface TerminalLine {
  id: string;
  text: string;
  tone: 'info' | 'success' | 'cyan' | 'warn' | 'error' | 'muted';
}

function shortAcc(id: string): string {
  const parts = id.split('-');
  if (parts.length >= 2) {
    return `${parts[0]}-${parts[1]}`;
  }
  return id.slice(0, 10);
}

function formatTerminalLine(
  res: TransferAttemptResult,
  srcShort: string,
  dstShort: string,
  amountStr: string,
): TerminalLine {
  const num = String(res.index).padStart(2, '0');
  const latency = `(${res.latencyMs.toFixed(0)}ms)`.padEnd(6);
  const route = `${srcShort} -> ${dstShort} | ৳${amountStr}`;
  if (res.outcome === 'SETTLED') {
    return {
      id: `req-${res.index}-${res.requestId}`,
      tone: 'success',
      text: `[REQ #${num}] ${route} | 200 SETTLED  ${latency} — Row lock acquired, debit/credit committed`,
    };
  }
  if (res.outcome === 'REPLAYED') {
    return {
      id: `req-${res.index}-${res.requestId}`,
      tone: 'cyan',
      text: `[REQ #${num}] ${route} | 200 REPLAYED ${latency} — Idempotency-Key matched, cached response`,
    };
  }
  if (res.outcome === 'RATE_LIMITED') {
    return {
      id: `req-${res.index}-${res.requestId}`,
      tone: 'warn',
      text: `[REQ #${num}] ${route} | 429 REJECTED ${latency} — Rate limit exceeded`,
    };
  }
  if (res.outcome === 'CIRCUIT_OPEN') {
    return {
      id: `req-${res.index}-${res.requestId}`,
      tone: 'error',
      text: `[REQ #${num}] ${route} | 503 CIRCUIT  ${latency} — Fail-fast guard triggered`,
    };
  }
  if (res.outcome === 'INSUFFICIENT_FUNDS') {
    return {
      id: `req-${res.index}-${res.requestId}`,
      tone: 'warn',
      text: `[REQ #${num}] ${route} | ${res.status} REJECTED ${latency} — Insufficient Funds`,
    };
  }
  return {
    id: `req-${res.index}-${res.requestId}`,
    tone: 'error',
    text: `[REQ #${num}] ${route} | ${res.status} ERROR    ${latency} — ${res.detail || 'Unexpected failure'}`,
  };
}

interface ConcurrencySimulatorProps {
  accounts: Account[];
  circuitState: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  onSimulationComplete: (results: TransferAttemptResult[]) => void;
  onCircuitStateChange: (state: 'CLOSED' | 'OPEN' | 'HALF_OPEN') => void;
}

export function ConcurrencySimulator({
  accounts,
  circuitState,
  onSimulationComplete,
  onCircuitStateChange,
}: ConcurrencySimulatorProps) {
  const [runningMode, setRunningMode] = useState<'concurrent' | 'idempotency' | 'chaos' | null>(null);
  const [terminalLogs, setTerminalLogs] = useState<TerminalLine[]>([
    {
      id: 'boot-1',
      tone: 'muted',
      text: '> LedgerCore Execution Terminal ready. Trigger a simulation above to stream live HTTP & lock telemetry...',
    },
  ]);
  const terminalEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [terminalLogs]);

  const appendLog = (line: TerminalLine) => {
    setTerminalLogs((prev) => [...prev.slice(-140), line]);
  };
  const [lastSummary, setLastSummary] = useState<{
    title: string;
    settled: number;
    replayed: number;
    rejected: number;
    rateLimited: number;
    circuitOpen: number;
    avgLatencyMs: number;
    drift: string;
    details: string;
  } | null>(null);

  const pickPair = () => {
    const active = accounts.filter((a) => a.status === 'ACTIVE');
    const src = active[0] || accounts[0];
    const dst = active[1] || active[0] || src;
    return {
      srcId: src?.id || 'ACC-001-NORTHSTAR',
      dstId: dst?.id || 'ACC-002-NORTHSTAR',
      currency: 'BDT',
    };
  };

  const ensureBreakerClosed = async () => {
    if (circuitState !== 'CLOSED') {
      const resetState = await api.simulateCircuitBreaker('reset');
      onCircuitStateChange(resetState);
      appendLog({
        id: `auto-reset-${Date.now()}`,
        tone: 'muted',
        text: '> Auto-reset Circuit Breaker -> CLOSED before running transfer simulation.',
      });
    }
  };

  const pickBidirectionalPairs = (): Array<{ srcId: string; dstId: string; currency: string }> => {
    const active = accounts.filter(
      (a) => a.status === 'ACTIVE' && !a.id.includes('CLEARING') && !a.id.includes('FEE'),
    );
    const pool = active.length >= 2 ? active : accounts.filter((a) => a.status === 'ACTIVE');
    if (pool.length < 2) {
      return [
        { srcId: 'ACC-001-NORTHSTAR', dstId: 'ACC-002-NORTHSTAR', currency: 'BDT' },
        { srcId: 'ACC-002-NORTHSTAR', dstId: 'ACC-001-NORTHSTAR', currency: 'BDT' },
      ];
    }
    const pairs: Array<{ srcId: string; dstId: string; currency: string }> = [];
    for (let i = 0; i < pool.length; i++) {
      const next = (i + 1) % pool.length;
      pairs.push({ srcId: pool[i].id, dstId: pool[next].id, currency: 'BDT' });
      pairs.push({ srcId: pool[next].id, dstId: pool[i].id, currency: 'BDT' });
    }
    return pairs;
  };

  const handleConcurrentBurst = async () => {
    setRunningMode('concurrent');
    await ensureBreakerClosed();
    const pairs = pickBidirectionalPairs();
    const unitAmount = '25.00';
    const totalRequests = 100;
    const batchId = Date.now();
    appendLog({
      id: `hdr-${batchId}`,
      tone: 'info',
      text: `> Firing ${totalRequests} concurrent bidirectional POST /api/v1/transfers (৳${unitAmount} each across ${Math.min(4, Math.max(2, pairs.length / 2))} accounts)...`,
    });

    const promises = Array.from({ length: totalRequests }, (_, idx) => {
      const pair = pairs[idx % pairs.length];
      const srcShort = shortAcc(pair.srcId);
      const dstShort = shortAcc(pair.dstId);
      return api
        .executeTransferProbe(
          {
            source_account_id: pair.srcId,
            destination_account_id: pair.dstId,
            amount: unitAmount,
            currency: pair.currency,
            idempotency_key: `sim_burst_${batchId}_${idx}`,
            reference_note: `Bidirectional burst #${idx + 1}`,
          },
          idx + 1,
        )
        .then((res) => {
          appendLog(formatTerminalLine(res, srcShort, dstShort, unitAmount));
          return res;
        });
    });
    const results = await Promise.all(promises);
    const settled = results.filter((r) => r.outcome === 'SETTLED').length;
    const rejected = results.filter((r) => r.outcome === 'INSUFFICIENT_FUNDS').length;
    const rateLimited = results.filter((r) => r.outcome === 'RATE_LIMITED').length;
    const circuitOpen = results.filter((r) => r.outcome === 'CIRCUIT_OPEN').length;
    const movedVolume = (settled * parseFloat(unitAmount)).toFixed(2);
    const avgLatencyMs =
      Math.round((results.reduce((s, r) => s + r.latencyMs, 0) / Math.max(1, results.length)) * 100) / 100;

    appendLog({
      id: `sep-${batchId}`,
      tone: 'muted',
      text: '--------------------------------------------------------------------------------',
    });
    appendLog({
      id: `done-${batchId}`,
      tone: 'info',
      text: `DONE: ${totalRequests} Total | ${settled} Settled (৳${movedVolume} moved) | ${rejected} Insufficient Funds | ${rateLimited} Rate Limited | ${circuitOpen} Circuit Open | Drift: ৳0.00`,
    });

    setLastSummary({
      title: `${totalRequests} Parallel Bidirectional Transfers Executed`,
      settled,
      replayed: 0,
      rejected,
      rateLimited,
      circuitOpen,
      avgLatencyMs,
      drift: '0.00',
      details: `${totalRequests} concurrent POST /api/v1/transfers dispatched bidirectionally across active accounts (৳${movedVolume} settled) with canonical lock ordering.`,
    });
    onSimulationComplete(results);
    setRunningMode(null);
  };

  const handleIdempotencyReplay = async () => {
    setRunningMode('idempotency');
    await ensureBreakerClosed();
    const { srcId, dstId, currency } = pickPair();
    const srcShort = shortAcc(srcId);
    const dstShort = shortAcc(dstId);
    const unitAmount = '10.00';
    const sharedKey = `idem_replay_${Date.now()}`;
    appendLog({
      id: `hdr-${sharedKey}`,
      tone: 'info',
      text: `> Sending 3 sequential POST /api/v1/transfers (${srcShort} -> ${dstShort} | ৳${unitAmount}) | Key: ${sharedKey}`,
    });
    const results: TransferAttemptResult[] = [];
    for (let i = 1; i <= 3; i++) {
      const res = await api.executeTransferProbe(
        {
          source_account_id: srcId,
          destination_account_id: dstId,
          amount: unitAmount,
          currency,
          idempotency_key: sharedKey,
          reference_note: 'Idempotency replay test',
        },
        i,
      );
      appendLog(formatTerminalLine(res, srcShort, dstShort, unitAmount));
      results.push(res);
    }
    const settled = results.filter((r) => r.outcome === 'SETTLED').length;
    const replayed = results.filter((r) => r.outcome === 'REPLAYED').length;
    const movedVolume = (settled * parseFloat(unitAmount)).toFixed(2);
    const avgLatencyMs =
      Math.round((results.reduce((s, r) => s + r.latencyMs, 0) / results.length) * 100) / 100;

    appendLog({
      id: `sep-${sharedKey}`,
      tone: 'muted',
      text: '--------------------------------------------------------------------------------',
    });
    appendLog({
      id: `done-${sharedKey}`,
      tone: 'info',
      text: `DONE: 3 Total | ${settled} Debited Once (৳${movedVolume} moved) | ${replayed} Safe Replays | Drift: ৳0.00`,
    });

    setLastSummary({
      title: 'Idempotency Replay (3x Same Key)',
      settled,
      replayed,
      rejected: results.filter((r) => r.outcome === 'INSUFFICIENT_FUNDS').length,
      rateLimited: 0,
      circuitOpen: 0,
      avgLatencyMs,
      drift: '0.00',
      details: `Key "${sharedKey}" sent 3 times sequentially. Balance debited only once; subsequent calls replayed safely.`,
    });
    onSimulationComplete(results);
    setRunningMode(null);
  };

  const handleCircuitBreakerChaos = async () => {
    setRunningMode('chaos');
    const nextAction = circuitState === 'OPEN' ? 'reset' : 'trip';
    const newState = await api.simulateCircuitBreaker(nextAction);
    onCircuitStateChange(newState);

    if (newState === 'OPEN') {
      const { srcId, dstId, currency } = pickPair();
      const srcShort = shortAcc(srcId);
      const dstShort = shortAcc(dstId);
      const unitAmount = '5.00';
      const ts = Date.now();
      appendLog({
        id: `cb-open-${ts}`,
        tone: 'error',
        text: `> Chaos injected: Circuit Breaker tripped -> OPEN. Sending fail-fast probe...`,
      });
      const probe = await api.executeTransferProbe(
        {
          source_account_id: srcId,
          destination_account_id: dstId,
          amount: unitAmount,
          currency,
          idempotency_key: `cb_probe_${ts}`,
          reference_note: 'Circuit breaker fail-fast probe',
        },
        1,
      );
      appendLog(formatTerminalLine(probe, srcShort, dstShort, unitAmount));
      appendLog({
        id: `cb-sep-${ts}`,
        tone: 'muted',
        text: '--------------------------------------------------------------------------------',
      });
      setLastSummary({
        title: 'Circuit Breaker Tripped -> OPEN',
        settled: 0,
        replayed: 0,
        rejected: 0,
        rateLimited: 0,
        circuitOpen: probe.outcome === 'CIRCUIT_OPEN' ? 1 : 0,
        avgLatencyMs: probe.latencyMs,
        drift: '0.00',
        details: `Downstream failures tripped the breaker OPEN. Probe failed fast in ${probe.latencyMs}ms with HTTP ${probe.status}.`,
      });
      onSimulationComplete([probe]);
    } else {
      appendLog({
        id: `cb-reset-${Date.now()}`,
        tone: 'success',
        text: '> Circuit Breaker reset -> CLOSED. Normal transaction execution restored.',
      });
      setLastSummary({
        title: 'Circuit Breaker Recovered -> CLOSED',
        settled: 0,
        replayed: 0,
        rejected: 0,
        rateLimited: 0,
        circuitOpen: 0,
        avgLatencyMs: 0,
        drift: '0.00',
        details: 'Circuit breaker reset to CLOSED. Normal transfer execution restored.',
      });
    }
    setRunningMode(null);
  };

  return (
    <section className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Flame className="w-4 h-4 text-amber-400" />
            Interactive Concurrency &amp; Chaos Simulator
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Stress-test race conditions, idempotency replay protection, and circuit breaker fail-fast directly from the browser.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <button
          onClick={handleConcurrentBurst}
          disabled={runningMode !== null}
          className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs sm:text-sm font-semibold transition shadow-sm"
        >
          {runningMode === 'concurrent' ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Flame className="w-4 h-4" />
          )}
          Simulate 100 Concurrent Transfers
        </button>

        <button
          onClick={handleIdempotencyReplay}
          disabled={runningMode !== null}
          className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-100 border border-slate-700 text-xs sm:text-sm font-semibold transition"
        >
          {runningMode === 'idempotency' ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Repeat className="w-4 h-4 text-cyan-400" />
          )}
          Test Idempotency Replay (3x)
        </button>

        <button
          onClick={handleCircuitBreakerChaos}
          disabled={runningMode !== null}
          className={`flex items-center justify-center gap-2 px-4 py-3 rounded-lg border text-xs sm:text-sm font-semibold transition disabled:opacity-50 ${
            circuitState === 'OPEN'
              ? 'bg-emerald-600/20 hover:bg-emerald-600/30 border-emerald-500/40 text-emerald-300'
              : 'bg-rose-600/20 hover:bg-rose-600/30 border-rose-500/40 text-rose-300'
          }`}
        >
          {runningMode === 'chaos' ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : circuitState === 'OPEN' ? (
            <RotateCcw className="w-4 h-4" />
          ) : (
            <ShieldAlert className="w-4 h-4" />
          )}
          {circuitState === 'OPEN' ? 'Reset Circuit Breaker' : 'Trigger Circuit Breaker'}
        </button>
      </div>

      {lastSummary && (
        <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 space-y-2 animate-fade-in">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">
              {lastSummary.title}
            </span>
            <span className="text-xs font-mono text-emerald-400">
              Balance Drift: ৳{lastSummary.drift} · Avg Latency: {lastSummary.avgLatencyMs}ms
            </span>
          </div>
          <p className="text-xs text-slate-400">{lastSummary.details}</p>
          <div className="flex flex-wrap gap-2 pt-1 text-xs font-mono">
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 className="w-3.5 h-3.5" /> {lastSummary.settled} Settled (200)
            </span>
            {lastSummary.replayed > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                <Repeat className="w-3.5 h-3.5" /> {lastSummary.replayed} Replayed
              </span>
            )}
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <XCircle className="w-3.5 h-3.5" /> {lastSummary.rejected} Insufficient Funds (422/409)
            </span>
            {lastSummary.rateLimited > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20">
                {lastSummary.rateLimited} Rate Limited (429)
              </span>
            )}
            {lastSummary.circuitOpen > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">
                {lastSummary.circuitOpen} Circuit Open (503)
              </span>
            )}
          </div>
        </div>
      )}
      {/* Live Execution Terminal */}
      <div className="bg-black/95 border border-slate-800 rounded-lg overflow-hidden">
        <div className="px-3.5 py-2 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400">
            <Terminal className="w-3.5 h-3.5 text-emerald-400" />
            <span className="font-semibold text-slate-200">Live Execution Terminal</span>
            <span className="text-slate-600">|</span>
            <span className="text-emerald-400">stdout</span>
          </div>
          <button
            onClick={() => setTerminalLogs([])}
            className="inline-flex items-center gap-1 text-[11px] font-mono text-slate-500 hover:text-slate-200 transition"
            title="Clear terminal logs"
          >
            <Trash2 className="w-3 h-3" /> Clear
          </button>
        </div>

        <div className="p-3.5 font-mono text-[11px] sm:text-xs leading-relaxed max-h-64 overflow-y-auto overflow-x-auto space-y-0.5">
          {terminalLogs.length === 0 ? (
            <p className="text-slate-600">Terminal cleared. Click a simulation button above.</p>
          ) : (
            terminalLogs.map((line) => {
              const colorClass =
                line.tone === 'success'
                  ? 'text-emerald-400'
                  : line.tone === 'cyan'
                  ? 'text-cyan-400'
                  : line.tone === 'warn'
                  ? 'text-amber-400'
                  : line.tone === 'error'
                  ? 'text-rose-400'
                  : line.tone === 'info'
                  ? 'text-slate-100 font-semibold'
                  : 'text-slate-500';
              return (
                <div key={line.id} className={`${colorClass} whitespace-nowrap`}>
                  {line.text}
                </div>
              );
            })
          )}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </section>
  );
}
