'use client';

import React from 'react';
import { BarChart3 } from 'lucide-react';

export interface ThroughputPoint {
  label: string;
  rps: number;
  success: number;
  rejected: number;
}

interface ThroughputChartProps {
  series: ThroughputPoint[];
}

export function ThroughputChart({ series }: ThroughputChartProps) {
  const maxRps = Math.max(10, ...series.map((p) => p.rps));
  const maxCount = Math.max(5, ...series.map((p) => p.success + p.rejected));

  const width = 760;
  const height = 180;
  const padX = 28;
  const padY = 18;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const rpsPoints = series
    .map((pt, i) => {
      const x = padX + (series.length > 1 ? (i / (series.length - 1)) * innerW : innerW / 2);
      const y = padY + innerH - (pt.rps / maxRps) * innerH;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <section className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-cyan-400" />
            Real-Time Throughput &amp; Outcome Telemetry
          </h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Live Requests/sec curve alongside Settled vs Rejected transaction volume
          </p>
        </div>

        <div className="flex items-center gap-4 text-[11px] font-mono">
          <span className="flex items-center gap-1.5 text-cyan-400">
            <span className="w-2.5 h-0.5 bg-cyan-400 inline-block" /> RPS
          </span>
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/70 inline-block" /> Settled
          </span>
          <span className="flex items-center gap-1.5 text-rose-400">
            <span className="w-2.5 h-2.5 rounded-sm bg-rose-500/70 inline-block" /> Rejected
          </span>
        </div>
      </div>

      <div className="w-full overflow-hidden">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-44 select-none">
          {/* Grid lines */}
          {[0.25, 0.5, 0.75, 1].map((frac) => {
            const y = padY + innerH * (1 - frac);
            return (
              <line
                key={frac}
                x1={padX}
                y1={y}
                x2={width - padX}
                y2={y}
                stroke="#1e293b"
                strokeDasharray="3 3"
              />
            );
          })}

          {/* Bars for Success & Rejected */}
          {series.map((pt, i) => {
            const slotW = innerW / Math.max(1, series.length);
            const barW = Math.max(4, Math.min(18, slotW * 0.45));
            const x = padX + i * slotW + (slotW - barW) / 2;
            const successH = (pt.success / maxCount) * innerH * 0.7;
            const rejectedH = (pt.rejected / maxCount) * innerH * 0.7;
            return (
              <g key={`${pt.label}-${i}`}>
                <rect
                  x={x}
                  y={padY + innerH - successH}
                  width={barW}
                  height={successH}
                  rx={2}
                  fill="rgba(16, 185, 129, 0.45)"
                />
                {rejectedH > 0 && (
                  <rect
                    x={x}
                    y={padY + innerH - successH - rejectedH}
                    width={barW}
                    height={rejectedH}
                    rx={2}
                    fill="rgba(244, 63, 94, 0.65)"
                  />
                )}
              </g>
            );
          })}

          {/* RPS Polyline */}
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
        </svg>
      </div>
    </section>
  );
}
