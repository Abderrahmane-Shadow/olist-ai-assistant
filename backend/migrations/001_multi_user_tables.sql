-- ==============================================================================
-- Migration 001: Multi-User Authentication, Conversations, Messages & Usage
-- Compatible with both local PostgreSQL and hosted Supabase PostgreSQL.
-- ==============================================================================

-- 1. Ensure UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Mock auth schema for local development/testing if not on Supabase
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
        CREATE SCHEMA auth;
        CREATE TABLE auth.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    END IF;
END $$;

-- 3. Public User Profiles Table
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    daily_question_limit INT NOT NULL DEFAULT 15,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index on profiles email
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(email);

-- 4. User Conversations Table
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes on conversations for fast user listing and sorting
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON public.conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON public.conversations(user_id, updated_at DESC);

-- 5. Conversation Messages Table
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index on messages for chronological retrieval per conversation
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON public.messages(conversation_id, created_at ASC);

-- 6. User Daily Question Usage & Quota Tracker
CREATE TABLE IF NOT EXISTS public.user_daily_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    question_count INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_daily_usage UNIQUE (user_id, usage_date)
);

-- Index on daily usage lookup
CREATE INDEX IF NOT EXISTS idx_user_daily_usage_lookup ON public.user_daily_usage(user_id, usage_date);

-- 7. Supabase Row Level Security (RLS) Policies
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_daily_usage ENABLE ROW LEVEL SECURITY;

-- Profile policies
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'profiles' AND policyname = 'Users can view own profile') THEN
        CREATE POLICY "Users can view own profile" ON public.profiles
            FOR SELECT USING (auth.uid() = id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'profiles' AND policyname = 'Users can update own profile') THEN
        CREATE POLICY "Users can update own profile" ON public.profiles
            FOR UPDATE USING (auth.uid() = id);
    END IF;
END $$;

-- Conversation policies
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'conversations' AND policyname = 'Users can select own conversations') THEN
        CREATE POLICY "Users can select own conversations" ON public.conversations
            FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'conversations' AND policyname = 'Users can insert own conversations') THEN
        CREATE POLICY "Users can insert own conversations" ON public.conversations
            FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'conversations' AND policyname = 'Users can update own conversations') THEN
        CREATE POLICY "Users can update own conversations" ON public.conversations
            FOR UPDATE USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'conversations' AND policyname = 'Users can delete own conversations') THEN
        CREATE POLICY "Users can delete own conversations" ON public.conversations
            FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

-- Message policies
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'messages' AND policyname = 'Users can view messages in own conversations') THEN
        CREATE POLICY "Users can view messages in own conversations" ON public.messages
            FOR SELECT USING (
                EXISTS (
                    SELECT 1 FROM public.conversations c
                    WHERE c.id = messages.conversation_id AND c.user_id = auth.uid()
                )
            );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'messages' AND policyname = 'Users can insert messages in own conversations') THEN
        CREATE POLICY "Users can insert messages in own conversations" ON public.messages
            FOR INSERT WITH CHECK (
                EXISTS (
                    SELECT 1 FROM public.conversations c
                    WHERE c.id = messages.conversation_id AND c.user_id = auth.uid()
                )
            );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'messages' AND policyname = 'Users can delete messages in own conversations') THEN
        CREATE POLICY "Users can delete messages in own conversations" ON public.messages
            FOR DELETE USING (
                EXISTS (
                    SELECT 1 FROM public.conversations c
                    WHERE c.id = messages.conversation_id AND c.user_id = auth.uid()
                )
            );
    END IF;
END $$;

-- Daily usage policies
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'user_daily_usage' AND policyname = 'Users can view own daily usage') THEN
        CREATE POLICY "Users can view own daily usage" ON public.user_daily_usage
            FOR SELECT USING (auth.uid() = user_id);
    END IF;
END $$;

-- 8. Auto-create profile trigger on Supabase auth.users signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name)
    VALUES (new.id, new.email, split_part(new.email, '@', 1))
    ON CONFLICT (id) DO NOTHING;
    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Bind trigger if auth.users exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'auth' AND table_name = 'users') THEN
        DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
    END IF;
END $$;

-- 9. Least-privilege role configuration and isolation for olist_readonly (if role exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'olist_readonly') THEN
        -- Grant schema usage
        GRANT USAGE ON SCHEMA public TO olist_readonly;

        -- Explicitly grant SELECT ONLY on the 9 approved Olist analytics tables
        GRANT SELECT ON TABLE public.customers TO olist_readonly;
        GRANT SELECT ON TABLE public.geolocation TO olist_readonly;
        GRANT SELECT ON TABLE public.orders TO olist_readonly;
        GRANT SELECT ON TABLE public.order_items TO olist_readonly;
        GRANT SELECT ON TABLE public.order_payments TO olist_readonly;
        GRANT SELECT ON TABLE public.order_reviews TO olist_readonly;
        GRANT SELECT ON TABLE public.products TO olist_readonly;
        GRANT SELECT ON TABLE public.sellers TO olist_readonly;
        GRANT SELECT ON TABLE public.product_category_name_translation TO olist_readonly;

        -- Explicitly revoke access to user & conversation tables
        REVOKE ALL PRIVILEGES ON TABLE public.profiles FROM olist_readonly;
        REVOKE ALL PRIVILEGES ON TABLE public.conversations FROM olist_readonly;
        REVOKE ALL PRIVILEGES ON TABLE public.messages FROM olist_readonly;
        REVOKE ALL PRIVILEGES ON TABLE public.user_daily_usage FROM olist_readonly;
    END IF;
END $$;
