-- Supabase Database Schema for Retail AI Agent
-- Run this in your Supabase SQL Editor

-- ============================================
-- 1. CHAT HISTORY TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS chat_history (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexes for fast queries
    INDEX idx_chat_session (session_id),
    INDEX idx_chat_customer (customer_id),
    INDEX idx_chat_created (created_at DESC)
);

-- ============================================
-- 2. CUSTOMERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS customers (
    id BIGSERIAL PRIMARY KEY,
    customer_id TEXT UNIQUE NOT NULL,
    name TEXT,
    email TEXT,
    phone TEXT,
    loyalty_points INTEGER DEFAULT 0,
    loyalty_tier TEXT DEFAULT 'Bronze' CHECK (loyalty_tier IN ('Bronze', 'Silver', 'Gold', 'Platinum')),
    total_spent NUMERIC(10, 2) DEFAULT 0,
    birthday DATE,
    preferences JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    INDEX idx_customer_id (customer_id),
    INDEX idx_customer_email (email),
    INDEX idx_customer_tier (loyalty_tier)
);

-- ============================================
-- 3. ORDERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT UNIQUE NOT NULL,
    customer_id TEXT NOT NULL,
    items JSONB NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    fulfillment_type TEXT NOT NULL,
    delivery_address JSONB,
    tracking_number TEXT,
    shipping_partner JSONB,
    estimated_delivery JSONB,
    status_history JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    INDEX idx_order_id (order_id),
    INDEX idx_order_customer (customer_id),
    INDEX idx_order_status (status),
    INDEX idx_order_created (created_at DESC)
);

-- ============================================
-- 4. COUPONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS coupons (
    id BIGSERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    description TEXT,
    discount_type TEXT NOT NULL CHECK (discount_type IN ('percentage', 'flat')),
    discount_value NUMERIC(10, 2) NOT NULL,
    min_purchase NUMERIC(10, 2) DEFAULT 0,
    max_discount NUMERIC(10, 2),
    min_tier_required INTEGER DEFAULT 0, -- 0=Bronze, 1=Silver, 2=Gold, 3=Platinum
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    usage_limit INTEGER,
    times_used INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    INDEX idx_coupon_code (code),
    INDEX idx_coupon_active (active),
    INDEX idx_coupon_validity (valid_from, valid_until)
);

-- ============================================
-- 5. COUPON USAGE TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS coupon_usage (
    id BIGSERIAL PRIMARY KEY,
    coupon_id BIGINT REFERENCES coupons(id),
    customer_id TEXT NOT NULL,
    order_id TEXT,
    discount_applied NUMERIC(10, 2),
    used_at TIMESTAMPTZ DEFAULT NOW(),
    
    INDEX idx_usage_customer (customer_id),
    INDEX idx_usage_coupon (coupon_id)
);

-- ============================================
-- 6. RETURNS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS returns (
    id BIGSERIAL PRIMARY KEY,
    return_id TEXT UNIQUE NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    items JSONB NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested',
    refund_amount NUMERIC(10, 2),
    status_history JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    INDEX idx_return_id (return_id),
    INDEX idx_return_customer (customer_id),
    INDEX idx_return_order (order_id)
);

-- ============================================
-- FUNCTIONS
-- ============================================

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for auto-updating updated_at
CREATE TRIGGER update_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_returns_updated_at
    BEFORE UPDATE ON returns
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- SAMPLE DATA
-- ============================================

-- Insert sample customer
INSERT INTO customers (customer_id, name, email, phone, loyalty_points, loyalty_tier, total_spent, birthday)
VALUES 
    ('cust_manor', 'Manor Customer', 'manor@example.com', '+919876543210', 500, 'Silver', 25000.00, '1990-06-15'),
    ('streamlit_user', 'Streamlit User', 'streamlit@example.com', '+919876543211', 200, 'Bronze', 5000.00, '1995-03-20')
ON CONFLICT (customer_id) DO NOTHING;

-- Insert sample coupons
INSERT INTO coupons (code, description, discount_type, discount_value, min_purchase, max_discount, min_tier_required, valid_from, valid_until, usage_limit)
VALUES 
    ('WELCOME10', '10% off for new customers', 'percentage', 10.00, 500.00, 500.00, 0, NOW(), NOW() + INTERVAL '30 days', 100),
    ('SAVE500', 'Flat ₹500 off', 'flat', 500.00, 2000.00, NULL, 0, NOW(), NOW() + INTERVAL '30 days', 200),
    ('SILVER15', '15% off for Silver+ members', 'percentage', 15.00, 1000.00, 1000.00, 1, NOW(), NOW() + INTERVAL '30 days', 50),
    ('GOLD20', '20% off for Gold+ members', 'percentage', 20.00, 1500.00, 2000.00, 2, NOW(), NOW() + INTERVAL '30 days', 30)
ON CONFLICT (code) DO NOTHING;

-- ============================================
-- ROW LEVEL SECURITY (Optional but recommended)
-- ============================================

-- Enable RLS
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE coupons ENABLE ROW LEVEL SECURITY;
ALTER TABLE returns ENABLE ROW LEVEL SECURITY;

-- Create policies (allow all for service key, restrict for anon)
CREATE POLICY "Enable read access for all users" ON chat_history FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON chat_history FOR INSERT WITH CHECK (true);

CREATE POLICY "Enable read access for all users" ON customers FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON customers FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update access for all users" ON customers FOR UPDATE USING (true);

CREATE POLICY "Enable read access for all users" ON orders FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON orders FOR INSERT WITH CHECK (true);

CREATE POLICY "Enable read access for all users" ON coupons FOR SELECT USING (true);

CREATE POLICY "Enable read access for all users" ON returns FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON returns FOR INSERT WITH CHECK (true);

-- ============================================
-- VERIFICATION QUERIES
-- ============================================

-- Check tables created
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Check sample data
SELECT * FROM customers LIMIT 5;
SELECT * FROM coupons WHERE active = true;

-- Success message
SELECT 'Database schema created successfully!' AS message;
