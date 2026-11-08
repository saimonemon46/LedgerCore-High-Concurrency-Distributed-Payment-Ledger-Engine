-- Production PostgreSQL Schema for Double-Entry Financial Ledgers
-- Enforces:
-- 1. Exact 2-decimal scale currency precision matching Money VO (rejects unquantized inputs).
-- 2. Non-negative, finite account balances (rejects NaN, +Infinity, -Infinity).
-- 3. Append-only journal records referencing parent transactions (blocks UPDATE, DELETE, TRUNCATE).
-- 4. Cross-row zero-drift transaction balance via deferred constraint trigger.
-- 5. Participant integrity (entries restricted to sender, receiver, and designated fee account).
-- 6. Settlement verification (SETTLED transactions must have matching debit, credit & zero drift).
-- 7. Currency immutability once ledger entries are appended (both transaction and account sides).
-- 8. Terminal state protection for SETTLED transactions.
-- 9. Idempotency uniqueness constraints.

CREATE TABLE IF NOT EXISTS accounts (
    account_id VARCHAR(64) PRIMARY KEY,
    owner_name VARCHAR(255) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    balance NUMERIC NOT NULL DEFAULT 0.00,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_account_balance_finite CHECK (balance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    CONSTRAINT chk_account_balance_non_negative CHECK (balance >= 0),
    CONSTRAINT chk_account_balance_scale CHECK (SCALE(balance) <= 2)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'default',
    idempotency_key VARCHAR(128) NOT NULL,
    from_account_id VARCHAR(64) NOT NULL REFERENCES accounts(account_id),
    to_account_id VARCHAR(64) NOT NULL REFERENCES accounts(account_id),
    fee_account_id VARCHAR(64) REFERENCES accounts(account_id),
    amount NUMERIC NOT NULL,
    fee NUMERIC NOT NULL DEFAULT 0.00,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'INITIATED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_tx_amount_finite CHECK (
        amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)
        AND fee NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)
    ),
    CONSTRAINT chk_tx_amount_positive CHECK (amount > 0 AND fee >= 0),
    CONSTRAINT chk_tx_amount_scale CHECK (SCALE(amount) <= 2 AND SCALE(fee) <= 2),
    CONSTRAINT uq_transactions_tenant_idempotency UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id VARCHAR(64) PRIMARY KEY,
    transaction_id VARCHAR(64) NOT NULL REFERENCES transactions(transaction_id) ON DELETE RESTRICT,
    account_id VARCHAR(64) NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    entry_type VARCHAR(10) NOT NULL CHECK (entry_type IN ('DEBIT', 'CREDIT')),
    amount NUMERIC NOT NULL, -- Negative for DEBIT, Positive for CREDIT
    balance_after NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_entry_sign CHECK (
        (entry_type = 'DEBIT' AND amount <= 0) OR (entry_type = 'CREDIT' AND amount >= 0)
    ),
    CONSTRAINT chk_entry_amount_finite CHECK (
        amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)
        AND balance_after NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)
    ),
    CONSTRAINT chk_entry_amount_scale CHECK (SCALE(amount) <= 2 AND SCALE(balance_after) <= 2)
);

CREATE OR REPLACE FUNCTION forbid_ledger_entries_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ledger_entries is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_entries_append_only ON ledger_entries;
CREATE TRIGGER trg_ledger_entries_append_only
    BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION forbid_ledger_entries_mutation();

DROP TRIGGER IF EXISTS trg_ledger_entries_forbid_truncate ON ledger_entries;
CREATE TRIGGER trg_ledger_entries_forbid_truncate
    BEFORE TRUNCATE ON ledger_entries
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_ledger_entries_mutation();

-- Enforce double-entry zero-sum conservation across all entries in each transaction at commit
CREATE OR REPLACE FUNCTION verify_transaction_balance_on_commit() RETURNS trigger AS $$
DECLARE
    net_drift NUMERIC;
BEGIN
    SELECT COALESCE(SUM(amount), 0.00) INTO net_drift
    FROM ledger_entries
    WHERE transaction_id = NEW.transaction_id;

    IF net_drift <> 0.00 THEN
        RAISE EXCEPTION 'Double-entry balance violation: net drift for transaction % is % (must be 0.00)',
            NEW.transaction_id, net_drift;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_entries_verify_balance ON ledger_entries;
CREATE CONSTRAINT TRIGGER trg_ledger_entries_verify_balance
    AFTER INSERT ON ledger_entries
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION verify_transaction_balance_on_commit();

-- Validate that ledger entries reference allowed transaction participants and matching currencies
-- Acquires row lock FOR UPDATE on transaction to serialize concurrent insertions with settlement
CREATE OR REPLACE FUNCTION verify_ledger_entry_participants() RETURNS trigger AS $$
DECLARE
    tx RECORD;
    acc RECORD;
BEGIN
    SELECT * INTO tx FROM transactions WHERE transaction_id = NEW.transaction_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Transaction % does not exist', NEW.transaction_id;
    END IF;

    IF tx.status = 'SETTLED' THEN
        RAISE EXCEPTION 'Cannot append ledger entries to already SETTLED transaction %', NEW.transaction_id;
    END IF;

    SELECT * INTO acc FROM accounts WHERE account_id = NEW.account_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Account % does not exist', NEW.account_id;
    END IF;

    IF acc.currency <> tx.currency THEN
        RAISE EXCEPTION 'Currency mismatch: account % has currency % but transaction is in %',
            acc.account_id, acc.currency, tx.currency;
    END IF;

    -- Only sender, receiver, and designated fee account are permitted
    IF NEW.account_id NOT IN (tx.from_account_id, tx.to_account_id, COALESCE(tx.fee_account_id, '')) THEN
        RAISE EXCEPTION 'Account % is not a valid participant for transaction %',
            NEW.account_id, NEW.transaction_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_entries_validate_participant ON ledger_entries;
CREATE TRIGGER trg_ledger_entries_validate_participant
    BEFORE INSERT ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION verify_ledger_entry_participants();

-- Prevent currency mutation once ledger entries exist (transaction side)
CREATE OR REPLACE FUNCTION forbid_transaction_currency_mutation() RETURNS trigger AS $$
BEGIN
    IF OLD.currency <> NEW.currency THEN
        IF EXISTS (SELECT 1 FROM ledger_entries WHERE transaction_id = OLD.transaction_id) THEN
            RAISE EXCEPTION 'Cannot modify currency of transaction % with existing ledger entries', OLD.transaction_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_transactions_currency_immutable ON transactions;
CREATE TRIGGER trg_transactions_currency_immutable
    BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION forbid_transaction_currency_mutation();

-- Prevent currency mutation once ledger entries exist (account side)
CREATE OR REPLACE FUNCTION forbid_account_currency_mutation() RETURNS trigger AS $$
BEGIN
    IF OLD.currency <> NEW.currency THEN
        IF EXISTS (SELECT 1 FROM ledger_entries WHERE account_id = OLD.account_id) THEN
            RAISE EXCEPTION 'Cannot modify currency of account % with existing ledger entries', OLD.account_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_accounts_currency_immutable ON accounts;
CREATE TRIGGER trg_accounts_currency_immutable
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION forbid_account_currency_mutation();

-- Validate that SETTLED transactions have exact matching journal entries, terminal status, and zero net drift
CREATE OR REPLACE FUNCTION verify_settled_transaction_on_commit() RETURNS trigger AS $$
DECLARE
    entry_count INT;
    expected_count INT;
    net_drift NUMERIC;
    sender_debit NUMERIC;
    receiver_credit NUMERIC;
    fee_credit NUMERIC;
BEGIN
    -- Protect settled transactions from mutation out of SETTLED (except valid REVERSED transition) or financial tampering
    IF TG_OP = 'UPDATE' AND OLD.status = 'SETTLED' THEN
        IF NEW.status NOT IN ('SETTLED', 'REVERSED') THEN
            RAISE EXCEPTION 'Cannot transition transaction % out of SETTLED status except to REVERSED', OLD.transaction_id;
        END IF;
        IF NEW.amount <> OLD.amount
           OR NEW.fee <> OLD.fee
           OR NEW.from_account_id <> OLD.from_account_id
           OR NEW.to_account_id <> OLD.to_account_id
           OR NEW.fee_account_id IS DISTINCT FROM OLD.fee_account_id THEN
            RAISE EXCEPTION 'Cannot modify financial fields of already SETTLED transaction %', OLD.transaction_id;
        END IF;
    END IF;

    IF NEW.status = 'SETTLED' THEN
        expected_count := CASE WHEN NEW.fee > 0.00 THEN 3 ELSE 2 END;

        SELECT
            COUNT(*),
            COALESCE(SUM(amount), 0.00),
            COALESCE(SUM(CASE WHEN account_id = NEW.from_account_id AND entry_type = 'DEBIT' THEN amount ELSE 0 END), 0.00),
            COALESCE(SUM(CASE WHEN account_id = NEW.to_account_id AND entry_type = 'CREDIT' THEN amount ELSE 0 END), 0.00),
            COALESCE(SUM(CASE WHEN NEW.fee_account_id IS NOT NULL AND account_id = NEW.fee_account_id AND entry_type = 'CREDIT' THEN amount ELSE 0 END), 0.00)
        INTO entry_count, net_drift, sender_debit, receiver_credit, fee_credit
        FROM ledger_entries
        WHERE transaction_id = NEW.transaction_id;

        IF entry_count <> expected_count THEN
            RAISE EXCEPTION 'Settled transaction % must have exactly % balanced ledger entries (found %)',
                NEW.transaction_id, expected_count, entry_count;
        END IF;

        IF net_drift <> 0.00 THEN
            RAISE EXCEPTION 'Double-entry balance violation: net drift for transaction % is % (must be 0.00)',
                NEW.transaction_id, net_drift;
        END IF;

        IF receiver_credit <> NEW.amount THEN
            RAISE EXCEPTION 'Receiver credit % does not match transaction amount %',
                receiver_credit, NEW.amount;
        END IF;

        IF abs(sender_debit) <> (NEW.amount + NEW.fee) THEN
            RAISE EXCEPTION 'Sender debit % does not match total debit (amount + fee) %',
                abs(sender_debit), (NEW.amount + NEW.fee);
        END IF;

        IF NEW.fee > 0.00 AND fee_credit <> NEW.fee THEN
            RAISE EXCEPTION 'Fee credit % does not match transaction fee %',
                fee_credit, NEW.fee;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_transactions_verify_settled ON transactions;
CREATE CONSTRAINT TRIGGER trg_transactions_verify_settled
    AFTER INSERT OR UPDATE ON transactions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION verify_settled_transaction_on_commit();

CREATE INDEX IF NOT EXISTS idx_ledger_entries_account_created
    ON ledger_entries(account_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_tx
    ON ledger_entries(transaction_id);

CREATE TABLE IF NOT EXISTS idempotency_records (
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'default',
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_until TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, idempotency_key)
);
