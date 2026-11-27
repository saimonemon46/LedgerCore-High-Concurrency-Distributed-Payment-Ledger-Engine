'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { ShieldCheck, RefreshCw, Activity, Database, Check } from 'lucide-react';
import { api } from '@/lib/api';

export function Topbar() {
  const [resetting, setResetting] = useState(false);
  const [resetDone, setResetDone] = useState(false);

  const handleResetDemo = () => {
    setResetting(true);
    api.resetDemo();
    setTimeout(() => {
      setResetting(false);
      setResetDone(true);
      setTimeout(() => {
        setResetDone(false);
        window.location.reload();
      }, 800);
    }, 600);
  };

  return (
    <header className="bg-slate-900 border-b border-slate-800 text-white sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        {/* Left: Brand & Workspace */}
        <div className="flex items-center space-x-3 sm:space-x-4">
          <Link href="/console" className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-base shadow-sm ring-1 ring-indigo-400/30">
              LC
            </div>
            <div>
              <span className="font-bold text-base tracking-tight block">LedgerCore Console</span>
              <span className="text-[10px] text-indigo-400 font-semibold tracking-wider uppercase block">
                Distributed Financial Engine
              </span>
            </div>
          </Link>

          <div className="hidden md:flex items-center space-x-2 pl-3 border-l border-slate-800">
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-200 border border-slate-700">
              Northstar Demo Payments
            </span>
            <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              SANDBOX SIMULATOR
            </span>
          </div>
        </div>

        {/* Right: Engine Telemetry & Actions */}
        <div className="flex items-center space-x-3">
          <div className="hidden lg:flex items-center space-x-2 text-xs font-mono text-slate-400 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span>RabbitMQ: Active</span>
            <span className="text-slate-600">|</span>
            <span className="text-emerald-400">0 Outbox Lag</span>
          </div>

          <button
            onClick={handleResetDemo}
            disabled={resetting || resetDone}
            className="inline-flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-700 transition"
            title="Reset sandbox balances and accounts to initial state"
          >
            {resetDone ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>Reset!</span>
              </>
            ) : (
              <>
                <RefreshCw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
                <span className="hidden sm:inline">Reset Sandbox</span>
              </>
            )}
          </button>

          <Link
            href="/docs"
            className="text-xs font-medium text-slate-400 hover:text-white px-2 py-1 rounded transition"
          >
            Docs
          </Link>
        </div>
      </div>
    </header>
  );
}
