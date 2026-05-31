import React, { useState, useEffect, useCallback } from 'react';
import { useWizardStore, getFamilyName } from './store';
import type { SectionState } from './store';
import {
  SECTIONS,
  SECTION_IDS,
  getSectionById,
  PER_CHILD_QUESTIONS,
  TONE_OPTIONS,
} from './engine/sections';
import type { Section, Question, QuestionOption, ChildInfo, DateRange, TextAndDateRanges, ToneOption } from './engine/sections';
import { generateSectionSummary } from './api/claude';
import { generateGuideHtml } from './guide';

// ── Colour tokens ─────────────────────────────────────────────────────────────
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
  optionBorder: '#e2e8f0',
  optionSelected: '#f0fdfa',
  optionSelectedBorder: '#14b8a6',
  optionSelectedText: '#0f766e',
};

// ── Option button styles ──────────────────────────────────────────────────────
function optionBtn(selected: boolean): React.CSSProperties {
  return {
    width: '100%',
    padding: '12px 16px',
    borderRadius: 10,
    textAlign: 'left',
    fontSize: 15,
    border: `${selected ? 2 : 1}px solid ${selected ? C.optionSelectedBorder : C.optionBorder}`,
    background: selected ? C.optionSelected : C.card,
    color: selected ? C.optionSelectedText : C.text,
    fontWeight: selected ? 600 : 400,
    cursor: 'pointer',
    transition: 'all .12s',
    display: 'block',
  };
}

// ── Format answers for AI summary ─────────────────────────────────────────────
function formatValue(val: unknown): string {
  if (val !== null && typeof val === 'object' && !Array.isArray(val) && 'text' in (val as object)) {
    const v = val as TextAndDateRanges;
    const parts: string[] = [];
    if (v.text.trim()) parts.push(v.text.trim());
    if (v.ranges.length > 0) parts.push('Blackout dates: ' + v.ranges.map(r => `${r.start} to ${r.end}`).join(', '));
    return parts.join(' — ');
  }
  if (Array.isArray(val)) {
    if (val.length === 0) return '';
    if (typeof val[0] === 'object' && val[0] !== null && 'start' in (val[0] as object)) {
      return (val as DateRange[]).map(r => `${r.start} to ${r.end}`).join(', ');
    }
    return (val as string[]).filter(Boolean).join(', ');
  }
  if (typeof val === 'boolean') return val ? 'Yes' : 'No';
  return String(val);
}

function formatAnswersForSummary(
  section: Section,
  answers: Record<string, unknown>,
  children: ChildInfo[],
): string {
  if (section.id === 'children') {
    const lines: string[] = [];
    children.forEach((child, i) => {
      lines.push(`\nChild: ${child.name}, age ${child.age}`);
      PER_CHILD_QUESTIONS.forEach(q => {
        const val = answers[`${q.id}_${i}`];
        if (val !== undefined && val !== null) {
          lines.push(`  ${q.text}: ${formatValue(val)}`);
        }
      });
    });
    return lines.join('\n');
  }

  const lines: string[] = [];
  section.questions.forEach(q => {
    const val = answers[q.id];
    if (val !== undefined && val !== null) {
      lines.push(`Q: ${q.text}\nA: ${formatValue(val)}`);
    }
    if (q.followUp && answers[q.followUp.id] !== undefined && answers[q.followUp.id] !== null) {
      lines.push(`Q: ${q.followUp.text}\nA: ${formatValue(answers[q.followUp.id])}`);
    }
  });
  return lines.join('\n\n');
}

// ── Tone selector screen ──────────────────────────────────────────────────────
function ToneSelector({ onSelect }: { onSelect: (t: ToneOption) => void }) {
  const [selected, setSelected] = useState<ToneOption>('balanced');

  return (
    <div style={{
      minHeight: '100vh', background: C.bg,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }}>
      <div style={{ maxWidth: 520, width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{ fontSize: 28, fontWeight: 800, color: C.navy, letterSpacing: '-1px', marginBottom: 6 }}>
            pair
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: C.navy, marginBottom: 8 }}>
            Household Guide Wizard
          </div>
          <p style={{ fontSize: 15, color: C.subtle }}>
            Before we start, choose the writing style for your guide.
          </p>
        </div>

        <div style={{
          background: C.card, borderRadius: 16, padding: 28,
          border: `1px solid ${C.border}`, marginBottom: 20,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: C.subtle, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 16 }}>
            Document tone
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {TONE_OPTIONS.map(opt => {
              const sel = selected === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setSelected(opt.value)}
                  style={{
                    padding: '14px 18px', borderRadius: 12, textAlign: 'left', cursor: 'pointer',
                    border: `2px solid ${sel ? C.teal : C.border}`,
                    background: sel ? C.tealLight : C.card,
                    transition: 'all .12s',
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: 15, color: sel ? C.tealDark : C.navy, marginBottom: 2 }}>
                    {sel ? '◉ ' : '○ '}{opt.label}
                  </div>
                  <div style={{ fontSize: 13, color: C.subtle }}>{opt.description}</div>
                </button>
              );
            })}
          </div>
        </div>

        <button
          onClick={() => onSelect(selected)}
          style={{
            width: '100%', padding: '15px 24px', borderRadius: 12, border: 'none',
            background: C.navy, color: '#fff', fontWeight: 700, fontSize: 16, cursor: 'pointer',
          }}
        >
          Start →
        </button>
      </div>
    </div>
  );
}

// ── Multi-select input ────────────────────────────────────────────────────────
interface MultiSelectProps {
  options: QuestionOption[];
  value: string[];
  onChange: (v: string[]) => void;
  freeTextValues: Record<string, string>;
  onFreeTextChange: (optionValue: string, text: string) => void;
}

function MultiSelectInput({ options, value, onChange, freeTextValues, onFreeTextChange }: MultiSelectProps) {
  const allOptions: QuestionOption[] = options;

  const groups: { label: string | null; items: QuestionOption[] }[] = [];
  let currentGroup: { label: string | null; items: QuestionOption[] } | null = null;

  for (const opt of allOptions) {
    const g = opt.group ?? null;
    if (!currentGroup || currentGroup.label !== g) {
      currentGroup = { label: g, items: [] };
      groups.push(currentGroup);
    }
    currentGroup.items.push(opt);
  }

  function toggle(optValue: string) {
    if (value.includes(optValue)) {
      onChange(value.filter(v => v !== optValue));
    } else {
      onChange([...value, optValue]);
    }
  }

  const selectableOptions = allOptions.filter(o => !o.freeText);
  const allSelected = selectableOptions.length > 0 && selectableOptions.every(o => value.includes(o.value));

  function toggleSelectAll() {
    if (allSelected) {
      onChange([]);
    } else {
      onChange(selectableOptions.map(o => o.value));
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <button
        onClick={toggleSelectAll}
        style={{
          alignSelf: 'flex-start', marginBottom: 10,
          padding: '5px 12px', borderRadius: 8, fontSize: 13, fontWeight: 600,
          border: `1px solid ${C.tealBorder}`, background: C.tealLight,
          color: C.tealDark, cursor: 'pointer',
        }}
      >
        {allSelected ? 'Deselect all' : 'Select all'}
      </button>
      {groups.map((group, gi) => (
        <div key={gi}>
          {group.label && (
            <div style={{
              fontSize: 11, fontWeight: 700, color: C.subtle,
              textTransform: 'uppercase', letterSpacing: 1,
              padding: '12px 0 6px',
            }}>
              {group.label}
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: group.label ? 4 : 6 }}>
            {group.items.map(opt => {
              const sel = value.includes(opt.value);
              return (
                <div key={opt.value}>
                  <button onClick={() => toggle(opt.value)} style={optionBtn(sel)}>
                    <span style={{ marginRight: 8 }}>{sel ? '☑' : '☐'}</span>
                    {opt.value}
                  </button>
                  {sel && opt.freeText && (
                    <input
                      type="text"
                      value={freeTextValues[opt.value] ?? ''}
                      onChange={e => onFreeTextChange(opt.value, e.target.value)}
                      placeholder="Please specify..."
                      style={{
                        display: 'block', width: '100%', marginTop: 6,
                        padding: '8px 12px', borderRadius: 8, fontSize: 14,
                        border: `1px solid ${C.border}`, color: C.text,
                      }}
                      onClick={e => e.stopPropagation()}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Single-select input ───────────────────────────────────────────────────────
function SingleSelectInput({ options, value, onChange }: {
  options: QuestionOption[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {options.map(opt => (
        <button key={opt.value} onClick={() => onChange(opt.value)} style={optionBtn(value === opt.value)}>
          <span style={{ marginRight: 8 }}>{value === opt.value ? '◉' : '○'}</span>
          {opt.value}
        </button>
      ))}
    </div>
  );
}

// ── Toggle input ──────────────────────────────────────────────────────────────
function ToggleInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div style={{ display: 'flex', gap: 12 }}>
      {['yes', 'no'].map(opt => {
        const sel = value === opt;
        return (
          <button key={opt} onClick={() => onChange(opt)} style={{
            flex: 1, padding: '14px 0', borderRadius: 12, fontSize: 16, fontWeight: sel ? 700 : 500,
            border: `2px solid ${sel ? C.teal : C.border}`,
            background: sel ? C.tealLight : C.card,
            color: sel ? C.tealDark : C.text,
            cursor: 'pointer', transition: 'all .12s',
          }}>
            {opt === 'yes' ? 'Yes' : 'No'}
          </button>
        );
      })}
    </div>
  );
}

// ── Text / Textarea inputs ────────────────────────────────────────────────────
function TextInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: '100%', padding: '12px 14px', borderRadius: 10, fontSize: 15,
        border: `1px solid ${C.border}`, color: C.text,
      }}
    />
  );
}

function TextareaInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={4}
      style={{
        width: '100%', padding: '12px 14px', borderRadius: 10, fontSize: 15,
        border: `1px solid ${C.border}`, color: C.text, resize: 'vertical',
      }}
    />
  );
}

// ── Children list input ───────────────────────────────────────────────────────
function ChildrenListInput({ value, onChange }: {
  value: ChildInfo[];
  onChange: (v: ChildInfo[]) => void;
}) {
  const children = value.length > 0 ? value : [{ name: '', age: '' }];

  function update(i: number, field: keyof ChildInfo, val: string) {
    const next = children.map((c, idx) => idx === i ? { ...c, [field]: val } : c);
    onChange(next);
  }

  function addChild() {
    onChange([...children, { name: '', age: '' }]);
  }

  function removeChild(i: number) {
    if (children.length === 1) return;
    onChange(children.filter((_, idx) => idx !== i));
  }

  return (
    <div>
      {children.map((child, i) => (
        <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 10, alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Name"
            value={child.name}
            onChange={e => update(i, 'name', e.target.value)}
            style={{
              flex: 2, padding: '10px 12px', borderRadius: 8, fontSize: 15,
              border: `1px solid ${C.border}`, color: C.text,
            }}
          />
          <input
            type="text"
            placeholder="Age"
            value={child.age}
            onChange={e => update(i, 'age', e.target.value)}
            style={{
              flex: 1, padding: '10px 12px', borderRadius: 8, fontSize: 15,
              border: `1px solid ${C.border}`, color: C.text,
            }}
          />
          {children.length > 1 && (
            <button
              onClick={() => removeChild(i)}
              style={{
                padding: '8px 12px', borderRadius: 8, border: `1px solid ${C.border}`,
                background: C.card, color: C.subtle, cursor: 'pointer', fontSize: 14,
              }}
            >
              ×
            </button>
          )}
        </div>
      ))}
      <button
        onClick={addChild}
        style={{
          padding: '9px 16px', borderRadius: 8, border: `1px dashed ${C.teal}`,
          background: C.tealLight, color: C.tealDark, fontSize: 14, fontWeight: 600,
          cursor: 'pointer', marginTop: 4,
        }}
      >
        + Add another child
      </button>
    </div>
  );
}

// ── Text list input (add-a-row custom items) ──────────────────────────────────
function TextListInput({ value, onChange }: {
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const rows = value.length > 0 ? value : [''];

  function update(i: number, val: string) {
    const next = rows.map((r, idx) => idx === i ? val : r);
    onChange(next);
  }

  function addRow() {
    onChange([...rows, '']);
  }

  function removeRow(i: number) {
    if (rows.length === 1) { onChange(['']); return; }
    onChange(rows.filter((_, idx) => idx !== i));
  }

  return (
    <div>
      {rows.map((row, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <input
            type="text"
            placeholder="e.g. Monthly gym membership"
            value={row}
            onChange={e => update(i, e.target.value)}
            style={{
              flex: 1, padding: '10px 12px', borderRadius: 8, fontSize: 15,
              border: `1px solid ${C.border}`, color: C.text,
            }}
          />
          <button
            onClick={() => removeRow(i)}
            style={{
              padding: '8px 12px', borderRadius: 8, border: `1px solid ${C.border}`,
              background: C.card, color: C.subtle, cursor: 'pointer', fontSize: 14,
            }}
          >
            ×
          </button>
        </div>
      ))}
      <button
        onClick={addRow}
        style={{
          padding: '9px 16px', borderRadius: 8, border: `1px dashed ${C.teal}`,
          background: C.tealLight, color: C.tealDark, fontSize: 14, fontWeight: 600,
          cursor: 'pointer', marginTop: 2,
        }}
      >
        + Add another
      </button>
    </div>
  );
}

// ── Date range list input ──────────────────────────────────────────────────────
function DateRangeListInput({ value, onChange }: {
  value: DateRange[];
  onChange: (v: DateRange[]) => void;
}) {
  const ranges = value.length > 0 ? value : [];

  function update(i: number, field: keyof DateRange, val: string) {
    const next = ranges.map((r, idx) => idx === i ? { ...r, [field]: val } : r);
    onChange(next);
  }

  function addRange() {
    onChange([...ranges, { start: '', end: '' }]);
  }

  function removeRange(i: number) {
    onChange(ranges.filter((_, idx) => idx !== i));
  }

  return (
    <div>
      {ranges.map((range, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
            <input
              type="date"
              value={range.start}
              onChange={e => update(i, 'start', e.target.value)}
              style={{
                flex: 1, padding: '10px 12px', borderRadius: 8, fontSize: 14,
                border: `1px solid ${C.border}`, color: C.text,
              }}
            />
            <span style={{ fontSize: 13, color: C.subtle, flexShrink: 0 }}>to</span>
            <input
              type="date"
              value={range.end}
              onChange={e => update(i, 'end', e.target.value)}
              style={{
                flex: 1, padding: '10px 12px', borderRadius: 8, fontSize: 14,
                border: `1px solid ${C.border}`, color: C.text,
              }}
            />
          </div>
          <button
            onClick={() => removeRange(i)}
            style={{
              padding: '8px 12px', borderRadius: 8, border: `1px solid ${C.border}`,
              background: C.card, color: C.subtle, cursor: 'pointer', fontSize: 14, flexShrink: 0,
            }}
          >
            ×
          </button>
        </div>
      ))}
      <button
        onClick={addRange}
        style={{
          padding: '9px 16px', borderRadius: 8, border: `1px dashed ${C.teal}`,
          background: C.tealLight, color: C.tealDark, fontSize: 14, fontWeight: 600,
          cursor: 'pointer', marginTop: 2,
        }}
      >
        + Add date range
      </button>
    </div>
  );
}

// ── Textarea + date range list (composite) ────────────────────────────────────
function TextareaAndDateRangeListInput({ value, onChange }: {
  value: TextAndDateRanges;
  onChange: (v: TextAndDateRanges) => void;
}) {
  const [showPicker, setShowPicker] = useState(value.ranges.length > 0);

  function updateText(text: string) {
    onChange({ ...value, text });
  }

  function updateRanges(ranges: DateRange[]) {
    onChange({ ...value, ranges });
  }

  return (
    <div>
      <TextareaInput
        value={value.text}
        onChange={updateText}
        placeholder="e.g. No vacation the last two weeks of August — school starts and we need full coverage"
      />
      <div style={{ marginTop: 14 }}>
        {!showPicker ? (
          <button
            onClick={() => setShowPicker(true)}
            style={{
              padding: '9px 16px', borderRadius: 8, border: `1px dashed ${C.teal}`,
              background: C.tealLight, color: C.tealDark, fontSize: 14, fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            + Select blackout dates
          </button>
        ) : (
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: C.subtle, marginBottom: 10 }}>
              Select blackout dates
            </div>
            <DateRangeListInput value={value.ranges} onChange={updateRanges} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── StarterBullets ────────────────────────────────────────────────────────────
function StarterBullets({
  bullets,
  currentValue,
  onSelect,
}: {
  bullets: string[];
  currentValue: string;
  onSelect: (v: unknown) => void;
}) {
  const [expanded, setExpanded] = React.useState(false);

  function append(bullet: string) {
    const prefix = currentValue.trim();
    onSelect(prefix ? `${prefix}\n\n${bullet}` : bullet);
  }

  return (
    <div style={{
      marginBottom: 14,
      background: C.tealLight,
      border: `1px solid ${C.tealBorder}`,
      borderRadius: 10,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', padding: '10px 14px',
          background: 'transparent', border: 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          cursor: 'pointer', gap: 8,
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 600, color: C.tealDark }}>
          💡 Need inspiration? See starter prompts
        </span>
        <span style={{ fontSize: 12, color: C.tealDark, flexShrink: 0 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>
      {expanded && (
        <div style={{ padding: '0 14px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <p style={{ fontSize: 12, color: C.subtle, margin: '0 0 8px' }}>
            Click any prompt to add it as a starting point. Edit freely — these are just to get you going.
          </p>
          {bullets.map((bullet, i) => (
            <button
              key={i}
              onClick={() => append(bullet)}
              style={{
                textAlign: 'left', padding: '8px 12px', borderRadius: 8,
                border: `1px solid ${C.tealBorder}`, background: C.card,
                fontSize: 13, color: C.text, cursor: 'pointer', lineHeight: 1.5,
                transition: 'background .1s',
              }}
            >
              {bullet}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── QuestionBlock ─────────────────────────────────────────────────────────────
interface QuestionBlockProps {
  question: Question;
  answer: unknown;
  onAnswer: (value: unknown) => void;
  followUpAnswer?: unknown;
  onFollowUpAnswer?: (value: unknown) => void;
  freeTextValues: Record<string, string>;
  onFreeTextChange: (opt: string, text: string) => void;
}

function QuestionBlock({
  question,
  answer,
  onAnswer,
  followUpAnswer,
  onFollowUpAnswer,
  freeTextValues,
  onFreeTextChange,
}: QuestionBlockProps) {
  const showFollowUp = question.followUp && answer === question.followUp.triggerValue;

  function renderInput(
    q: { inputType: string; options?: QuestionOption[]; placeholder?: string },
    val: unknown,
    onVal: (v: unknown) => void,
    ftValues: Record<string, string>,
    onFtChange: (opt: string, text: string) => void,
  ) {
    switch (q.inputType) {
      case 'text':
        return <TextInput value={(val as string) ?? ''} onChange={onVal} placeholder={q.placeholder} />;
      case 'textarea':
        return <TextareaInput value={(val as string) ?? ''} onChange={onVal} placeholder={q.placeholder} />;
      case 'single-select':
        return (
          <SingleSelectInput
            options={q.options ?? []}
            value={(val as string) ?? ''}
            onChange={onVal}
          />
        );
      case 'multi-select':
        return (
          <MultiSelectInput
            options={q.options ?? []}
            value={(val as string[]) ?? []}
            onChange={onVal}
            freeTextValues={ftValues}
            onFreeTextChange={onFtChange}
          />
        );
      case 'toggle':
        return <ToggleInput value={(val as string) ?? ''} onChange={onVal} />;
      case 'children-list':
        return <ChildrenListInput value={(val as ChildInfo[]) ?? []} onChange={onVal as (v: ChildInfo[]) => void} />;
      case 'text-list':
        return <TextListInput value={(val as string[]) ?? []} onChange={onVal as (v: string[]) => void} />;
      case 'date-range-list':
        return <DateRangeListInput value={(val as DateRange[]) ?? []} onChange={onVal as (v: DateRange[]) => void} />;
      case 'textarea-and-date-range-list': {
        const raw = val as TextAndDateRanges | null | undefined;
        const safeVal: TextAndDateRanges = { text: raw?.text ?? '', ranges: raw?.ranges ?? [] };
        return <TextareaAndDateRangeListInput value={safeVal} onChange={onVal as (v: TextAndDateRanges) => void} />;
      }
      default:
        return null;
    }
  }

  return (
    <div style={{
      background: C.card, borderRadius: 14, padding: 24,
      border: `1px solid ${C.border}`, marginBottom: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
        <h3 style={{ fontSize: 16, fontWeight: 700, color: C.navy, lineHeight: 1.4, flex: 1, margin: 0 }}>
          {question.text}
        </h3>
        {question.optional && (
          <span style={{ fontSize: 11, color: C.subtle, fontWeight: 500, flexShrink: 0, marginTop: 2 }}>
            Optional
          </span>
        )}
      </div>
      {question.subtext && (
        <p style={{ fontSize: 13, color: C.subtle, marginBottom: 14, marginTop: 2 }}>{question.subtext}</p>
      )}
      {!question.subtext && <div style={{ marginBottom: 14 }} />}

      {question.starterBullets && question.starterBullets.length > 0 && (
        <StarterBullets
          bullets={question.starterBullets}
          currentValue={(answer as string) ?? ''}
          onSelect={onAnswer}
        />
      )}

      {renderInput(question, answer, onAnswer, freeTextValues, onFreeTextChange)}

      {showFollowUp && question.followUp && (
        <div style={{
          marginTop: 16, paddingLeft: 16,
          borderLeft: `3px solid ${C.tealBorder}`,
        }}>
          <h4 style={{ fontSize: 15, fontWeight: 700, color: C.navy, marginBottom: 10, marginTop: 0 }}>
            {question.followUp.text}
          </h4>
          {renderInput(
            question.followUp,
            followUpAnswer,
            onFollowUpAnswer ?? (() => {}),
            {},
            () => {},
          )}
        </div>
      )}
    </div>
  );
}

// ── AllQuestionsView ──────────────────────────────────────────────────────────
interface AllQuestionsViewProps {
  section: Section;
  sectionId: string;
  sectionState: SectionState;
  children: ChildInfo[];
  onSetAnswer: (sectionId: string, qId: string, value: unknown) => void;
  onSetChildren: (children: ChildInfo[]) => void;
  onGenerateSummary: () => void;
  phase: SectionPhase;
}

// Parse "Value: freetext" back into { [value]: freetext }
function parseFreeTextFromStored(storedValues: unknown[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const v of storedValues) {
    if (typeof v !== 'string') continue;
    const colonIdx = v.indexOf(': ');
    if (colonIdx !== -1) {
      const key = v.slice(0, colonIdx);
      const text = v.slice(colonIdx + 2);
      map[key] = text;
    }
  }
  return map;
}

function AllQuestionsView({
  section,
  sectionId,
  sectionState,
  children,
  onSetAnswer,
  onSetChildren,
  onGenerateSummary,
  phase,
}: AllQuestionsViewProps) {
  const { answers } = sectionState;
  const isChildrenSection = section.id === 'children';

  // freeTextMap: { questionId: { optionValue: freeText } }
  const [freeTextMap, setFreeTextMap] = useState<Record<string, Record<string, string>>>(() => {
    // Initialize from stored values
    const map: Record<string, Record<string, string>> = {};
    for (const q of section.questions) {
      const stored = answers[q.id];
      if (Array.isArray(stored)) {
        map[q.id] = parseFreeTextFromStored(stored as unknown[]);
      }
    }
    if (isChildrenSection) {
      for (const q of PER_CHILD_QUESTIONS) {
        children.forEach((_, i) => {
          const key = `${q.id}_${i}`;
          const stored = answers[key];
          if (Array.isArray(stored)) {
            map[key] = parseFreeTextFromStored(stored as unknown[]);
          }
        });
      }
    }
    return map;
  });

  function handleAnswer(questionId: string, value: unknown) {
    onSetAnswer(sectionId, questionId, value);
  }

  function handleMultiSelectAnswer(questionId: string, rawValues: string[]) {
    const ft = freeTextMap[questionId] ?? {};
    const merged = rawValues.map(v => {
      const text = ft[v];
      return text && text.trim() ? `${v}: ${text.trim()}` : v;
    });
    onSetAnswer(sectionId, questionId, merged);
  }

  function handleFreeTextChange(questionId: string, optValue: string, text: string) {
    const updatedFt = { ...(freeTextMap[questionId] ?? {}), [optValue]: text };
    setFreeTextMap(prev => ({ ...prev, [questionId]: updatedFt }));
    // Re-merge into stored value
    const currentArr = answers[questionId];
    if (Array.isArray(currentArr)) {
      const rawValues = (currentArr as string[]).map(v => {
        const colonIdx = v.indexOf(': ');
        return colonIdx !== -1 ? v.slice(0, colonIdx) : v;
      });
      const merged = rawValues.map(v => {
        const t = updatedFt[v];
        return t && t.trim() ? `${v}: ${t.trim()}` : v;
      });
      onSetAnswer(sectionId, questionId, merged);
    }
  }

  function getMultiSelectDisplayValue(questionId: string): string[] {
    const stored = answers[questionId];
    if (!Array.isArray(stored)) return [];
    return (stored as string[]).map(v => {
      const colonIdx = v.indexOf(': ');
      return colonIdx !== -1 ? v.slice(0, colonIdx) : v;
    });
  }

  // Count answered questions for progress
  function countAnswered(): { answered: number; total: number } {
    if (isChildrenSection) {
      const childList = answers['children_list'] as ChildInfo[] | undefined;
      const validChildren = (childList ?? []).filter(c => c.name.trim().length > 0);
      let total = 1; // children_list question
      let answered = validChildren.length > 0 ? 1 : 0;
      validChildren.forEach((_, i) => {
        PER_CHILD_QUESTIONS.forEach(q => {
          total++;
          const val = answers[`${q.id}_${i}`];
          const hasFollowUp = q.followUp && answers[`${q.id}_${i}`] === q.followUp.triggerValue;
          if (hasFollowUp) total++;
          if (val !== undefined && val !== null && val !== '' && !(Array.isArray(val) && (val as unknown[]).length === 0)) answered++;
        });
      });
      return { answered, total };
    }
    let total = 0;
    let answered = 0;
    for (const q of section.questions) {
      total++;
      const val = answers[q.id];
      if (val !== undefined && val !== null && val !== '' && !(Array.isArray(val) && (val as unknown[]).length === 0)) answered++;
      if (q.followUp && answers[q.id] === q.followUp.triggerValue) {
        total++;
        const fuVal = answers[q.followUp.id];
        if (fuVal !== undefined && fuVal !== null && fuVal !== '') answered++;
      }
    }
    return { answered, total };
  }

  const { answered, total } = countAnswered();
  const progressPct = total > 0 ? Math.round((answered / total) * 100) : 0;

  const hasAnyAnswer = answered > 0;

  const childListStored = answers['children_list'] as ChildInfo[] | undefined;
  const validChildren = (childListStored ?? []).filter(c => c.name.trim().length > 0);

  // Tab state for children section
  const [selectedChildIdx, setSelectedChildIdx] = useState(0);

  // Clamp selected index when children list shrinks
  const activeIdx = Math.min(selectedChildIdx, Math.max(0, validChildren.length - 1));

  function childIcon(age: string): string {
    const n = parseInt(age, 10);
    if (isNaN(n)) return '🧒';
    if (n <= 2) return '👶';
    if (n <= 6) return '🧒';
    return '👦';
  }

  function isChildComplete(i: number): boolean {
    return PER_CHILD_QUESTIONS
      .filter(q => !q.optional)
      .every(q => {
        const val = answers[`${q.id}_${i}`];
        return val !== undefined && val !== null && val !== '' && !(Array.isArray(val) && (val as unknown[]).length === 0);
      });
  }

  function renderChildQuestions(i: number) {
    return PER_CHILD_QUESTIONS.map(q => {
      const key = `${q.id}_${i}`;
      const storedVal = answers[key];
      const ft = freeTextMap[key] ?? {};
      const displayVal = q.inputType === 'multi-select'
        ? (() => {
          if (!Array.isArray(storedVal)) return [];
          return (storedVal as string[]).map(v => {
            const colonIdx = v.indexOf(': ');
            return colonIdx !== -1 ? v.slice(0, colonIdx) : v;
          });
        })()
        : storedVal;

      return (
        <QuestionBlock
          key={key}
          question={q}
          answer={displayVal}
          onAnswer={val => {
            if (q.inputType === 'multi-select') {
              const rawArr = val as string[];
              const currentFt = freeTextMap[key] ?? {};
              const merged = rawArr.map(v => {
                const t = currentFt[v];
                return t && t.trim() ? `${v}: ${t.trim()}` : v;
              });
              onSetAnswer(sectionId, key, merged);
            } else {
              onSetAnswer(sectionId, key, val);
            }
          }}
          freeTextValues={ft}
          onFreeTextChange={(opt, text) => {
            const updatedFt = { ...ft, [opt]: text };
            setFreeTextMap(prev => ({ ...prev, [key]: updatedFt }));
            const currentArr = answers[key];
            if (Array.isArray(currentArr)) {
              const rawValues = (currentArr as string[]).map(v => {
                const colonIdx = v.indexOf(': ');
                return colonIdx !== -1 ? v.slice(0, colonIdx) : v;
              });
              const merged = rawValues.map(v => {
                const t = updatedFt[v];
                return t && t.trim() ? `${v}: ${t.trim()}` : v;
              });
              onSetAnswer(sectionId, key, merged);
            }
          }}
        />
      );
    });
  }

  return (
    <div style={{ maxWidth: 680, margin: '0 auto', padding: '32px 24px 120px' }}>
      {/* Section header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
          <span style={{ fontSize: 28 }}>{section.icon}</span>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: C.navy, margin: 0 }}>{section.title}</h1>
          <span style={{
            fontSize: 12, color: C.tealDark, background: C.tealLight,
            border: `1px solid ${C.tealBorder}`, borderRadius: 20,
            padding: '2px 10px', fontWeight: 600, flexShrink: 0,
          }}>
            ~{section.estimatedMinutes} min{section.id === 'children' ? ' per child' : ''}
          </span>
        </div>
        {section.description && (
          <p style={{ fontSize: 13, color: C.subtle, marginBottom: 12 }}>{section.description}</p>
        )}
        {/* Progress bar */}
        <div style={{ background: C.border, borderRadius: 4, height: 4, marginTop: 8 }}>
          <div style={{
            height: '100%', background: C.teal, borderRadius: 4,
            width: `${progressPct}%`, transition: 'width .3s',
          }} />
        </div>
        <div style={{ fontSize: 12, color: C.subtle, marginTop: 4 }}>
          {answered} of {total} questions answered
        </div>
      </div>

      {/* Questions */}
      {isChildrenSection ? (
        <>
          {/* Children-list input — always visible at top */}
          <QuestionBlock
            question={section.questions[0]}
            answer={childListStored ?? [{ name: '', age: '' }]}
            onAnswer={val => {
              const list = val as ChildInfo[];
              onSetAnswer(sectionId, 'children_list', list);
              onSetChildren(list.filter(c => c.name.trim().length > 0));
            }}
            freeTextValues={{}}
            onFreeTextChange={() => {}}
          />

          {validChildren.length === 0 ? (
            <div style={{
              textAlign: 'center', padding: '32px 24px',
              color: C.subtle, fontSize: 14,
              background: C.card, borderRadius: 14, border: `1px solid ${C.border}`,
            }}>
              Add your children above to see their profiles
            </div>
          ) : (
            <>
              {/* Sticky tab bar */}
              <div style={{
                position: 'sticky', top: 0, zIndex: 10,
                background: C.bg, paddingBottom: 12, paddingTop: 4,
                marginBottom: 4,
              }}>
                <div style={{
                  display: 'flex', gap: 8, overflowX: 'auto',
                  paddingBottom: 2,
                }}>
                  {validChildren.map((child, i) => {
                    const active = i === activeIdx;
                    const complete = isChildComplete(i);
                    return (
                      <button
                        key={i}
                        onClick={() => setSelectedChildIdx(i)}
                        style={{
                          display: 'flex', flexDirection: 'column', alignItems: 'center',
                          gap: 4, padding: '10px 18px', borderRadius: 12, cursor: 'pointer',
                          flexShrink: 0, position: 'relative',
                          border: `2px solid ${active ? C.teal : C.border}`,
                          background: active ? C.tealLight : C.card,
                          transition: 'all .15s',
                        }}
                      >
                        <span style={{ fontSize: 22 }}>{childIcon(child.age)}</span>
                        <span style={{
                          fontSize: 12, fontWeight: 700,
                          color: active ? C.tealDark : C.text,
                          maxWidth: 72, overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {child.name}
                        </span>
                        {complete && (
                          <span style={{
                            position: 'absolute', top: 6, right: 6,
                            width: 16, height: 16, borderRadius: '50%',
                            background: '#22c55e', color: '#fff',
                            fontSize: 10, fontWeight: 700,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }}>
                            ✓
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Active child profile */}
              <div>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20,
                }}>
                  <span style={{ fontSize: 26 }}>{childIcon(validChildren[activeIdx].age)}</span>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: C.navy }}>
                      {validChildren[activeIdx].name}
                      {validChildren[activeIdx].age ? `, age ${validChildren[activeIdx].age}` : ''}
                    </div>
                    {isChildComplete(activeIdx) && (
                      <div style={{ fontSize: 12, color: '#22c55e', fontWeight: 600 }}>
                        ✓ Profile complete
                      </div>
                    )}
                  </div>
                </div>
                {renderChildQuestions(activeIdx)}
              </div>
            </>
          )}
        </>
      ) : (
        section.questions.map(q => {
          const ans = q.inputType === 'multi-select' ? getMultiSelectDisplayValue(q.id) : answers[q.id];
          const fuId = q.followUp?.id;
          const fuAns = fuId ? answers[fuId] : undefined;

          return (
            <QuestionBlock
              key={q.id}
              question={q}
              answer={ans}
              onAnswer={val => {
                if (q.inputType === 'multi-select') {
                  handleMultiSelectAnswer(q.id, val as string[]);
                } else {
                  handleAnswer(q.id, val);
                }
              }}
              followUpAnswer={fuAns}
              onFollowUpAnswer={fuId ? (val => handleAnswer(fuId, val)) : undefined}
              freeTextValues={freeTextMap[q.id] ?? {}}
              onFreeTextChange={(opt, text) => handleFreeTextChange(q.id, opt, text)}
            />
          );
        })
      )}

      {/* Sticky bottom bar */}
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0,
        background: C.card, borderTop: `1px solid ${C.border}`,
        padding: '14px 24px',
        display: 'flex', justifyContent: 'center',
      }}>
        <div style={{ maxWidth: 680, width: '100%' }}>
          <button
            onClick={onGenerateSummary}
            disabled={!hasAnyAnswer || phase === 'summarizing'}
            style={{
              width: '100%', padding: '14px 24px', borderRadius: 12, border: 'none',
              background: hasAnyAnswer && phase !== 'summarizing' ? C.navy : C.border,
              color: hasAnyAnswer && phase !== 'summarizing' ? '#fff' : C.subtle,
              fontWeight: 700, fontSize: 16,
              cursor: hasAnyAnswer && phase !== 'summarizing' ? 'pointer' : 'not-allowed',
              transition: 'all .12s',
            }}
          >
            {phase === 'summarizing' ? 'Generating summary…' : 'Generate Summary →'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── SummaryView ───────────────────────────────────────────────────────────────
interface SummaryViewProps {
  section: Section;
  sectionIdx: number;
  sectionState: SectionState;
  onGoToNext: () => void;
  onReset: (sectionId: string) => void;
}

function SummaryView({ section, sectionIdx, sectionState, onGoToNext, onReset }: SummaryViewProps) {
  const isLast = sectionIdx === SECTION_IDS.length - 1;
  const nextSection = getSectionById(SECTION_IDS[sectionIdx + 1]);

  return (
    <div style={{ maxWidth: 680, margin: '0 auto', padding: '36px 24px 100px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <span style={{
          background: C.teal, color: '#fff', borderRadius: '50%',
          width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontWeight: 800, fontSize: 15, flexShrink: 0,
        }}>✓</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.tealDark, textTransform: 'uppercase', letterSpacing: 1 }}>
          Section {sectionIdx + 1} complete
        </span>
      </div>
      <div style={{ fontSize: 28, marginBottom: 4 }}>{section.icon}</div>
      <h1 style={{ fontSize: 26, fontWeight: 800, color: C.navy, marginBottom: 6 }}>{section.title}</h1>
      <p style={{ fontSize: 14, color: C.subtle, marginBottom: 24 }}>
        Here's a summary of what you shared:
      </p>
      <div style={{
        background: C.card, borderRadius: 14, padding: 28,
        border: `1px solid ${C.border}`, borderLeft: `4px solid ${C.teal}`, marginBottom: 28,
      }}>
        <p style={{ fontSize: 15, lineHeight: 1.85, color: C.text, whiteSpace: 'pre-wrap' }}>
          {sectionState.summary}
        </p>
      </div>
      <button onClick={onGoToNext} style={{
        width: '100%', padding: '15px 24px', borderRadius: 12, border: 'none',
        background: isLast ? C.teal : C.navy,
        color: '#fff', fontWeight: 700, fontSize: 16, cursor: 'pointer',
        marginBottom: 10,
      }}>
        {isLast ? 'Preview Guide' : `Continue to ${nextSection?.title ?? 'next'} →`}
      </button>
      <button
        onClick={() => onReset(section.id)}
        style={{
          width: '100%', padding: '13px 24px', borderRadius: 12,
          border: `1px solid ${C.border}`, background: C.card,
          color: C.subtle, fontWeight: 500, fontSize: 14, cursor: 'pointer',
        }}
      >
        ✏️ Edit answers
      </button>
    </div>
  );
}

// ── SectionView — orchestrates AllQuestionsView ↔ SummaryView ────────────────
type SectionPhase = 'questioning' | 'summarizing' | 'summary';

interface SectionViewProps {
  sectionId: string;
  sectionIdx: number;
  sectionState: SectionState;
  tone: ToneOption;
  children: ChildInfo[];
  currentChildIndex: number;
  currentChildQuestionIndex: number;
  onSectionComplete: (sectionId: string) => void;
  onAdvanceChildQuestion: () => void;
  onSetAnswer: (sectionId: string, qId: string, value: unknown) => void;
  onSetChildren: (children: ChildInfo[]) => void;
  onSetSummary: (sectionId: string, summary: string) => void;
  onMarkComplete: (sectionId: string) => void;
  onReset: (sectionId: string) => void;
  onGoToNext: () => void;
}

function SectionView({
  sectionId,
  sectionIdx,
  sectionState,
  tone,
  children,
  onSetAnswer,
  onSetChildren,
  onSetSummary,
  onMarkComplete,
  onReset,
  onGoToNext,
}: SectionViewProps) {
  const section = getSectionById(sectionId)!;
  const { answers } = sectionState;

  const [phase, setPhase] = useState<SectionPhase>(
    sectionState.complete && sectionState.summary ? 'summary' : 'questioning'
  );
  const [error, setError] = useState<string | null>(null);

  // Reset local state when section changes
  useEffect(() => {
    setPhase(sectionState.complete && sectionState.summary ? 'summary' : 'questioning');
    setError(null);
  }, [sectionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleGenerateSummary = useCallback(async () => {
    setPhase('summarizing');
    setError(null);
    try {
      const formattedQA = formatAnswersForSummary(section, answers, children);
      const summary = await generateSectionSummary(section.title, formattedQA, tone);
      onSetSummary(sectionId, summary);
      onMarkComplete(sectionId);
      setPhase('summary');
    } catch (e) {
      setError('Failed to generate summary. Please try again.');
      setPhase('questioning');
    }
  }, [sectionId, section, answers, children, tone, onMarkComplete, onSetSummary]);

  const handleReset = useCallback((id: string) => {
    onReset(id);
    setPhase('questioning');
    setError(null);
  }, [onReset]);

  if (phase === 'summarizing' && sectionState.summary === '') {
    return (
      <div style={{ maxWidth: 680, margin: '0 auto', padding: '80px 24px', textAlign: 'center' }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>✍️</div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: C.navy, marginBottom: 8 }}>
          Generating your summary…
        </h2>
        <p style={{ color: C.subtle, fontSize: 14 }}>
          Putting everything you shared into plain language for your au pair.
        </p>
      </div>
    );
  }

  if (phase === 'summary' && sectionState.summary) {
    return (
      <SummaryView
        section={section}
        sectionIdx={sectionIdx}
        sectionState={sectionState}
        onGoToNext={onGoToNext}
        onReset={handleReset}
      />
    );
  }

  return (
    <>
      {error && (
        <div style={{
          maxWidth: 680, margin: '16px auto 0', padding: '0 24px',
        }}>
          <div style={{
            background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 10,
            padding: '12px 16px', fontSize: 14, color: '#b91c1c',
          }}>
            {error}
          </div>
        </div>
      )}
      <AllQuestionsView
        section={section}
        sectionId={sectionId}
        sectionState={sectionState}
        children={children}
        onSetAnswer={onSetAnswer}
        onSetChildren={onSetChildren}
        onGenerateSummary={handleGenerateSummary}
        phase={phase}
      />
    </>
  );
}

// ── LandingPage ───────────────────────────────────────────────────────────────
function LandingPage({ onGetStarted }: { onGetStarted: () => void }) {
  return (
    <div style={{ minHeight: '100vh', background: C.bg, fontFamily: 'inherit' }}>
      {/* Hero */}
      <div style={{
        background: C.navy, color: '#fff',
        padding: '64px 24px 56px',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: 32, fontWeight: 800, color: '#fff', letterSpacing: '-1px', marginBottom: 20 }}>
          pair
        </div>
        <h1 style={{
          fontSize: 36, fontWeight: 800, color: '#fff', letterSpacing: '-1px',
          marginBottom: 16, maxWidth: 560, margin: '0 auto 16px',
        }}>
          Create a guide your au pair will actually use.
        </h1>
        <p style={{
          fontSize: 16, color: '#94a3b8', maxWidth: 520, margin: '0 auto 36px', lineHeight: 1.7,
        }}>
          A personalised household guide takes about 15 minutes to complete and gives your au pair everything they need to feel confident and at home from day one.
        </p>
        <button
          onClick={onGetStarted}
          style={{
            display: 'block', margin: '0 auto',
            maxWidth: 480, width: '100%',
            padding: '16px 32px', borderRadius: 12, border: 'none',
            background: C.teal, color: '#fff',
            fontWeight: 700, fontSize: 17, cursor: 'pointer',
            transition: 'all .12s',
          }}
        >
          Get Started →
        </button>
      </div>

      {/* Why it matters */}
      <div style={{ maxWidth: 860, margin: '0 auto', padding: '56px 24px 0' }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: C.navy, textAlign: 'center', marginBottom: 32 }}>
          Why it matters
        </h2>
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', justifyContent: 'center' }}>
          {[
            {
              icon: '📋',
              title: 'Everything in one place',
              desc: 'Daily routines, house rules, and family expectations, all clearly written.',
            },
            {
              icon: '🤝',
              title: 'Less explaining, more connecting',
              desc: 'Spend the first week bonding, not briefing.',
            },
            {
              icon: '✏️',
              title: 'Editable any time',
              desc: "Update it as your family evolves. Your au pair always has the latest version.",
            },
          ].map(card => (
            <div key={card.title} style={{
              flex: '1 1 220px', maxWidth: 260,
              background: C.card, borderRadius: 16, padding: '28px 24px',
              border: `1px solid ${C.border}`, textAlign: 'center',
            }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>{card.icon}</div>
              <div style={{ fontWeight: 700, fontSize: 16, color: C.navy, marginBottom: 8 }}>{card.title}</div>
              <div style={{ fontSize: 14, color: C.subtle, lineHeight: 1.6 }}>{card.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Time estimate */}
      <div style={{ maxWidth: 680, margin: '0 auto', padding: '56px 24px 0' }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: C.navy, marginBottom: 8 }}>
          How long does it take?
        </h2>
        <p style={{ fontSize: 14, color: C.subtle, marginBottom: 24 }}>
          Complete sections in any order. You can save and come back at any time.
        </p>
        <div style={{
          background: C.card, borderRadius: 16, border: `1px solid ${C.border}`, overflow: 'hidden',
        }}>
          {[
            { icon: '🏡', title: 'Your Family', time: '~2 min' },
            { icon: '👨‍👩‍👧‍👦', title: 'Your Children', time: '~3 min per child' },
            { icon: '📋', title: 'Childcare Responsibilities', time: '~3 min' },
            { icon: '🏠', title: 'House Rules', time: '~3 min' },
            { icon: '✨', title: 'Benefits & Practical Details', time: '~2 min' },
            { icon: '💬', title: 'Parenting Style & Philosophy', time: '~2 min' },
          ].map((row, i) => (
            <div key={row.title} style={{
              display: 'flex', alignItems: 'center', gap: 14,
              padding: '14px 20px',
              borderBottom: i < 5 ? `1px solid ${C.border}` : 'none',
            }}>
              <span style={{ fontSize: 20, width: 28, textAlign: 'center', flexShrink: 0 }}>{row.icon}</span>
              <span style={{ flex: 1, fontSize: 15, color: C.text, fontWeight: 500 }}>{row.title}</span>
              <span style={{ fontSize: 13, color: C.subtle, fontWeight: 500 }}>{row.time}</span>
            </div>
          ))}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14,
            padding: '14px 20px',
            background: C.tealLight,
            borderTop: `2px solid ${C.tealBorder}`,
          }}>
            <span style={{ width: 28, flexShrink: 0 }} />
            <span style={{ flex: 1, fontSize: 15, color: C.tealDark, fontWeight: 700 }}>Total</span>
            <span style={{ fontSize: 13, color: C.tealDark, fontWeight: 700 }}>~15 min for 1 child</span>
          </div>
        </div>
      </div>

      {/* Sample guide preview */}
      <div style={{ maxWidth: 680, margin: '0 auto', padding: '56px 24px 0' }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: C.navy, marginBottom: 8 }}>
          What you'll get
        </h2>
        <div style={{ marginBottom: 12 }}>
          <span style={{
            fontSize: 11, color: C.subtle, background: C.bg,
            border: `1px solid ${C.border}`, borderRadius: 20,
            padding: '3px 10px', fontWeight: 500,
          }}>
            Sample output — your guide will be personalised to your family
          </span>
        </div>
        <div style={{
          background: C.card, borderRadius: 16, padding: '28px 32px',
          border: `1px solid ${C.border}`, borderLeft: `4px solid ${C.teal}`,
          fontSize: 14, lineHeight: 1.8, color: C.text,
        }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: C.subtle, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 20 }}>
            THE ANDERSON FAMILY — HOUSEHOLD GUIDE
          </div>
          <div style={{ fontWeight: 700, color: C.navy, marginBottom: 8 }}>Your Family</div>
          <p style={{ marginBottom: 20 }}>
            Sarah and James are a warm, close-knit family living in Boston with their two children. They describe their home as high-energy and active, with a real emphasis on doing things together. Having an au pair matters to them because they want reliable, consistent childcare and someone who becomes a genuine part of the family. Day-to-day communication happens mainly over WhatsApp, with a quick verbal debrief at handover each evening.
          </p>
          <div style={{ fontWeight: 700, color: C.navy, marginBottom: 8 }}>Your Children</div>
          <p style={{ marginBottom: 16 }}>
            Emma is 3 years old. She has no dietary restrictions. Emma is fully potty trained and loves arts and crafts, pretend play, and anything outdoors. She is warm, affectionate, and high-energy — she needs a consistent daily routine and does best when given advance notice before transitions. When Emma is upset, the approach that works best is staying calm, offering a hug, and giving her a moment before re-engaging.
          </p>
          <p>
            Lucas is 8 years old. He has a moderate nut allergy — always check labels. Lucas is intellectually curious and competitive, and loves building toys and board games. He is easy-going but strong-willed when it comes to screen time. Homework support is needed Monday through Thursday after school.
          </p>
        </div>
      </div>

      {/* Second Get Started */}
      <div style={{ maxWidth: 480, margin: '0 auto', padding: '48px 24px 64px', textAlign: 'center' }}>
        <button
          onClick={onGetStarted}
          style={{
            display: 'block', width: '100%',
            padding: '16px 32px', borderRadius: 12, border: 'none',
            background: C.navy, color: '#fff',
            fontWeight: 700, fontSize: 17, cursor: 'pointer',
          }}
        >
          Get Started →
        </button>
      </div>
    </div>
  );
}

// ── MainWizard ────────────────────────────────────────────────────────────────
function MainWizard() {
  const store = useWizardStore();
  const { state } = store;
  const [showReset, setShowReset] = useState(false);

  const sectionId = state.currentSectionId;
  const sectionIdx = SECTION_IDS.indexOf(sectionId);
  const sectionState = state.sections[sectionId];

  const familyName = getFamilyName(state);

  const hasSummaries = SECTIONS.some(s => !!state.sections[s.id].summary);

  function handleGoToSection(id: string) {
    store.goToSection(id);
  }

  function handleGoToNext() {
    const isLast = sectionIdx === SECTION_IDS.length - 1;
    if (isLast) {
      handleGenerateDraft();
    } else {
      store.goToSection(SECTION_IDS[sectionIdx + 1]);
    }
  }

  function handleGenerateDraft() {
    const summaries: Record<string, string> = {};
    for (const s of SECTIONS) {
      if (state.sections[s.id].summary) {
        summaries[s.id] = state.sections[s.id].summary;
      }
    }
    if (Object.keys(summaries).length === 0) return;
    const html = generateGuideHtml(familyName, summaries);
    const win = window.open('', '_blank');
    if (win) { win.document.write(html); win.document.close(); }
  }

  return (
    <div style={{ minHeight: '100vh', background: C.bg }}>
      {/* Fixed header */}
      <header style={{
        background: '#fff', borderBottom: `1px solid ${C.border}`,
        padding: '0 24px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        height: 60, position: 'fixed', top: 0, left: 0, right: 0, zIndex: 20,
      }}>
        <span style={{ fontWeight: 800, fontSize: 22, color: C.navy, letterSpacing: '-0.5px' }}>pair</span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            onClick={handleGenerateDraft}
            disabled={!hasSummaries}
            title={!hasSummaries ? 'Complete at least one section to generate a draft' : undefined}
            style={{
              padding: '7px 16px', borderRadius: 8,
              border: `2px solid ${hasSummaries ? C.teal : C.border}`,
              background: 'transparent',
              color: hasSummaries ? C.tealDark : C.subtle,
              fontWeight: 600, fontSize: 13,
              cursor: hasSummaries ? 'pointer' : 'not-allowed',
              transition: 'all .12s',
            }}
          >
            Generate Draft
          </button>
          <button
            onClick={() => setShowReset(true)}
            style={{
              padding: '6px 14px', borderRadius: 8, border: 'none',
              background: C.bg, color: C.subtle,
              cursor: 'pointer', fontSize: 13,
            }}
          >
            Reset
          </button>
        </div>
      </header>

      {/* Body below fixed header */}
      <div style={{ display: 'flex', minHeight: '100vh', paddingTop: 60 }}>
        {/* Sidebar */}
        <aside style={{
          width: 220, flexShrink: 0, background: C.card, borderRight: `1px solid ${C.border}`,
          padding: '20px 0', position: 'fixed', top: 60, bottom: 0,
          overflowY: 'auto', zIndex: 10,
        }}>
          {SECTIONS.map((sec, i) => {
            const done = state.sections[sec.id].complete;
            const active = sec.id === sectionId;
            return (
              <button
                key={sec.id}
                onClick={() => handleGoToSection(sec.id)}
                style={{
                  width: '100%', padding: '10px 16px',
                  background: active ? C.tealLight : 'transparent',
                  border: 'none', borderLeft: `3px solid ${active ? C.teal : 'transparent'}`,
                  cursor: 'pointer', textAlign: 'left',
                  display: 'flex', alignItems: 'center', gap: 10,
                }}
              >
                <span style={{ fontSize: 16, flexShrink: 0 }}>{sec.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13, fontWeight: active ? 700 : 500, lineHeight: 1.3,
                    color: active ? C.tealDark : done ? C.subtle : C.text,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {sec.title}
                  </div>
                  <div style={{ fontSize: 11, color: C.subtle, marginTop: 1 }}>
                    ~{sec.estimatedMinutes} min{sec.id === 'children' ? ' per child' : ''}
                  </div>
                </div>
                {done ? (
                  <span style={{
                    width: 20, height: 20, borderRadius: '50%',
                    background: C.teal, color: '#fff',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, fontWeight: 700, flexShrink: 0,
                  }}>✓</span>
                ) : (
                  <span style={{
                    width: 20, height: 20, borderRadius: '50%',
                    border: `2px solid ${active ? C.teal : C.border}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, fontWeight: 700, color: active ? C.tealDark : C.subtle,
                    flexShrink: 0,
                  }}>{i + 1}</span>
                )}
              </button>
            );
          })}
        </aside>

        {/* Main content — offset by sidebar width */}
        <main style={{ flex: 1, marginLeft: 220, minWidth: 0 }}>
          <SectionView
            key={sectionId}
            sectionId={sectionId}
            sectionIdx={sectionIdx}
            sectionState={sectionState}
            tone={state.tone!}
            children={state.children}
            currentChildIndex={state.currentChildIndex}
            currentChildQuestionIndex={state.currentChildQuestionIndex}
            onSectionComplete={store.markSectionComplete}
            onAdvanceChildQuestion={() => store.advanceChildQuestion(PER_CHILD_QUESTIONS.length)}
            onSetAnswer={store.setAnswer}
            onSetChildren={store.setChildren}
            onSetSummary={store.setSummary}
            onMarkComplete={store.markSectionComplete}
            onReset={store.resetSection}
            onGoToNext={handleGoToNext}
          />
        </main>
      </div>

      {/* Reset confirmation */}
      {showReset && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
        }}>
          <div style={{ background: C.card, borderRadius: 16, padding: 28, maxWidth: 380, width: '90%' }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: C.navy, marginBottom: 8 }}>Reset all answers?</h3>
            <p style={{ color: C.subtle, fontSize: 14, marginBottom: 20 }}>
              This will clear everything, including all answers and summaries.
            </p>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setShowReset(false)} style={{
                flex: 1, padding: '11px', borderRadius: 10, border: `2px solid ${C.border}`,
                background: 'transparent', color: C.subtle, fontWeight: 600, cursor: 'pointer',
              }}>Cancel</button>
              <button onClick={() => { store.resetAll(); setShowReset(false); }} style={{
                flex: 1, padding: '11px', borderRadius: 10, border: 'none',
                background: '#dc2626', color: '#fff', fontWeight: 700, cursor: 'pointer',
              }}>Reset</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const store = useWizardStore();
  const { state } = store;
  const [showToneSelector, setShowToneSelector] = useState(false);

  if (state.tone === null) {
    if (showToneSelector) {
      return (
        <ToneSelector
          onSelect={tone => {
            store.setTone(tone);
            setShowToneSelector(false);
          }}
        />
      );
    }
    return <LandingPage onGetStarted={() => setShowToneSelector(true)} />;
  }

  return <MainWizard />;
}
