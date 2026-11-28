'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Account, TelemetrySummary, Transaction, TransferAttemptResult } from '@/types/api';
import { LiveInvariantBar } from '@/components/command-center/LiveInvariantBar';
import { ConcurrencySimulator } from '@/components/command-center/ConcurrencySimulator';
import { LedgerAccountExplorer } from '@/components/command-center/LedgerAccountExplorer';
import { ThroughputChart, ThroughputPoint } from '@/components/command-center/ThroughputChart';

const INITIAL_TELEMETRY: TelemetrySummary = {
  status: 'healthy',
  circuit_breaker_state: 'CLOSED',
  rps: 0,
  p95_latency_ms: 8.4,
  outbox_lag: 0,
  transfers_settled_total: 0,
  transfers_failed_total: 0,
  rate_limit_rejections_total: 0,
  timestamp: 0,
};

function formatHHMMSS(date: Date): string {
  return date.toTimeString().slice(0, 8);
}

export default function DashboardPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetrySummary>(INITIAL_TELEMETRY);
  const [driftAmount, setDriftAmount] = useState<string>('0.00');
  const [isAuditing, setIsAuditing] = useState<boolean>(false);
  const [chartSeries, setChartSeries] = useState<ThroughputPoint[]>([]);

  const refreshData = useCallback(async () => {
    const [accs, txs, tel] = await Promise.all([
      api.getAccounts(),
      api.getTransactions(),
      api.getTelemetrySummary(),
    ]);
    setAccounts(accs);
    setTransactions(txs);
    setTelemetry(tel);
  }, []);

  useEffect(() => {
    const now = Date.now();
    setChartSeries(
      Array.from({ length: 12 }, (_, idx) => ({
        label: formatHHMMSS(new Date(now - (11 - idx) * 3000)),
        rps: 2.5 + (idx % 3) * 1.2,
        avgLatencyMs: 8.4 + (idx % 4) * 1.5,
        settled: 3 + (idx % 4),
        insufficientFunds: 0,
        rateLimited: 0,
        circuitOpen: 0,
      })),
    );

    refreshData();
    const interval = setInterval(async () => {
      const tel = await api.getTelemetrySummary();
      setTelemetry(tel);
      setChartSeries((prev) => [
        ...prev.slice(-19),
        {
          label: formatHHMMSS(new Date()),
          rps: tel.rps,
          avgLatencyMs: tel.p95_latency_ms,
          settled: 0,
          insufficientFunds: 0,
          rateLimited: 0,
          circuitOpen: 0,
        },
      ]);
    }, 3000);
    return () => clearInterval(interval);
  }, [refreshData]);

  const handleRunAudit = async () => {
    setIsAuditing(true);
    try {
      const run = await api.triggerReconciliation();
      setDriftAmount(parseFloat(run.net_drift_amount || '0').toFixed(2));
    } finally {
      setIsAuditing(false);
    }
  };

  const handleSimulationComplete = async (results: TransferAttemptResult[]) => {
    const settled = results.filter(
      (r) => r.outcome === 'SETTLED' || r.outcome === 'REPLAYED',
    ).length;
    const rateLimited = results.filter(
      (r) => r.outcome === 'RATE_LIMITED' || r.status === 429,
    ).length;
    const circuitOpen = results.filter(
      (r) => r.outcome === 'CIRCUIT_OPEN' || r.status === 503,
    ).length;
    const insufficientFunds = results.filter(
      (r) =>
        r.outcome === 'INSUFFICIENT_FUNDS' ||
        r.status === 422 ||
        r.status === 409 ||
        (r.outcome === 'ERROR' && r.status !== 429 && r.status !== 503),
    ).length;

    const totalMs = Math.max(10, results.reduce((s, r) => s + r.latencyMs, 0));
    const avgLatencyMs =
      results.length > 0
        ? Math.round((results.reduce((s, r) => s + r.latencyMs, 0) / results.length) * 10) / 10
        : 0;
    const burstRps = Math.round((results.length / totalMs) * 1000 * 10) / 10;

    setChartSeries((prev) => [
      ...prev.slice(-19),
      {
        label: formatHHMMSS(new Date()),
        rps: burstRps,
        avgLatencyMs,
        settled,
        insufficientFunds,
        rateLimited,
        circuitOpen,
      },
    ]);
    await refreshData();
  };

  const handleCircuitStateChange = (state: 'CLOSED' | 'OPEN' | 'HALF_OPEN') => {
    setTelemetry((prev) => ({
      ...prev,
      circuit_breaker_state: state,
      status: state === 'OPEN' ? 'degraded' : 'healthy',
    }));
  };

  return (
    <div className="space-y-6">
      <LiveInvariantBar
        telemetry={telemetry}
        driftAmount={driftAmount}
        isAuditing={isAuditing}
        onRunAudit={handleRunAudit}
      />

      <ConcurrencySimulator
        accounts={accounts}
        circuitState={telemetry.circuit_breaker_state}
        onSimulationComplete={handleSimulationComplete}
        onCircuitStateChange={handleCircuitStateChange}
      />

      <ThroughputChart series={chartSeries} />

      <LedgerAccountExplorer accounts={accounts} transactions={transactions} />
    </div>
  );
}
