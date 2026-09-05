-- =========================================================
-- Vento Mini App — Supabase PostgreSQL schema
-- Supabase SQL Editor ichida ishga tushiring
-- =========================================================

-- Foydalanuvchilar
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    expiry_date BIGINT DEFAULT 0,
    warned BOOLEAN DEFAULT FALSE,
    username TEXT,
    first_name TEXT,
    is_active INTEGER DEFAULT 1
);

-- Scraped guruhlar
CREATE TABLE IF NOT EXISTS scraped_groups (
    group_id TEXT PRIMARY KEY,
    group_title TEXT,
    date_scraped BIGINT,
    owner_id BIGINT DEFAULT 0
);

-- Scraped a'zolar
CREATE TABLE IF NOT EXISTS scraped_members (
    user_id BIGINT,
    username TEXT,
    first_name TEXT,
    group_id TEXT,
    PRIMARY KEY (user_id, group_id),
    FOREIGN KEY(group_id) REFERENCES scraped_groups(group_id)
);

-- Statistika
CREATE TABLE IF NOT EXISTS stats (
    key TEXT PRIMARY KEY,
    value BIGINT DEFAULT 0
);

-- Banlangan foydalanuvchilar
CREATE TABLE IF NOT EXISTS banned_users (
    user_id BIGINT PRIMARY KEY,
    violation_count INTEGER DEFAULT 1
);

-- Bepul foydalanuvchilar
CREATE TABLE IF NOT EXISTS free_users (
    user_id BIGINT PRIMARY KEY
);

-- To'lovlar
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    invoice_payload TEXT,
    status TEXT NOT NULL DEFAULT 'paid',
    grant_status TEXT NOT NULL DEFAULT 'pending',
    granted_expiry BIGINT DEFAULT 0,
    created_at BIGINT DEFAULT 0,
    granted_at BIGINT DEFAULT 0
);

-- Taklif (referral) tizimi
CREATE TABLE IF NOT EXISTS referrals (
    user_id BIGINT PRIMARY KEY,
    referrer_id BIGINT NOT NULL,
    created_at BIGINT NOT NULL
);

-- Pending referral bonuslar (referrer hali users qatoriga ega bo'lmasa)
CREATE TABLE IF NOT EXISTS referral_bonuses (
    user_id BIGINT PRIMARY KEY,
    pending_days INTEGER NOT NULL DEFAULT 0
);

-- Taniqli foydalanuvchilar
CREATE TABLE IF NOT EXISTS known_users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    joined_date BIGINT,
    last_seen BIGINT,
    language TEXT DEFAULT 'uz'
);

-- Yangilanishlar
CREATE TABLE IF NOT EXISTS updates (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    created_by BIGINT NOT NULL
);

-- O'qilgan yangilanishlar
CREATE TABLE IF NOT EXISTS read_updates (
    user_id BIGINT NOT NULL,
    update_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, update_id)
);

-- Admin loglari
CREATE TABLE IF NOT EXISTS admin_logs (
    id SERIAL PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_id BIGINT,
    details TEXT,
    timestamp BIGINT NOT NULL
);

-- Foydalanuvchi sozlamalari
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id BIGINT PRIMARY KEY,
    disable_update_notifications INTEGER DEFAULT 0,
    utag_atag_cmd TEXT DEFAULT 'atag',
    utag_stop_cmd TEXT DEFAULT 'stop',
    utag_pause_cmd TEXT DEFAULT 'pause',
    utag_resume_cmd TEXT DEFAULT 'resume'
);

-- Foydalanuvchi limitleri
CREATE TABLE IF NOT EXISTS user_limits (
    user_id BIGINT PRIMARY KEY,
    last_nakrutka_time BIGINT DEFAULT 0
);

-- Foydalanuvchi harakatlari
CREATE TABLE IF NOT EXISTS user_actions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    timestamp BIGINT NOT NULL
);

-- Adminlar
CREATE TABLE IF NOT EXISTS admins (
    admin_id BIGINT PRIMARY KEY,
    joined_date BIGINT NOT NULL,
    admin_date BIGINT NOT NULL,
    can_add_admin INTEGER DEFAULT 1,
    can_ban INTEGER DEFAULT 1,
    can_clear_db INTEGER DEFAULT 1,
    can_broadcast INTEGER DEFAULT 1,
    can_manage_users INTEGER DEFAULT 1
);

-- MassDM progress
CREATE TABLE IF NOT EXISTS massdm_progress (
    user_id BIGINT NOT NULL,
    group_id TEXT NOT NULL,
    last_index INTEGER DEFAULT 0,
    updated_at BIGINT DEFAULT 0,
    PRIMARY KEY (user_id, group_id)
);

-- MassDM sozlamalari
CREATE TABLE IF NOT EXISTS massdm_settings (
    user_id BIGINT PRIMARY KEY,
    auto_stop_on_high_risk INTEGER DEFAULT 0
);

-- MassDM avtomatik to'xtatilganlar
CREATE TABLE IF NOT EXISTS massdm_auto_stopped (
    stop_key TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    group_id TEXT NOT NULL,
    resume_after BIGINT DEFAULT 0,
    reason TEXT,
    message_to_copy_id BIGINT DEFAULT 0,
    delay_hours INTEGER DEFAULT 0,
    created_at BIGINT DEFAULT 0
);

-- Chat xabarlari
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    sender_id BIGINT NOT NULL,
    receiver_id BIGINT NOT NULL,
    message TEXT NOT NULL,
    photo_file_id TEXT,
    timestamp BIGINT NOT NULL,
    is_read INTEGER DEFAULT 0
);

-- Chat bloklari
CREATE TABLE IF NOT EXISTS chat_blocks (
    blocker_id BIGINT NOT NULL,
    blocked_id BIGINT NOT NULL,
    timestamp BIGINT NOT NULL,
    PRIMARY KEY (blocker_id, blocked_id)
);

-- Chat mute
CREATE TABLE IF NOT EXISTS chat_mutes (
    muter_id BIGINT NOT NULL,
    muted_id BIGINT NOT NULL,
    timestamp BIGINT NOT NULL,
    PRIMARY KEY (muter_id, muted_id)
);

-- Chat shartlari
CREATE TABLE IF NOT EXISTS chat_terms_accepted (
    user_id BIGINT PRIMARY KEY,
    accepted_at BIGINT NOT NULL
);

-- Utag taymerlar
CREATE TABLE IF NOT EXISTS utag_timers (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    message_text TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    repeat_count INTEGER DEFAULT 1,
    repeat_delay INTEGER DEFAULT 5,
    is_active INTEGER DEFAULT 1,
    last_sent BIGINT DEFAULT 0,
    created_at BIGINT NOT NULL,
    UNIQUE(user_id, chat_id)
);

-- Utag custom komandalar
CREATE TABLE IF NOT EXISTS utag_custom_commands (
    user_id BIGINT NOT NULL,
    command TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    PRIMARY KEY (user_id, command)
);

-- Shikoyatlar
CREATE TABLE IF NOT EXISTS complaints (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    target_id BIGINT,
    complaint_type TEXT,
    description TEXT,
    status TEXT DEFAULT 'pending',
    created_at BIGINT DEFAULT 0,
    resolved_at BIGINT DEFAULT 0,
    resolved_by BIGINT
);
