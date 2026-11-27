import React from 'react';
import { ShieldCheck, Info } from 'lucide-react';

interface IdempotencyAlertProps {
  idempotencyKey: string;
  transactionId: string;
}

export function IdempotencyAlert({ idempotencyKey, transactionId }: IdempotencyAlertProps) {
  return (
    <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-start gap-3 shadow-sm">
      <div className="p-1.5 bg-emerald-100 rounded-lg text-emerald-700 flex-shrink-0 mt-0.5">
        <ShieldCheck className="w-5 h-5" />
      </div>
      <div className="text-sm">
        <h4 className="font-bold text-emerald-950 flex items-center gap-1.5">
          Request Idempotency Safeguard Triggered
        </h4>
        <p className="text-emerald-800 mt-1 leading-relaxed">
          Existing transaction <span className="font-mono font-bold text-emerald-900 bg-emerald-100/70 px-1.5 py-0.5 rounded">{transactionId}</span> was returned for key <span className="font-mono text-xs text-emerald-900 bg-emerald-100/70 px-1.5 py-0.5 rounded">{idempotencyKey}</span>.
        </p>
        <div className="mt-2 text-xs font-semibold text-emerald-700 flex items-center gap-1">
          <Info className="w-3.5 h-3.5" />
          Zero duplicate ledger postings were created. System balances remain strictly conserved.
        </div>
      </div>
    </div>
  );
}
