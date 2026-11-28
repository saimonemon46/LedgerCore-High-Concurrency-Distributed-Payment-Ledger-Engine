'use client';

import React, { useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { useDemoGuide } from '@/components/layout/DemoGuideContext';

export interface ThroughputPoint {
  label: string;
  rps: number;
  avgLatencyMs: number;
  settled: number;
  insufficientFunds: number;
  rateLimited: number;
  circuitOpen: number;
}

interface ThroughputChartProps {
  series: ThroughputPoint[];
}

export function ThroughputChart({ series }: ThroughputChartProps) {
  const { demoGuide } = useDemoGuide();
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Dynamic scales with clean minimum baselines matching spec (0..100+ RPS/Count, 0..200ms+ Latency)
  const rawMaxLeft = Math.max(
    100,
    ...series.map((p) =>
      Math.max(
        p.rps,
        p.settled + p.insufficientFunds + p.rateLimited + p.circuitOpen,
      ),
    ),
  );
  const maxLeft = Math.ceil(rawMaxLeft / 25) * 25;

  const rawMaxLatency = Math.max(200, ...series.map((p) => p.avgLatencyMs));
  const maxLatency = Math.ceil(rawMaxLatency / 50) * 50;

  // Live aggregate counters across the visible window
  const peakRps = series.length > 0 ? Math.max(...series.map((p) => p.rps)) : 0;
  const nonZeroLatencies = series.filter((p) => p.avgLatencyMs > 0);
  const avgLatency =
    nonZeroLatencies.length > 0
      ? nonZeroLatencies.reduce((sum, p) => sum + p.avgLatencyMs, 0) /
        nonZeroLatencies.length
      : 0;
  const totalSettled = series.reduce((sum, p) => sum + p.settled, 0);
  const totalFunds = series.reduce((sum, p) => sum + p.insufficientFunds, 0);
  const totalRateLimited = series.reduce((sum, p) => sum + p.rateLimited, 0);
  const totalCircuit = series.reduce((sum, p) => sum + p.circuitOpen, 0);

  // SVG geometry with room for Left Y-Axis, Right Y-Axis, and Bottom X-Axis
  const width = 820;
  const height = 240;
  const padLeft = 48;
  const padRight = 56;
  const padTop = 24;
  const padBottom = 28;
  const innerW = width - padLeft - padRight;
  const innerH = height - padTop - padBottom;

  const slotW = innerW / Math.max(1, series.length);
  const getCenterX = (i: number) =>
    series.length > 1 ? padLeft + i * slotW + slotW / 2 : padLeft + innerW / 2;

  const rpsPoints = series
    .map((pt, i) => {
      const x = getCenterX(i);
      const y = padTop + innerH - Math.min(1, pt.rps / maxLeft) * innerH;
      return `${x},${y}`;
    })
    .join(' ');

  const latencyPoints = series
    .map((pt, i) => {
      const x = getCenterX(i);
      const y =
        padTop + innerH - Math.min(1, pt.avgLatencyMs / maxLatency) * innerH;
      return `${x},${y}`;
    })
    .join(' ');

  const leftTicks = [0, 0.25, 0.5, 0.75, 1];
  const rightTicks = [0, 0.25, 0.5, 0.75, 1];

  const hoveredPoint =
    hoveredIdx !== null && hoveredIdx >= 0 && hoveredIdx < series.length
      ? series[hoveredIdx]
      : null;

  const tooltipLeftPct =
    hoveredIdx !== null && series.length > 0
      ? ((getCenterX(hoveredIdx) - padLeft) / innerW) * 100
      : 50;

  return (
    <section className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4">
      {demoGuide && (
        <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-xs">
          <span className="font-mono font-bold text-indigo-300 bg-indigo-500/20 px-2 py-0.5 rounded">
            Step 3: View Telemetry
          </span>
          <span className="text-slate-300">
            Watch real-time RPS &amp; latency curves alongside stacked HTTP outcome bars.
          </span>
        </div>
      )}

      {/* Header + Live Summary Pills */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-2">
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-cyan-400" />
              Real-Time Throughput &amp; Outcome Telemetry
            </h2>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Live RPS &amp; Avg Latency curves overlaid on HTTP outcome breakdown
            </p>
          </div>

          {/* Live Aggregate Counters */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-mono">
            <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              Peak RPS: <strong className="text-cyan-200">{peakRps.toFixed(1)}</strong>
            </span>
            <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/30">
              Avg Latency: <strong className="text-purple-200">{avgLatency.toFixed(1)}ms</strong>
            </span>
            <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
              Settled: <strong className="text-emerald-200">{totalSettled}</strong>
            </span>
            <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30">
              422 Funds: <strong className="text-amber-200">{totalFunds}</strong>
            </span>
            <span className="px-2 py-0.5 rounded bg-orange-500/10 text-orange-300 border border-orange-500/30">
              429 Rate-Limited: <strong className="text-orange-200">{totalRateLimited}</strong>
            </span>
            <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/30">
              503 Circuit: <strong className="text-rose-200">{totalCircuit}</strong>
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono text-slate-300">
          <span className="flex items-center gap-1.5 text-cyan-400">
            <span className="w-3 h-0.5 bg-cyan-400 inline-block" /> RPS
          </span>
          <span className="flex items-center gap-1.5 text-purple-400">
            <span className="w-3 h-0 border-t-2 border-dashed border-purple-400 inline-block" /> Avg Latency (ms)
          </span>
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/80 inline-block" /> Settled (200)
          </span>
          <span className="flex items-center gap-1.5 text-amber-400">
            <span className="w-2.5 h-2.5 rounded-sm bg-amber-500/85 inline-block" /> Insufficient Funds (422)
          </span>
          <span className="flex items-center gap-1.5 text-orange-400">
            <span className="w-2.5 h-2.5 rounded-sm bg-orange-500/85 inline-block" /> Rate Limited (429)
          </span>
          <span className="flex items-center gap-1.5 text-rose-400">
            <span className="w-2.5 h-2.5 rounded-sm bg-rose-500/85 inline-block" /> Circuit Open (503)
          </span>
        </div>
      </div>

      {/* Chart + Interactive Hover Tooltip */}
      <div
        className="relative w-full"
        onMouseLeave={() => setHoveredIdx(null)}
      >
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-60 select-none overflow-visible">
          {/* Axis Header Labels */}
          <text
            x={padLeft}
            y={12}
            textAnchor="start"
            className="fill-cyan-400/80 text-[9px] font-mono uppercase"
          >
            Req / RPS
          </text>
          <text
            x={width - padRight}
            y={12}
            textAnchor="end"
            className="fill-purple-400/80 text-[9px] font-mono uppercase"
          >
            Latency (ms)
          </text>

          {/* Horizontal Grid Lines + Left & Right Y-Axis Ticks */}
          {leftTicks.map((frac, idx) => {
            const y = padTop + innerH * (1 - frac);
            const leftVal = Math.round(maxLeft * frac);
            const rightVal = Math.round(maxLatency * rightTicks[idx]);
            const isTop = frac === 1;
            return (
              <g key={frac}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={width - padRight}
                  y2={y}
                  stroke={frac === 0 ? '#334155' : '#1e293b'}
                  strokeDasharray={frac === 0 ? undefined : '3 3'}
                />
                {/* Left Y-Axis Label */}
                <text
                  x={padLeft - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-slate-400 text-[10px] font-mono"
                >
                  {isTop ? `${leftVal}+` : leftVal}
                </text>
                {/* Right Y-Axis Label */}
                <text
                  x={width - padRight + 8}
                  y={y + 3}
                  textAnchor="start"
                  className="fill-purple-300/80 text-[10px] font-mono"
                >
                  {isTop ? `${rightVal}ms+` : `${rightVal}ms`}
                </text>
              </g>
            );
          })}

          {/* Vertical Hover Crosshair */}
          {hoveredIdx !== null && hoveredIdx >= 0 && hoveredIdx < series.length && (
            <line
              x1={getCenterX(hoveredIdx)}
              y1={padTop}
              x2={getCenterX(hoveredIdx)}
              y2={padTop + innerH}
              stroke="#64748b"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
          )}

          {/* Stacked Outcome Bars (Settled -> 422 Funds -> 429 Rate Limited -> 503 Circuit Open) */}
          {series.map((pt, i) => {
            const barW = Math.max(6, Math.min(20, slotW * 0.48));
            const x = getCenterX(i) - barW / 2;
            const baselineY = padTop + innerH;

            const scaleH = (count: number) =>
              Math.min(innerH, (count / maxLeft) * innerH);

            const settledH = scaleH(pt.settled);
            const fundsH = scaleH(pt.insufficientFunds);
            const rateH = scaleH(pt.rateLimited);
            const circuitH = scaleH(pt.circuitOpen);

            const ySettled = baselineY - settledH;
            const yFunds = ySettled - fundsH;
            const yRate = yFunds - rateH;
            const yCircuit = yRate - circuitH;

            const isHovered = hoveredIdx === i;

            return (
              <g key={`${pt.label}-${i}`} opacity={hoveredIdx === null || isHovered ? 1 : 0.65}>
                {settledH > 0 && (
                  <rect
                    x={x}
                    y={ySettled}
                    width={barW}
                    height={settledH}
                    rx={1.5}
                    fill="rgba(16, 185, 129, 0.78)"
                  />
                )}
                {fundsH > 0 && (
                  <rect
                    x={x}
                    y={yFunds}
                    width={barW}
                    height={fundsH}
                    rx={1.5}
                    fill="rgba(245, 158, 11, 0.85)"
                  />
                )}
                {rateH > 0 && (
                  <rect
                    x={x}
                    y={yRate}
                    width={barW}
                    height={rateH}
                    rx={1.5}
                    fill="rgba(249, 115, 22, 0.85)"
                  />
                )}
                {circuitH > 0 && (
                  <rect
                    x={x}
                    y={yCircuit}
                    width={barW}
                    height={circuitH}
                    rx={1.5}
                    fill="rgba(239, 68, 68, 0.88)"
                  />
                )}
              </g>
            );
          })}

          {/* Avg Latency Polyline (Dashed Purple) */}
          {series.length > 1 && (
            <polyline
              fill="none"
              stroke="#a855f7"
              strokeWidth="2"
              strokeDasharray="5 4"
              strokeLinejoin="round"
              strokeLinecap="round"
              points={latencyPoints}
            />
          )}

          {/* RPS Polyline (Solid Cyan) */}
          {series.length > 1 && (
            <polyline
              fill="none"
              stroke="#22d3ee"
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
              points={rpsPoints}
            />
          )}

          {/* Hovered Data Point Markers */}
          {hoveredIdx !== null && hoveredPoint && (
            <g>
              <circle
                cx={getCenterX(hoveredIdx)}
                cy={
                  padTop +
                  innerH -
                  Math.min(1, hoveredPoint.rps / maxLeft) * innerH
                }
                r={4}
                fill="#22d3ee"
                stroke="#0f172a"
                strokeWidth={1.5}
              />
              <circle
                cx={getCenterX(hoveredIdx)}
                cy={
                  padTop +
                  innerH -
                  Math.min(1, hoveredPoint.avgLatencyMs / maxLatency) * innerH
                }
                r={4}
                fill="#a855f7"
                stroke="#0f172a"
                strokeWidth={1.5}
              />
            </g>
          )}

          {/* Bottom X-Axis Timestamps (HH:MM:SS) */}
          {series.map((pt, i) => {
            const step = Math.max(1, Math.ceil(series.length / 6));
            const showLabel = i % step === 0 || i === series.length - 1;
            if (!showLabel) return null;
            return (
              <text
                key={`xlabel-${pt.label}-${i}`}
                x={getCenterX(i)}
                y={height - 6}
                textAnchor="middle"
                className="fill-slate-400 text-[10px] font-mono"
              >
                {pt.label}
              </text>
            );
          })}

          {/* Invisible Interactive Hover Columns */}
          {series.map((pt, i) => (
            <rect
              key={`hover-slot-${pt.label}-${i}`}
              x={padLeft + i * slotW}
              y={padTop}
              width={slotW}
              height={innerH}
              fill="transparent"
              className="cursor-crosshair"
              onMouseEnter={() => setHoveredIdx(i)}
            />
          ))}
        </svg>

        {/* Interactive Dark Tooltip Card */}
        {hoveredPoint && (
          <div
            className="pointer-events-none absolute top-4 z-20 w-56 rounded-lg border border-slate-700 bg-slate-950/95 p-3 text-[11px] font-mono shadow-xl backdrop-blur"
            style={{
              left:
                tooltipLeftPct > 65
                  ? `calc(${tooltipLeftPct}% - 15rem)`
                  : `calc(${tooltipLeftPct}% + 1rem)`,
            }}
          >
            <div className="mb-1.5 flex items-center justify-between border-b border-slate-800 pb-1 text-slate-300">
              <span className="text-slate-400">Time</span>
              <span className="font-bold text-white">{hoveredPoint.label}</span>
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-cyan-400">RPS</span>
                <span className="font-semibold text-white">
                  {hoveredPoint.rps.toFixed(1)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-purple-400">Avg Latency</span>
                <span className="font-semibold text-white">
                  {hoveredPoint.avgLatencyMs.toFixed(1)} ms
                </span>
              </div>
              <div className="my-1 border-t border-slate-800/80" />
              <div className="flex items-center justify-between">
                <span className="text-emerald-400">Settled (200)</span>
                <span className="font-semibold text-emerald-300">
                  {hoveredPoint.settled}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-amber-400">Insufficient Funds (422)</span>
                <span className="font-semibold text-amber-300">
                  {hoveredPoint.insufficientFunds}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-orange-400">Rate Limited (429)</span>
                <span className="font-semibold text-orange-300">
                  {hoveredPoint.rateLimited}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-rose-400">Circuit Open (503)</span>
                <span className="font-semibold text-rose-300">
                  {hoveredPoint.circuitOpen}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
