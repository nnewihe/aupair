-- ============================================================
-- Pair Platform — Initial Schema
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Households ──────────────────────────────────────────────
CREATE TABLE households (
  id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id              uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  family_name          text NOT NULL DEFAULT '',
  state                text NOT NULL DEFAULT 'US',
  wizard_completed_at  timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_households_user_id ON households(user_id);

-- ── Child Profiles ───────────────────────────────────────────
CREATE TABLE child_profiles (
  id                         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  household_id               uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  name                       text NOT NULL,
  date_of_birth              date NOT NULL,
  special_needs              boolean NOT NULL DEFAULT false,
  special_needs_description  text,
  dietary_restrictions       text[] NOT NULL DEFAULT '{}',
  allergies                  text[] NOT NULL DEFAULT '{}',
  medical_notes              text,
  school_name                text,
  school_pickup_time         text,
  communication_notes        text,
  emotional_regulation_notes text,
  preferred_activities       text[] NOT NULL DEFAULT '{}',
  sort_order                 integer NOT NULL DEFAULT 0,
  created_at                 timestamptz NOT NULL DEFAULT now(),
  updated_at                 timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_child_profiles_household_id ON child_profiles(household_id);

-- ── Wizard Answers ───────────────────────────────────────────
-- Flat storage: one row per (household, question, repeat_index).
-- Future modules query by question_id without parsing wizard internals.
CREATE TABLE wizard_answers (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  household_id  uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  question_id   text NOT NULL,
  repeat_index  integer NOT NULL DEFAULT 0,
  answer_json   jsonb NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),

  UNIQUE (household_id, question_id, repeat_index)
);

CREATE INDEX idx_wizard_answers_lookup ON wizard_answers(household_id, question_id);
CREATE INDEX idx_wizard_answers_household ON wizard_answers(household_id);

-- ── Share Tokens ─────────────────────────────────────────────
CREATE TABLE share_tokens (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  household_id  uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  token         text NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(32), 'hex'),
  created_at    timestamptz NOT NULL DEFAULT now(),
  revoked_at    timestamptz
);

CREATE INDEX idx_share_tokens_household_id ON share_tokens(household_id);
CREATE INDEX idx_share_tokens_token ON share_tokens(token) WHERE revoked_at IS NULL;

-- ── Generated Guides ─────────────────────────────────────────
-- Stores assembled HTML and metadata for each generated guide.
CREATE TABLE generated_guides (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  household_id  uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  version       integer NOT NULL DEFAULT 1,
  storage_path  text NOT NULL,
  generated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_generated_guides_household ON generated_guides(household_id);

-- ── Row-Level Security ───────────────────────────────────────

ALTER TABLE households ENABLE ROW LEVEL SECURITY;
ALTER TABLE child_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE wizard_answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE share_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE generated_guides ENABLE ROW LEVEL SECURITY;

-- Households: owner only
CREATE POLICY "households_owner" ON households
  USING (auth.uid() = user_id);

-- Child profiles: through household ownership
CREATE POLICY "child_profiles_owner" ON child_profiles
  USING (
    EXISTS (
      SELECT 1 FROM households h
      WHERE h.id = child_profiles.household_id AND h.user_id = auth.uid()
    )
  );

-- Wizard answers: through household ownership
CREATE POLICY "wizard_answers_owner" ON wizard_answers
  USING (
    EXISTS (
      SELECT 1 FROM households h
      WHERE h.id = wizard_answers.household_id AND h.user_id = auth.uid()
    )
  );

-- Share tokens: owner can read/write; public token lookup handled by Edge Function
CREATE POLICY "share_tokens_owner" ON share_tokens
  USING (
    EXISTS (
      SELECT 1 FROM households h
      WHERE h.id = share_tokens.household_id AND h.user_id = auth.uid()
    )
  );

-- Generated guides: owner only
CREATE POLICY "generated_guides_owner" ON generated_guides
  USING (
    EXISTS (
      SELECT 1 FROM households h
      WHERE h.id = generated_guides.household_id AND h.user_id = auth.uid()
    )
  );

-- ── updated_at Trigger ────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER households_updated_at
  BEFORE UPDATE ON households
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER child_profiles_updated_at
  BEFORE UPDATE ON child_profiles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER wizard_answers_updated_at
  BEFORE UPDATE ON wizard_answers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
