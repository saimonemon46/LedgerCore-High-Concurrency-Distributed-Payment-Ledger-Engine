import React from 'react';
import { CheckCircle2, Clock, XCircle, AlertTriangle, ShieldCheck } from 'lucide-react';
import { TransactionStatus, AccountStatus } from '@/types/api';

export function StatusBadge({ status }: { status: TransactionStatus | AccountStatus | string }) {
  switch (status) {
    case 'SETTLED':
    case 'ACTIVE':
    case 'COMPLETED_BALANCED':
    case 'DELIVERED':
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 flex items-center gap-1 w-max">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          {status}
        </span>
      );

    case 'PENDING':
    case 'RETRYING':
    case 'RUNNING':
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 flex items-center gap-1 w-max">
          <Clock className="w-3.5 h-3.5 text-amber-600 animate-spin" />
          {status}
        </span>
      );

    case 'FROZEN':
    case 'DISCREPANCY_DETECTED':
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-900 flex items-center gap-1 w-max">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-700" />
          {status}
        </span>
      );

    case 'REVERSED':
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-100 text-purple-800 flex items-center gap-1 w-max">
          <ShieldCheck className="w-3.5 h-3.5 text-purple-600" />
          REVERSED
        </span>
      );

    case 'FAILED':
    case 'REJECTED':
    case 'FAILED_DLQ':
    case 'SUSPENDED':
    default:
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 flex items-center gap-1 w-max">
          <XCircle className="w-3.5 h-3.5 text-rose-600" />
          {status}
        </span>
      );
  }
}
