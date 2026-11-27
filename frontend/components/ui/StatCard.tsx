import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string;
  subtext: string;
  icon: LucideIcon;
  tone?: 'emerald' | 'blue' | 'indigo' | 'amber' | 'rose';
  trend?: string;
}

const toneStyles = {
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
  blue: { bg: 'bg-blue-50', text: 'text-blue-600' },
  indigo: { bg: 'bg-indigo-50', text: 'text-indigo-600' },
  amber: { bg: 'bg-amber-50', text: 'text-amber-600' },
  rose: { bg: 'bg-rose-50', text: 'text-rose-600' },
};

export function StatCard({ label, value, subtext, icon: Icon, tone = 'indigo', trend }: StatCardProps) {
  const { bg, text } = toneStyles[tone];
  return (
    <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</span>
        <div className={`p-2 rounded-lg ${bg} ${text}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <div className="mt-4">
        <div className="text-2xl font-extrabold text-slate-900 font-mono tracking-tight">{value}</div>
        <p className="text-xs text-slate-500 mt-1 flex items-center justify-between">
          <span>{subtext}</span>
          {trend && <span className="font-semibold text-emerald-600">{trend}</span>}
        </p>
      </div>
    </div>
  );
}
