-- ============================================================
-- Pair Platform — Module 2: Hours Logger
-- J-1 limits: 10h/day, 45h/week (enforced in application layer)
-- ============================================================

CREATE TABLE work_logs (
  id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  household_id uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  log_date     date NOT NULL,
  start_time   time NOT NULL,
  end_time     time NOT NULL,
  notes        text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT work_logs_valid_range CHECK (end_time > start_time)
);

CREATE INDEX idx_work_logs_household_date ON work_logs(household_id, log_date);

ALTER TABLE work_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "work_logs_owner" ON work_logs
  USING (
    EXISTS (
      SELECT 1 FROM households h
      WHERE h.id = work_logs.household_id AND h.user_id = auth.uid()
    )
  );

CREATE POLICY "work_logs_owner_insert" ON work_logs
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM households h
      WHERE h.id = work_logs.household_id AND h.user_id = auth.uid()
    )
  );

CREATE POLICY "work_logs_owner_delete" ON work_logs
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM households h
      WHERE h.id = work_logs.household_id AND h.user_id = auth.uid()
    )
  );

CREATE TRIGGER work_logs_updated_at
  BEFORE UPDATE ON work_logs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
