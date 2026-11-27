export type Currency = 'BDT' | 'USD' | 'EUR' | 'GBP';

export type AccountStatus = 'ACTIVE' | 'FROZEN' | 'SUSPENDED';
export type AccountType = 'CUSTOMER' | 'MERCHANT' | 'CLEARING' | 'FEE_REVENUE';

export interface Account {
  id: string;
  tenant_id: string;
  account_number: string;
  label: string;
  account_type: AccountType;
  currency: Currency;
  status: AccountStatus;
  balance: string; // Exact decimal string
  created_at: string;
}

export type TransactionStatus = 'DRAFT' | 'PENDING' | 'SETTLED' | 'REJECTED' | 'FAILED' | 'REVERSED';

export interface LedgerEntry {
  id: string;
  transaction_id: string;
  account_id: string;
  entry_type: 'DEBIT' | 'CREDIT';
  amount: string; // Exact decimal string
  currency: Currency;
  sequence_id: number;
  created_at: string;
}

export interface Transaction {
  id: string;
  tenant_id: string;
  idempotency_key: string;
  source_account_id: string;
  destination_account_id: string;
  amount: string;
  fee_amount: string;
  currency: Currency;
  status: TransactionStatus;
  reference_note?: string;
  created_at: string;
  postings?: LedgerEntry[];
  is_replayed?: boolean;
}

export interface ReconciliationRun {
  id: string;
  tenant_id: string;
  status: 'COMPLETED_BALANCED' | 'DISCREPANCY_DETECTED' | 'RUNNING';
  total_accounts_checked: number;
  total_journal_entries: number;
  net_drift_amount: string;
  currency: Currency;
  discrepancies: Array<{
    account_id: string;
    cached_balance: string;
    journal_sum: string;
    drift: string;
  }>;
  executed_by: string;
  started_at: string;
  finished_at: string;
}

export interface ApiKeyRecord {
  id: string;
  tenant_id: string;
  name: string;
  key_prefix: string;
  secret_preview?: string;
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  is_revoked: boolean;
}

export interface WebhookEndpoint {
  id: string;
  tenant_id: string;
  url: string;
  event_types: string[];
  status: 'ACTIVE' | 'DISABLED';
  secret_preview: string;
  created_at: string;
}

export interface WebhookDelivery {
  id: string;
  endpoint_id: string;
  event_type: string;
  status: 'DELIVERED' | 'RETRYING' | 'FAILED_DLQ';
  http_status: number;
  response_time_ms: number;
  attempt_count: number;
  created_at: string;
}

export interface OutboxStatus {
  relay_status: 'RUNNING' | 'DEGRADED' | 'STOPPED';
  pending_events: number;
  oldest_event_age_seconds: number;
  dlq_count: number;
  broker: 'RabbitMQ (Durable)';
}

export interface TelemetrySummary {
  status: 'healthy' | 'degraded';
  circuit_breaker_state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  rps: number;
  p95_latency_ms: number;
  outbox_lag: number;
  transfers_settled_total: number;
  transfers_failed_total: number;
  rate_limit_rejections_total: number;
  timestamp: number;
}

export interface TransferAttemptResult {
  index: number;
  status: number;
  outcome: 'SETTLED' | 'INSUFFICIENT_FUNDS' | 'RATE_LIMITED' | 'CIRCUIT_OPEN' | 'REPLAYED' | 'ERROR';
  latencyMs: number;
  requestId: string;
  transactionId?: string;
  detail?: string;
}
