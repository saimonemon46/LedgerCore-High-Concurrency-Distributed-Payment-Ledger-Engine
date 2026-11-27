'use client';

import React from 'react';
import Link from 'next/link';
import {
  ShieldCheck,
  Zap,
  Lock,
  RefreshCw,
  Scale,
  ArrowRight,
  Database,
  Terminal,
  Cpu,
  CheckCircle2,
} from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white selection:bg-indigo-500 selection:text-white">
      {/* Top Navbar */}
      <header className="border-b border-slate-800/80 sticky top-0 z-50 backdrop-blur-md bg-slate-950/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-md">
              LC
            </div>
            <div>
              <span className="font-bold text-base tracking-tight block">LedgerCore</span>
              <span className="text-[10px] text-indigo-400 font-semibold tracking-wider uppercase block">
                Distributed Financial Engine
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-3 sm:space-x-4">
            <Link
              href="/docs"
              className="text-sm font-medium text-slate-300 hover:text-white transition px-3 py-1.5"
            >
              Architecture & API
            </Link>
            <Link
              href="/login"
              className="text-sm font-medium text-slate-300 hover:text-white transition px-3 py-1.5"
            >
              Sign In
            </Link>
            <Link
              href="/console"
              className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold px-4 py-2 rounded-lg shadow-sm transition"
            >
              Open Sandbox Console <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative pt-20 pb-24 overflow-hidden border-b border-slate-900">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-950/80 border border-indigo-700/40 text-indigo-300 text-xs font-semibold mb-6">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            Mathematical Invariant: 0.00 Financial Drift Under Concurrency
          </div>

          <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-white max-w-4xl mx-auto leading-tight">
            High-Concurrency Distributed Payment & Double-Entry Ledger Engine
          </h1>

          <p className="mt-6 text-lg sm:text-xl text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Engineered with Clean Architecture, canonical monotonic row-locking, exact decimal arithmetic, transactional outbox publishing, and automated reconciliation.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/console"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-6 py-3.5 rounded-xl shadow-lg shadow-indigo-600/30 transition text-base"
            >
              Launch Live Sandbox Console <ArrowRight className="w-5 h-5" />
            </Link>
            <Link
              href="/console/transfers/new"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-800 text-slate-200 font-semibold px-6 py-3.5 rounded-xl border border-slate-800 transition text-base"
            >
              <RefreshCw className="w-4 h-4 text-emerald-400" /> Test Idempotency Replay
            </Link>
          </div>

          {/* Systems Blueprint ASCII Box */}
          <div className="mt-14 text-left max-w-3xl mx-auto bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl overflow-x-auto font-mono text-xs text-slate-300">
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800 text-[11px] text-slate-500">
              <span className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-indigo-400" />
                SYSTEM TOPOLOGY & ATOMIC WRITE PIPELINE
              </span>
              <span className="text-emerald-400 font-semibold">PostgreSQL ACID Source of Truth</span>
            </div>
            <pre className="text-indigo-200/90 leading-relaxed">
{`Client Request (Idempotency-Key: idem_xxx)
      │
      ▼
┌──────────────┐
│ FastAPI API  │ ──> Resolve Tenant & Auth Boundary
└──────┬───────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ PostgreSQL Unit of Work (Pessimistic Row Locks)        │
│ 1. Canonical sort lock order: min(src,dest) -> max     │
│ 2. Deduct sender, credit receiver                      │
│ 3. Insert immutable double-entry journal (Σ = 0.00)     │
│ 4. Record idempotency lease & settled response         │
│ 5. Insert Transactional Outbox event                   │
└──────────────────────────┬─────────────────────────────┘
                           │ (Atomic Commit)
                           ▼
                  ┌─────────────────┐
                  │ Outbox Relay    │ ──> RabbitMQ Durable Queue
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Async Consumer  │ ──> Signed Webhook Delivery
                  └─────────────────┘`}
            </pre>
          </div>
        </div>
      </section>

      {/* Core Architectural Guarantees */}
      <section className="py-20 max-w-7xl mx-auto px-4 sm:px-6">
        <div className="text-center mb-14">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">Core Engineering Invariants</h2>
          <p className="text-slate-400 text-sm mt-2">Zero financial cheating. Every transaction is mathematically verifiable.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-slate-900/60 p-6 rounded-xl border border-slate-800/80">
            <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-400 w-max mb-4">
              <Scale className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-white">Strict Double-Entry Bookkeeping</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Every fund movement produces at least two balanced journal entries. Sum of debits and credits strictly equals zero. No single-column account balance increments.
            </p>
          </div>

          <div className="bg-slate-900/60 p-6 rounded-xl border border-slate-800/80">
            <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 w-max mb-4">
              <Lock className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-white">Canonical Lock Ordering</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Account locks are deterministically sorted (<code className="text-indigo-300">min(src,dest)</code> before <code className="text-indigo-300">max</code>) before executing <code className="text-indigo-300">SELECT FOR UPDATE</code>, mathematically preventing deadlock under bidirectional load.
            </p>
          </div>

          <div className="bg-slate-900/60 p-6 rounded-xl border border-slate-800/80">
            <div className="p-2.5 rounded-lg bg-purple-500/10 text-purple-400 w-max mb-4">
              <RefreshCw className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-white">Guaranteed Idempotency</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Durable idempotency keys guard every money-moving request. Network retries replay cached settled results without creating duplicate postings or double charges.
            </p>
          </div>
        </div>
      </section>

      {/* Footer Disclaimer */}
      <footer className="border-t border-slate-900 py-8 text-center text-xs text-slate-500">
        <p>LedgerCore Console — Built for Technical Recruiter & Engineering Demonstration.</p>
        <p className="mt-1">Uses simulated sandbox accounts only. Not a licensed banking or depository institution.</p>
      </footer>
    </div>
  );
}
