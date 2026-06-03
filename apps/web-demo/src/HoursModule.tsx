import React, { useState } from 'react';

// ── Colour tokens (match App.tsx) ──────────────────────────────────────────────
const C = {
  navy: '#1a2744',
  teal: '#14b8a6',
  tealLight: '#f0fdfa',
  tealDark: '#0f766e',
  tealBorder: '#99f6e4',
  bg: '#f8fafc',
  card: '#fff',
  border: '#e2e8f0',
  text: '#334155',
  subtle: '#64748b',
};

// ── Types ──────────────────────────────────────────────────────────────────────
type Priority = 'mandatory' | 'helpful' | 'nice-to-have';

interface ScheduleDay {
  active: boolean;
  blocks: TimeBlock[];   // one entry = single shift, multiple = split day
  priority: Priority;
}

const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const;
type WeekdayKey = typeof WEEKDAYS[number];
type StandardSchedule = Record<WeekdayKey, ScheduleDay>;

interface TimeBlock {
  startTime: string;
  endTime: string;
}

interface WorkEntry {
  id: string;
  date: string;
  startTime: string;
  endTime: string;
  notes: string;
  type: 'standard' | 'extra';
}

// ── Constants ──────────────────────────────────────────────────────────────────
const DAILY_LIMIT_MINS = 600;   // 10 hours J-1 limit
const WEEKLY_LIMIT_MINS = 2700; // 45 hours J-1 limit

const LS_SCHEDULE_KEY = 'pair_standard_schedule';
const LS_ENTRIES_KEY  = 'pair_work_entries';

const DEFAULT_SCHEDULE: StandardSchedule = {
  monday:    { active: true,  blocks: [{ startTime: '08:00', endTime: '17:00' }], priority: 'mandatory' },
  tuesday:   { active: true,  blocks: [{ startTime: '08:00', endTime: '17:00' }], priority: 'mandatory' },
  wednesday: { active: true,  blocks: [{ startTime: '08:00', endTime: '17:00' }], priority: 'mandatory' },
  thursday:  { active: true,  blocks: [{ startTime: '08:00', endTime: '17:00' }], priority: 'mandatory' },
  friday:    { active: true,  blocks: [{ startTime: '08:00', endTime: '17:00' }], priority: 'mandatory' },
  saturday:  { active: false, blocks: [{ startTime: '09:00', endTime: '13:00' }], priority: 'helpful' },
  sunday:    { active: false, blocks: [{ startTime: '09:00', endTime: '13:00' }], priority: 'nice-to-have' },
};

const DAY_LABELS: Record<WeekdayKey, string> = {
  monday: 'Monday', tuesday: 'Tuesday', wednesday: 'Wednesday',
  thursday: 'Thursday', friday: 'Friday', saturday: 'Saturday', sunday: 'Sunday',
};

const DAY_SHORT: Record<WeekdayKey, string> = {
  monday: 'Mon', tuesday: 'Tue', wednesday: 'Wed',
  thursday: 'Thu', friday: 'Fri', saturday: 'Sat', sunday: 'Sun',
};

const PRIORITY_LABELS: Record<Priority, string> = {
  mandatory: 'Mandatory',
  helpful: 'Helpful',
  'nice-to-have': 'Nice to have',
};

const PRIORITY_COLORS: Record<Priority, { bg: string; text: string; border: string }> = {
  mandatory:      { bg: '#fee2e2', text: '#b91c1c', border: '#fca5a5' },
  helpful:        { bg: '#fef3c7', text: '#92400e', border: '#fcd34d' },
  'nice-to-have': { bg: '#f0fdf4', text: '#166534', border: '#86efac' },
};

// ── Utilities ──────────────────────────────────────────────────────────────────
function minutesBetween(start: string, end: string): number {
  const [sh, sm] = start.split(':').map(Number);
  const [eh, em] = end.split(':').map(Number);
  const result = (eh * 60 + em) - (sh * 60 + sm);
  return result > 0 ? result : 0;
}

function formatMinutes(mins: number): string {
  if (mins === 0) return '0h';
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

function formatTime12(time: string): string {
  const [h, m] = time.split(':').map(Number);
  const ampm = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 || 12;
  return `${h12}:${m.toString().padStart(2, '0')} ${ampm}`;
}

function getWeekStart(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

function toDateKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}

// ── LocalStorage helpers ───────────────────────────────────────────────────────
function loadSchedule(): StandardSchedule | null {
  try {
    const raw = localStorage.getItem(LS_SCHEDULE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, Record<string, unknown>>;
    // Migrate legacy format (startTime/endTime → blocks)
    const result = { ...DEFAULT_SCHEDULE };
    for (const day of WEEKDAYS) {
      const d = parsed[day];
      if (!d) continue;
      result[day] = {
        active:   (d.active as boolean) ?? true,
        priority: (d.priority as Priority) ?? 'mandatory',
        blocks:   Array.isArray(d.blocks)
          ? (d.blocks as TimeBlock[])
          : [{ startTime: (d.startTime as string) ?? '08:00', endTime: (d.endTime as string) ?? '17:00' }],
      };
    }
    return result;
  } catch { return null; }
}

function saveScheduleLS(s: StandardSchedule): void {
  localStorage.setItem(LS_SCHEDULE_KEY, JSON.stringify(s));
}

function loadEntries(): WorkEntry[] {
  try {
    const raw = localStorage.getItem(LS_ENTRIES_KEY);
    return raw ? (JSON.parse(raw) as WorkEntry[]) : [];
  } catch { return []; }
}

function saveEntriesLS(entries: WorkEntry[]): void {
  localStorage.setItem(LS_ENTRIES_KEY, JSON.stringify(entries));
}

// ── SetupView ──────────────────────────────────────────────────────────────────
function SetupView({ onSave, initial }: { onSave: (s: StandardSchedule) => void; initial?: StandardSchedule | null }) {
  const [schedule, setSchedule] = useState<StandardSchedule>(initial ?? DEFAULT_SCHEDULE);

  // ── Day-level helpers
  function toggleDay(day: WeekdayKey) {
    setSchedule(prev => ({ ...prev, [day]: { ...prev[day], active: !prev[day].active } }));
  }
  function setPriority(day: WeekdayKey, p: Priority) {
    setSchedule(prev => ({ ...prev, [day]: { ...prev[day], priority: p } }));
  }

  // ── Block-level helpers
  function updateBlock(day: WeekdayKey, i: number, field: keyof TimeBlock, value: string) {
    setSchedule(prev => ({
      ...prev,
      [day]: {
        ...prev[day],
        blocks: prev[day].blocks.map((b, idx) => idx === i ? { ...b, [field]: value } : b),
      },
    }));
  }
  function addBlock(day: WeekdayKey) {
    setSchedule(prev => {
      const lastEnd = prev[day].blocks[prev[day].blocks.length - 1]?.endTime ?? '12:00';
      return {
        ...prev,
        [day]: { ...prev[day], blocks: [...prev[day].blocks, { startTime: lastEnd, endTime: lastEnd }] },
      };
    });
  }
  function removeBlock(day: WeekdayKey, i: number) {
    setSchedule(prev => ({
      ...prev,
      [day]: { ...prev[day], blocks: prev[day].blocks.filter((_, idx) => idx !== i) },
    }));
  }

  const activeCount = WEEKDAYS.filter(d => schedule[d].active).length;
  const totalWeeklyMins = WEEKDAYS.reduce((sum, d) => {
    if (!schedule[d].active) return sum;
    return sum + schedule[d].blocks.reduce((s, b) => s + minutesBetween(b.startTime, b.endTime), 0);
  }, 0);
  const overWeeklyLimit = totalWeeklyMins > WEEKLY_LIMIT_MINS;

  return (
    <div style={{ maxWidth: 680, margin: '0 auto', padding: '32px 24px 80px' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: C.navy, marginBottom: 6 }}>
          Set up your standard schedule
        </h1>
        <p style={{ fontSize: 14, color: C.subtle, lineHeight: 1.65 }}>
          Define your au pair's regular weekly hours. Add multiple shifts per day for split schedules (e.g. morning drop-off + afternoon pick-up).
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
        {WEEKDAYS.map(day => {
          const d = schedule[day];
          const dayMins = d.active
            ? d.blocks.reduce((s, b) => s + minutesBetween(b.startTime, b.endTime), 0)
            : 0;
          const pc = PRIORITY_COLORS[d.priority];

          return (
            <div key={day} style={{
              background: C.card, borderRadius: 12, padding: '14px 18px',
              border: `1px solid ${C.border}`,
              opacity: d.active ? 1 : 0.55, transition: 'opacity .15s',
            }}>
              {/* Toggle + day name + total */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: d.active ? 12 : 0 }}>
                <button
                  onClick={() => toggleDay(day)}
                  style={{
                    width: 44, height: 24, borderRadius: 12, border: 'none',
                    background: d.active ? C.teal : C.border,
                    cursor: 'pointer', position: 'relative', flexShrink: 0,
                    transition: 'background .15s',
                  }}
                >
                  <span style={{
                    position: 'absolute', top: 3, width: 18, height: 18,
                    borderRadius: '50%', background: '#fff',
                    left: d.active ? 23 : 3, transition: 'left .15s',
                  }} />
                </button>
                <span style={{ fontSize: 15, fontWeight: 700, color: C.navy, minWidth: 100 }}>
                  {DAY_LABELS[day]}
                </span>
                <span style={{ fontSize: 13, color: C.subtle, marginLeft: 'auto' }}>
                  {d.active ? formatMinutes(dayMins) : 'Off'}
                </span>
              </div>

              {d.active && (
                <>
                  {/* Shift blocks */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
                    {d.blocks.map((block, i) => {
                      const blockMins = minutesBetween(block.startTime, block.endTime);
                      return (
                        <div key={i} style={{
                          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
                          background: C.bg, borderRadius: 8, padding: '8px 10px',
                          border: `1px solid ${C.border}`,
                        }}>
                          {d.blocks.length > 1 && (
                            <span style={{
                              fontSize: 10, fontWeight: 700, textTransform: 'uppercase' as const,
                              color: C.tealDark, background: C.tealLight,
                              border: `1px solid ${C.tealBorder}`, borderRadius: 4,
                              padding: '2px 6px', flexShrink: 0,
                            }}>
                              Shift {i + 1}
                            </span>
                          )}
                          <input
                            type="time"
                            value={block.startTime}
                            onChange={e => updateBlock(day, i, 'startTime', e.target.value)}
                            style={{
                              padding: '6px 8px', borderRadius: 7, fontSize: 13,
                              border: `1px solid ${C.border}`, color: C.text, flex: '1 1 90px',
                            }}
                          />
                          <span style={{ fontSize: 12, color: C.subtle, flexShrink: 0 }}>to</span>
                          <input
                            type="time"
                            value={block.endTime}
                            onChange={e => updateBlock(day, i, 'endTime', e.target.value)}
                            style={{
                              padding: '6px 8px', borderRadius: 7, fontSize: 13,
                              border: `1px solid ${C.border}`, color: C.text, flex: '1 1 90px',
                            }}
                          />
                          {blockMins > 0 && (
                            <span style={{ fontSize: 12, fontWeight: 600, color: C.subtle, flexShrink: 0 }}>
                              {formatMinutes(blockMins)}
                            </span>
                          )}
                          {d.blocks.length > 1 && (
                            <button
                              onClick={() => removeBlock(day, i)}
                              style={{
                                padding: '3px 8px', borderRadius: 6, fontSize: 12, flexShrink: 0,
                                border: '1px solid #fca5a5', background: '#fee2e2',
                                color: '#b91c1c', cursor: 'pointer',
                              }}
                            >
                              ×
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Add shift + priority on same row */}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                      onClick={() => addBlock(day)}
                      style={{
                        padding: '6px 12px', borderRadius: 7, fontSize: 12, fontWeight: 600,
                        border: `1px dashed ${C.teal}`, background: C.tealLight,
                        color: C.tealDark, cursor: 'pointer',
                      }}
                    >
                      + Add shift
                    </button>
                    <select
                      value={d.priority}
                      onChange={e => setPriority(day, e.target.value as Priority)}
                      style={{
                        padding: '6px 10px', borderRadius: 7, fontSize: 12, fontWeight: 600,
                        border: `1px solid ${pc.border}`,
                        background: pc.bg, color: pc.text, cursor: 'pointer',
                      }}
                    >
                      <option value="mandatory">Mandatory</option>
                      <option value="helpful">Helpful</option>
                      <option value="nice-to-have">Nice to have</option>
                    </select>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Weekly summary */}
      <div style={{
        background: overWeeklyLimit ? '#fee2e2' : C.tealLight,
        border: `1px solid ${overWeeklyLimit ? '#fca5a5' : C.tealBorder}`,
        borderRadius: 12, padding: '14px 18px', marginBottom: 24,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
      }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: overWeeklyLimit ? '#b91c1c' : C.tealDark }}>
            {activeCount} day{activeCount !== 1 ? 's' : ''} / week · {formatMinutes(totalWeeklyMins)} standard
          </div>
          {overWeeklyLimit && (
            <div style={{ fontSize: 12, color: '#b91c1c', marginTop: 2 }}>
              ⚠️ Exceeds the 45h J-1 weekly limit — consider adjusting hours
            </div>
          )}
        </div>
        <div style={{ fontSize: 13, color: overWeeklyLimit ? '#b91c1c' : C.tealDark, fontWeight: 600 }}>
          {formatMinutes(WEEKLY_LIMIT_MINS)} limit
        </div>
      </div>

      <button
        onClick={() => onSave(schedule)}
        style={{
          width: '100%', padding: '15px 24px', borderRadius: 12, border: 'none',
          background: C.navy, color: '#fff', fontWeight: 700, fontSize: 16, cursor: 'pointer',
        }}
      >
        Save Schedule →
      </button>
    </div>
  );
}

// ── LogEntryModal ──────────────────────────────────────────────────────────────
interface LogEntryModalProps {
  date: string;
  /** Returns one entry per time block (split shifts produce multiple entries). */
  onSave: (entries: Omit<WorkEntry, 'id'>[]) => void;
  onClose: () => void;
  /** When provided the modal is in single-block edit mode. */
  existing?: WorkEntry;
}

function LogEntryModal({ date, onSave, onClose, existing }: LogEntryModalProps) {
  const [entryDate, setEntryDate] = useState(existing?.date ?? date);
  const [type, setType] = useState<'standard' | 'extra'>(existing?.type ?? 'standard');
  const [notes, setNotes] = useState(existing?.notes ?? '');

  // In edit mode we only show the one block being edited; in add mode we start
  // with a single block and allow more to be appended (split shifts).
  const [blocks, setBlocks] = useState<TimeBlock[]>(
    existing
      ? [{ startTime: existing.startTime, endTime: existing.endTime }]
      : [{ startTime: '08:00', endTime: '17:00' }],
  );

  function updateBlock(i: number, field: keyof TimeBlock, value: string) {
    setBlocks(prev => prev.map((b, idx) => idx === i ? { ...b, [field]: value } : b));
  }

  function addBlock() {
    // Seed the new block's start from the previous block's end
    const lastEnd = blocks[blocks.length - 1]?.endTime ?? '12:00';
    setBlocks(prev => [...prev, { startTime: lastEnd, endTime: lastEnd }]);
  }

  function removeBlock(i: number) {
    if (blocks.length === 1) return;
    setBlocks(prev => prev.filter((_, idx) => idx !== i));
  }

  const blockMins = blocks.map(b => minutesBetween(b.startTime, b.endTime));
  const totalMins = blockMins.reduce((s, m) => s + m, 0);
  const allValid  = blocks.length > 0 && blockMins.every(m => m > 0);

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 100, padding: 16,
    }}>
      <div style={{
        background: C.card, borderRadius: 16, padding: 28,
        maxWidth: 460, width: '100%', maxHeight: '90vh', overflowY: 'auto',
      }}>
        <h3 style={{ fontSize: 18, fontWeight: 800, color: C.navy, marginBottom: 20 }}>
          {existing ? 'Edit entry' : 'Log hours'}
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Date */}
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, color: C.subtle, display: 'block', marginBottom: 6 }}>
              Date
            </label>
            <input
              type="date"
              value={entryDate}
              onChange={e => setEntryDate(e.target.value)}
              style={{
                width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                border: `1px solid ${C.border}`, color: C.text,
              }}
            />
          </div>

          {/* Time blocks */}
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, color: C.subtle, display: 'block', marginBottom: 8 }}>
              {existing ? 'Time' : 'Time blocks'}
            </label>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {blocks.map((block, i) => {
                const mins = blockMins[i];
                const over = mins > DAILY_LIMIT_MINS;
                return (
                  <div key={i} style={{
                    background: C.bg, borderRadius: 10,
                    border: `1px solid ${C.border}`, padding: '12px 14px',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      {/* Block label */}
                      {!existing && blocks.length > 1 && (
                        <span style={{
                          fontSize: 11, fontWeight: 700, color: C.tealDark,
                          background: C.tealLight, border: `1px solid ${C.tealBorder}`,
                          borderRadius: 5, padding: '2px 7px', flexShrink: 0,
                        }}>
                          Shift {i + 1}
                        </span>
                      )}

                      <input
                        type="time"
                        value={block.startTime}
                        onChange={e => updateBlock(i, 'startTime', e.target.value)}
                        style={{
                          padding: '8px 10px', borderRadius: 8, fontSize: 14,
                          border: `1px solid ${C.border}`, color: C.text, flex: '1 1 100px',
                        }}
                      />
                      <span style={{ fontSize: 13, color: C.subtle, flexShrink: 0 }}>to</span>
                      <input
                        type="time"
                        value={block.endTime}
                        onChange={e => updateBlock(i, 'endTime', e.target.value)}
                        style={{
                          padding: '8px 10px', borderRadius: 8, fontSize: 14,
                          border: `1px solid ${C.border}`, color: C.text, flex: '1 1 100px',
                        }}
                      />

                      {/* Duration badge */}
                      {mins > 0 && (
                        <span style={{
                          fontSize: 12, fontWeight: 600, flexShrink: 0,
                          color: over ? '#b91c1c' : C.tealDark,
                        }}>
                          {formatMinutes(mins)}{over ? ' ⚠️' : ''}
                        </span>
                      )}

                      {/* Remove block */}
                      {!existing && blocks.length > 1 && (
                        <button
                          onClick={() => removeBlock(i)}
                          style={{
                            padding: '4px 9px', borderRadius: 6, fontSize: 13, flexShrink: 0,
                            border: '1px solid #fca5a5', background: '#fee2e2',
                            color: '#b91c1c', cursor: 'pointer',
                          }}
                        >
                          ×
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Add block (only in add mode) */}
            {!existing && (
              <button
                onClick={addBlock}
                style={{
                  marginTop: 8, width: '100%',
                  padding: '9px 14px', borderRadius: 9,
                  border: `1px dashed ${C.teal}`, background: C.tealLight,
                  color: C.tealDark, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                }}
              >
                + Add another shift
              </button>
            )}

            {/* Total across all blocks */}
            {blocks.length > 1 && totalMins > 0 && (
              <div style={{
                marginTop: 10, fontSize: 13, fontWeight: 600,
                color: totalMins > DAILY_LIMIT_MINS ? '#b91c1c' : C.tealDark,
                background: totalMins > DAILY_LIMIT_MINS ? '#fee2e2' : C.tealLight,
                border: `1px solid ${totalMins > DAILY_LIMIT_MINS ? '#fca5a5' : C.tealBorder}`,
                borderRadius: 8, padding: '8px 12px',
              }}>
                {totalMins > DAILY_LIMIT_MINS
                  ? `⚠️ Total ${formatMinutes(totalMins)} — exceeds 10h daily J-1 limit`
                  : `Total: ${formatMinutes(totalMins)} across ${blocks.length} shifts`}
              </div>
            )}
          </div>

          {/* Type */}
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, color: C.subtle, display: 'block', marginBottom: 6 }}>
              Type
            </label>
            <div style={{ display: 'flex', gap: 10 }}>
              {(['standard', 'extra'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setType(t)}
                  style={{
                    flex: 1, padding: '10px 14px', borderRadius: 10, cursor: 'pointer',
                    border: `2px solid ${type === t ? C.teal : C.border}`,
                    background: type === t ? C.tealLight : C.card,
                    color: type === t ? C.tealDark : C.text,
                    fontWeight: type === t ? 700 : 400, fontSize: 14,
                  }}
                >
                  {t === 'standard' ? 'Standard' : 'Extra'}
                </button>
              ))}
            </div>
            <p style={{ fontSize: 12, color: C.subtle, marginTop: 6 }}>
              {type === 'extra'
                ? 'Extra hours are outside the standard schedule and require family approval.'
                : 'Standard hours match the weekly schedule baseline.'}
            </p>
          </div>

          {/* Notes */}
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, color: C.subtle, display: 'block', marginBottom: 6 }}>
              Notes <span style={{ fontWeight: 400 }}>(optional)</span>
            </label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="e.g. Morning school run + afternoon pick-up"
              rows={2}
              style={{
                width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                border: `1px solid ${C.border}`, color: C.text, resize: 'vertical',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
          <button onClick={onClose} style={{
            flex: 1, padding: '12px', borderRadius: 10,
            border: `1px solid ${C.border}`, background: 'transparent',
            color: C.subtle, fontWeight: 600, cursor: 'pointer',
          }}>
            Cancel
          </button>
          <button
            onClick={() => {
              if (!allValid) return;
              onSave(blocks.map(b => ({ date: entryDate, startTime: b.startTime, endTime: b.endTime, notes, type })));
            }}
            disabled={!allValid}
            style={{
              flex: 2, padding: '12px', borderRadius: 10, border: 'none',
              background: allValid ? C.navy : C.border,
              color: allValid ? '#fff' : C.subtle,
              fontWeight: 700, cursor: allValid ? 'pointer' : 'not-allowed',
            }}
          >
            {existing ? 'Save changes' : `Log ${blocks.length > 1 ? blocks.length + ' shifts' : 'hours'}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── WeeklyLogView ──────────────────────────────────────────────────────────────
interface WeeklyLogViewProps {
  schedule: StandardSchedule;
  entries: WorkEntry[];
  onAddEntries: (entries: Omit<WorkEntry, 'id'>[]) => void;
  onUpdateEntry: (id: string, entry: Omit<WorkEntry, 'id'>) => void;
  onDeleteEntry: (id: string) => void;
  onEditSchedule: () => void;
}

function WeeklyLogView({ schedule, entries, onAddEntries, onUpdateEntry, onDeleteEntry, onEditSchedule }: WeeklyLogViewProps) {
  const [weekOffset, setWeekOffset] = useState(0);
  const [addModal, setAddModal] = useState<string | null>(null);
  const [editModal, setEditModal] = useState<WorkEntry | null>(null);

  const today = new Date();
  const weekStart = addDays(getWeekStart(today), weekOffset * 7);
  const weekEnd = addDays(weekStart, 6);
  const weekDayKeys: WeekdayKey[] = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

  // Build per-day data
  let weeklyScheduledMins = 0;
  let weeklyLoggedMins = 0;

  const dayData = Array.from({ length: 7 }, (_, i) => {
    const date = addDays(weekStart, i);
    const dateKey = toDateKey(date);
    const dayKey = weekDayKeys[i];
    const sched = schedule[dayKey];
    const dayEntries = entries.filter(e => e.date === dateKey);
    const scheduledMins = sched.active
      ? sched.blocks.reduce((s, b) => s + minutesBetween(b.startTime, b.endTime), 0)
      : 0;
    const loggedMins = dayEntries.reduce((sum, e) => sum + minutesBetween(e.startTime, e.endTime), 0);
    weeklyScheduledMins += scheduledMins;
    weeklyLoggedMins += loggedMins;
    return { date, dateKey, dayKey, sched, dayEntries, scheduledMins, loggedMins };
  });

  const weeklyOver = weeklyLoggedMins > WEEKLY_LIMIT_MINS;
  const todayKey = toDateKey(today);

  function fmtWeekRange(start: Date, end: Date): string {
    const o: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
    return `${start.toLocaleDateString('en-US', o)} – ${end.toLocaleDateString('en-US', o)}`;
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '32px 24px 80px' }}>
      {/* Page header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: 24, flexWrap: 'wrap', gap: 12,
      }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: C.navy, marginBottom: 4 }}>Hours Log</h1>
          <p style={{ fontSize: 13, color: C.subtle }}>Track your au pair's working hours week by week.</p>
        </div>
        <button
          onClick={onEditSchedule}
          style={{
            padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            border: `1px solid ${C.border}`, background: C.card, color: C.subtle, cursor: 'pointer',
          }}
        >
          Edit schedule
        </button>
      </div>

      {/* Week navigator */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: C.card, border: `1px solid ${C.border}`,
        borderRadius: 12, padding: '12px 16px', marginBottom: 16,
      }}>
        <button
          onClick={() => setWeekOffset(w => w - 1)}
          style={{
            padding: '6px 12px', borderRadius: 8,
            border: `1px solid ${C.border}`, background: 'transparent',
            color: C.text, fontWeight: 600, cursor: 'pointer',
          }}
        >
          ← Prev
        </button>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: C.navy }}>
            {fmtWeekRange(weekStart, weekEnd)}
          </div>
          {weekOffset === 0 && (
            <div style={{ fontSize: 12, color: C.tealDark, fontWeight: 600 }}>This week</div>
          )}
          {weekOffset < 0 && (
            <div style={{ fontSize: 12, color: C.subtle }}>
              {Math.abs(weekOffset)} week{Math.abs(weekOffset) > 1 ? 's' : ''} ago
            </div>
          )}
          {weekOffset > 0 && (
            <div style={{ fontSize: 12, color: C.subtle }}>
              {weekOffset} week{weekOffset > 1 ? 's' : ''} ahead
            </div>
          )}
        </div>
        <button
          onClick={() => setWeekOffset(w => w + 1)}
          style={{
            padding: '6px 12px', borderRadius: 8,
            border: `1px solid ${C.border}`, background: 'transparent',
            color: C.text, fontWeight: 600, cursor: 'pointer',
          }}
        >
          Next →
        </button>
      </div>

      {/* Day rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
        {dayData.map(({ date, dateKey, dayKey, sched, dayEntries, scheduledMins, loggedMins }) => {
          const isToday = dateKey === todayKey;
          const isOver = loggedMins > DAILY_LIMIT_MINS;
          const pc = PRIORITY_COLORS[sched.priority];
          const hasContent = sched.active || dayEntries.length > 0;

          return (
            <div key={dateKey} style={{
              background: C.card, borderRadius: 12,
              border: `1px solid ${isToday ? C.teal : C.border}`,
              overflow: 'hidden',
            }}>
              {/* Day header */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px',
                background: isToday ? C.tealLight : 'transparent',
                borderBottom: hasContent && dayEntries.length > 0 ? `1px solid ${C.border}` : 'none',
              }}>
                {/* Date label */}
                <div style={{ minWidth: 50, flexShrink: 0 }}>
                  <div style={{
                    fontSize: 13, fontWeight: 700,
                    color: isToday ? C.tealDark : C.navy,
                  }}>
                    {DAY_SHORT[dayKey]}
                  </div>
                  <div style={{ fontSize: 11, color: C.subtle }}>
                    {date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </div>
                </div>

                {/* Standard schedule badge */}
                {sched.active ? (
                  <>
                    <div style={{
                      fontSize: 11, fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: 0.4,
                      color: pc.text, background: pc.bg, border: `1px solid ${pc.border}`,
                      borderRadius: 6, padding: '2px 7px', flexShrink: 0,
                    }}>
                      {PRIORITY_LABELS[sched.priority]}
                    </div>
                    <div style={{ fontSize: 13, color: C.subtle, flexShrink: 0 }}>
                      {sched.blocks.map((b, i) => (
                        <span key={i}>
                          {i > 0 && <span style={{ color: C.border }}> · </span>}
                          {formatTime12(b.startTime)} – {formatTime12(b.endTime)}
                        </span>
                      ))}
                      <span style={{ color: C.border }}> · </span>
                      <span style={{ color: C.text, fontWeight: 500 }}>{formatMinutes(scheduledMins)}</span>
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 13, color: C.border, fontStyle: 'italic' }}>Not scheduled</div>
                )}

                {/* Logged total + add button */}
                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  {loggedMins > 0 && (
                    <span style={{
                      fontSize: 13, fontWeight: 700,
                      color: isOver ? '#b91c1c' : C.tealDark,
                    }}>
                      {formatMinutes(loggedMins)}{isOver ? ' ⚠️' : ' ✓'}
                    </span>
                  )}
                  <button
                    onClick={() => setAddModal(dateKey)}
                    style={{
                      padding: '5px 10px', borderRadius: 7, fontSize: 12, fontWeight: 600,
                      border: `1px solid ${C.tealBorder}`, background: C.tealLight,
                      color: C.tealDark, cursor: 'pointer',
                    }}
                  >
                    + Log
                  </button>
                </div>
              </div>

              {/* Logged entries */}
              {dayEntries.length > 0 && (
                <div>
                  {dayEntries.map((entry, ei) => {
                    const entryMins = minutesBetween(entry.startTime, entry.endTime);
                    const isExtra = entry.type === 'extra';
                    return (
                      <div key={entry.id} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '9px 16px',
                        borderBottom: ei < dayEntries.length - 1 ? `1px solid ${C.border}` : 'none',
                        background: isExtra ? '#fffbeb' : 'transparent',
                      }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: 0.5,
                          color: isExtra ? '#92400e' : C.tealDark,
                          background: isExtra ? '#fef3c7' : C.tealLight,
                          border: `1px solid ${isExtra ? '#fcd34d' : C.tealBorder}`,
                          borderRadius: 4, padding: '2px 6px', flexShrink: 0,
                        }}>
                          {entry.type}
                        </span>
                        <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 0 }}>
                          {formatTime12(entry.startTime)} – {formatTime12(entry.endTime)}
                          {entry.notes && (
                            <span style={{ color: C.subtle }}> · {entry.notes}</span>
                          )}
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: C.subtle, flexShrink: 0 }}>
                          {formatMinutes(entryMins)}
                        </span>
                        <button
                          onClick={() => setEditModal(entry)}
                          style={{
                            padding: '3px 8px', borderRadius: 6, fontSize: 12,
                            border: `1px solid ${C.border}`, background: 'transparent',
                            color: C.subtle, cursor: 'pointer',
                          }}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => onDeleteEntry(entry.id)}
                          style={{
                            padding: '3px 8px', borderRadius: 6, fontSize: 12,
                            border: '1px solid #fca5a5', background: '#fee2e2',
                            color: '#b91c1c', cursor: 'pointer',
                          }}
                        >
                          ×
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Weekly summary */}
      <div style={{
        background: weeklyOver ? '#fee2e2' : C.tealLight,
        border: `1px solid ${weeklyOver ? '#fca5a5' : C.tealBorder}`,
        borderRadius: 12, padding: '16px 20px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: weeklyOver ? '#b91c1c' : C.tealDark }}>
              {weeklyOver ? '⚠️ Weekly limit exceeded' : 'Week total'}
            </div>
            <div style={{ fontSize: 13, color: weeklyOver ? '#b91c1c' : C.subtle, marginTop: 2 }}>
              {formatMinutes(weeklyLoggedMins)} logged · {formatMinutes(weeklyScheduledMins)} scheduled baseline
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 26, fontWeight: 800, color: weeklyOver ? '#b91c1c' : C.tealDark }}>
              {formatMinutes(weeklyLoggedMins)}
            </div>
            <div style={{ fontSize: 12, color: weeklyOver ? '#b91c1c' : C.subtle }}>
              of {formatMinutes(WEEKLY_LIMIT_MINS)} J-1 limit
            </div>
          </div>
        </div>
      </div>

      {/* Modals */}
      {addModal && (
        <LogEntryModal
          date={addModal}
          onSave={newEntries => { onAddEntries(newEntries); setAddModal(null); }}
          onClose={() => setAddModal(null)}
        />
      )}
      {editModal && (
        <LogEntryModal
          date={editModal.date}
          existing={editModal}
          onSave={([entry]) => { onUpdateEntry(editModal.id, entry); setEditModal(null); }}
          onClose={() => setEditModal(null)}
        />
      )}
    </div>
  );
}

// ── HoursModule (main export) ──────────────────────────────────────────────────
export default function HoursModule() {
  const [schedule, setSchedule] = useState<StandardSchedule | null>(() => loadSchedule());
  const [entries, setEntries] = useState<WorkEntry[]>(() => loadEntries());
  const [editingSchedule, setEditingSchedule] = useState(false);

  function handleSaveSchedule(s: StandardSchedule) {
    saveScheduleLS(s);
    setSchedule(s);
    setEditingSchedule(false);
  }

  function handleAddEntries(newEntries: Omit<WorkEntry, 'id'>[]) {
    const created = newEntries.map(e => ({ ...e, id: crypto.randomUUID() }));
    const updated = [...entries, ...created];
    saveEntriesLS(updated);
    setEntries(updated);
  }

  function handleUpdateEntry(id: string, entry: Omit<WorkEntry, 'id'>) {
    const updated = entries.map(e => e.id === id ? { ...entry, id } : e);
    saveEntriesLS(updated);
    setEntries(updated);
  }

  function handleDeleteEntry(id: string) {
    const updated = entries.filter(e => e.id !== id);
    saveEntriesLS(updated);
    setEntries(updated);
  }

  if (!schedule || editingSchedule) {
    return <SetupView onSave={handleSaveSchedule} initial={schedule} />;
  }

  return (
    <WeeklyLogView
      schedule={schedule}
      entries={entries}
      onAddEntries={handleAddEntries}
      onUpdateEntry={handleUpdateEntry}
      onDeleteEntry={handleDeleteEntry}
      onEditSchedule={() => setEditingSchedule(true)}
    />
  );
}
