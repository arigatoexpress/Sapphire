-- Sapphire Trading Database Schema
-- PostgreSQL 15

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Proposals table - tracks all trade proposals
CREATE TABLE IF NOT EXISTS proposals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    proposal_id VARCHAR(32) UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    amount_usd DECIMAL(10,2) NOT NULL,
    confidence DECIMAL(5,4) CHECK (confidence >= 0 AND confidence <= 1),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'analyzing', 'approved', 'rejected', 'executed', 'failed', 'cancelled')),
    strategy_name VARCHAR(100),
    source VARCHAR(50),
    ai_analysis JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    executed_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Trades table - tracks executed trades
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    proposal_id VARCHAR(32) REFERENCES proposals(proposal_id),
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) DEFAULT 'market',
    quantity DECIMAL(20,8) NOT NULL,
    price DECIMAL(20,8),
    total_value DECIMAL(20,8),
    fees DECIMAL(20,8) DEFAULT 0,
    net_proceeds DECIMAL(20,8),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'open', 'partially_filled', 'filled', 'cancelled', 'failed')),
    exchange_order_id VARCHAR(100),
    fill_percentage DECIMAL(5,2) DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    filled_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB
);

-- Positions table - tracks open positions
CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL UNIQUE,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL DEFAULT 0,
    avg_entry_price DECIMAL(20,8),
    current_price DECIMAL(20,8),
    unrealized_pnl DECIMAL(20,8),
    unrealized_pnl_percent DECIMAL(10,4),
    total_value DECIMAL(20,8),
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_trade_id UUID REFERENCES trades(id)
);

-- Daily P&L tracking
CREATE TABLE IF NOT EXISTS daily_pnl (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL UNIQUE,
    starting_balance DECIMAL(20,8),
    ending_balance DECIMAL(20,8),
    realized_pnl DECIMAL(20,8) DEFAULT 0,
    unrealized_pnl DECIMAL(20,8) DEFAULT 0,
    total_fees DECIMAL(20,8) DEFAULT 0,
    num_trades INTEGER DEFAULT 0,
    num_proposals INTEGER DEFAULT 0,
    win_rate DECIMAL(5,4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- System events/audit log
CREATE TABLE IF NOT EXISTS system_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info'
        CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical')),
    component VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Circuit breaker state
CREATE TABLE IF NOT EXISTS circuit_breakers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) UNIQUE NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'closed'
        CHECK (state IN ('closed', 'open', 'half_open')),
    failure_count INTEGER DEFAULT 0,
    last_failure_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE,
    opened_at TIMESTAMP WITH TIME ZONE,
    threshold INTEGER DEFAULT 5,
    timeout_seconds INTEGER DEFAULT 300,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_proposals_status ON proposals(status);
CREATE INDEX idx_proposals_symbol ON proposals(symbol);
CREATE INDEX idx_proposals_created_at ON proposals(created_at);
CREATE INDEX idx_proposals_status_created ON proposals(status, created_at);

CREATE INDEX idx_trades_proposal_id ON trades(proposal_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_created_at ON trades(created_at);
CREATE INDEX idx_trades_exchange_order_id ON trades(exchange_order_id);

CREATE INDEX idx_positions_symbol ON positions(symbol);

CREATE INDEX idx_daily_pnl_date ON daily_pnl(date);

CREATE INDEX idx_system_events_type ON system_events(event_type);
CREATE INDEX idx_system_events_severity ON system_events(severity);
CREATE INDEX idx_system_events_created ON system_events(created_at);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_proposals_updated_at BEFORE UPDATE ON proposals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_trades_updated_at BEFORE UPDATE ON trades
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_daily_pnl_updated_at BEFORE UPDATE ON daily_pnl
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_circuit_breakers_updated_at BEFORE UPDATE ON circuit_breakers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert initial circuit breaker states
INSERT INTO circuit_breakers (name, threshold, timeout_seconds) VALUES
    ('daily_loss_limit', 1, 86400),  -- 24 hours
    ('consecutive_failures', 3, 300),  -- 5 minutes
    ('api_rate_limit', 10, 60),  -- 1 minute
    ('vpn_disconnect', 1, 0)  -- Immediate
ON CONFLICT (name) DO NOTHING;

-- Create view for open positions with current prices
CREATE OR REPLACE VIEW open_positions_view AS
SELECT
    p.*,
    p.quantity * p.current_price as market_value,
    p.quantity * (p.current_price - p.avg_entry_price) as unrealized_pnl_usd
FROM positions p
WHERE p.quantity != 0;

-- Create view for daily trading summary
CREATE OR REPLACE VIEW daily_trading_summary AS
SELECT
    DATE(p.created_at) as date,
    COUNT(*) as total_proposals,
    COUNT(*) FILTER (WHERE p.status = 'executed') as executed,
    COUNT(*) FILTER (WHERE p.status = 'rejected') as rejected,
    COUNT(*) FILTER (WHERE p.status = 'failed') as failed,
    AVG(p.confidence) as avg_confidence,
    COUNT(DISTINCT p.symbol) as unique_symbols
FROM proposals p
GROUP BY DATE(p.created_at)
ORDER BY date DESC;

-- Grant permissions (for service account)
-- Note: Run this after creating the service account
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO sapphire_service;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sapphire_service;

COMMENT ON TABLE proposals IS 'Trade proposals from various sources (Telegram, TradingView, AI)';
COMMENT ON TABLE trades IS 'Executed trades on exchanges';
COMMENT ON TABLE positions IS 'Current open positions';
COMMENT ON TABLE daily_pnl IS 'Daily profit/loss tracking';
COMMENT ON TABLE system_events IS 'System audit log and events';
COMMENT ON TABLE circuit_breakers IS 'Circuit breaker states for risk management';
