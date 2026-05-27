import { describe, it, expect } from 'vitest';
import { computeApplicableQuestions, computeSectionCompletion } from '../engine';
import { deriveContext, buildRepeatItems } from '../context';
import { ALL_QUESTIONS } from '@pair/question-definitions';
import type { WizardContext, RepeatItem } from '@pair/types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function dobFromMonthsAgo(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}

function makeChild(name: string, ageMonths: number, specialNeeds = false) {
  return {
    id: `child-${name.toLowerCase()}`,
    name,
    dateOfBirth: dobFromMonthsAgo(ageMonths),
    specialNeeds,
  };
}

function makeContext(overrides: Partial<WizardContext> = {}): WizardContext {
  return {
    childCount: 0,
    hasChildUnder2: false,
    hasChildUnder5: false,
    hasSchoolAgeChild: false,
    hasTeenager: false,
    specialNeedsFlag: false,
    householdStyle: 'moderate',
    culturalEmphasis: 'medium',
    communicationStyle: 'collaborative',
    hasCar: false,
    hasSchoolPickup: false,
    answers: {},
    ...overrides,
  };
}

// ── deriveContext ─────────────────────────────────────────────────────────────

describe('deriveContext', () => {
  it('derives correct age buckets for a 14-month-old', () => {
    const ctx = deriveContext({ children_list: [makeChild('Emma', 14)] });
    expect(ctx.childCount).toBe(1);
    expect(ctx.hasChildUnder2).toBe(true);
    expect(ctx.hasChildUnder5).toBe(true);
    expect(ctx.hasSchoolAgeChild).toBe(false);
    expect(ctx.hasTeenager).toBe(false);
  });

  it('correctly identifies a 10-year-old as school-age only', () => {
    const ctx = deriveContext({ children_list: [makeChild('Lucas', 120)] });
    expect(ctx.hasChildUnder5).toBe(false);
    expect(ctx.hasSchoolAgeChild).toBe(true);
    expect(ctx.hasTeenager).toBe(false);
  });

  it('detects teenager at 156 months (13 years)', () => {
    const ctx = deriveContext({ children_list: [makeChild('Zoe', 156)] });
    expect(ctx.hasTeenager).toBe(true);
    expect(ctx.hasSchoolAgeChild).toBe(false);
  });

  it('flags specialNeedsFlag if any child has special needs', () => {
    const ctx = deriveContext({
      children_list: [makeChild('Emma', 48, false), makeChild('Lucas', 96, true)],
    });
    expect(ctx.specialNeedsFlag).toBe(true);
  });

  it('derives householdStyle from scale answer', () => {
    expect(deriveContext({ household_style: 1 }).householdStyle).toBe('relaxed');
    expect(deriveContext({ household_style: 3 }).householdStyle).toBe('moderate');
    expect(deriveContext({ household_style: 5 }).householdStyle).toBe('structured');
  });

  it('defaults to moderate/medium/collaborative when answers are absent', () => {
    const ctx = deriveContext({});
    expect(ctx.householdStyle).toBe('moderate');
    expect(ctx.culturalEmphasis).toBe('medium');
    expect(ctx.communicationStyle).toBe('collaborative');
  });
});

// ── computeApplicableQuestions ────────────────────────────────────────────────

describe('computeApplicableQuestions — responsibilities section', () => {
  it('excludes toddler nap question for a 10-year-old', () => {
    const ctx = makeContext({ answers: { children_list: [makeChild('Lucas', 120)] } });
    const items = buildRepeatItems(ctx.answers);
    const fullCtx = deriveContext(ctx.answers);

    const questions = computeApplicableQuestions('responsibilities', ALL_QUESTIONS, fullCtx, items);
    const ids = questions.map((q) => q.id);
    expect(ids).not.toContain('child_nap_schedule_0');
  });

  it('includes toddler nap question for a 14-month-old', () => {
    const ctx = makeContext({ answers: { children_list: [makeChild('Emma', 14)] } });
    const items = buildRepeatItems(ctx.answers);
    const fullCtx = deriveContext(ctx.answers);

    const questions = computeApplicableQuestions('responsibilities', ALL_QUESTIONS, fullCtx, items);
    const ids = questions.map((q) => q.id);
    expect(ids).toContain('child_nap_schedule_0');
  });

  it('generates per-child questions for all children', () => {
    const answers = {
      children_list: [makeChild('Emma', 14), makeChild('Lucas', 96)],
    };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('responsibilities', ALL_QUESTIONS, fullCtx, items);
    const bedtimeIds = questions.filter((q) => q.id.startsWith('child_bedtime_routine'));
    expect(bedtimeIds).toHaveLength(2);
  });

  it('includes homework support question for school-age child only', () => {
    const answers = {
      children_list: [makeChild('Emma', 14), makeChild('Lucas', 96)],
    };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('responsibilities', ALL_QUESTIONS, fullCtx, items);
    const hwIds = questions.filter((q) => q.id.startsWith('child_homework_support'));
    // Only Lucas (96 months = 8 years) triggers homework support
    expect(hwIds).toHaveLength(1);
    expect(hwIds[0]?.repeatLabel).toBe('Lucas');
  });
});

describe('computeApplicableQuestions — screen time section', () => {
  it('excludes social media question for a 5-year-old', () => {
    const answers = { children_list: [makeChild('Emma', 60)] };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('screen_time_media', ALL_QUESTIONS, fullCtx, items);
    const ids = questions.map((q) => q.id);
    expect(ids).not.toContain('child_social_media_0');
  });

  it('includes social media question for a 12-year-old (144 months)', () => {
    const answers = { children_list: [makeChild('Zoe', 144)] };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('screen_time_media', ALL_QUESTIONS, fullCtx, items);
    const ids = questions.map((q) => q.id);
    expect(ids).toContain('child_social_media_0');
  });
});

describe('computeApplicableQuestions — discipline section', () => {
  it('includes special needs discipline question only for children with special needs', () => {
    const answers = {
      children_list: [makeChild('Emma', 60, false), makeChild('Lucas', 96, true)],
    };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('discipline_philosophy', ALL_QUESTIONS, fullCtx, items);
    const specialIds = questions.filter((q) => q.id.startsWith('child_special_needs_discipline'));
    // Only Lucas has special needs
    expect(specialIds).toHaveLength(1);
    expect(specialIds[0]?.repeatLabel).toBe('Lucas');
  });

  it('excludes timeout_notes when timeout_approach is false', () => {
    const answers = {
      children_list: [],
      timeout_approach: false,
    };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('discipline_philosophy', ALL_QUESTIONS, fullCtx, items);
    const ids = questions.map((q) => q.id);
    expect(ids).not.toContain('timeout_notes');
  });

  it('includes timeout_notes when timeout_approach is true', () => {
    const answers = {
      children_list: [],
      timeout_approach: true,
    };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('discipline_philosophy', ALL_QUESTIONS, fullCtx, items);
    const ids = questions.map((q) => q.id);
    expect(ids).toContain('timeout_notes');
  });
});

describe('computeApplicableQuestions — family goals section', () => {
  it('hides cultural exchange goals when emphasis is low', () => {
    const answers = { cultural_exchange_emphasis: 1 };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('family_goals', ALL_QUESTIONS, fullCtx, items);
    const ids = questions.map((q) => q.id);
    expect(ids).not.toContain('cultural_exchange_goals');
  });

  it('shows cultural exchange goals when emphasis is high', () => {
    const answers = { cultural_exchange_emphasis: 5 };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('family_goals', ALL_QUESTIONS, fullCtx, items);
    const ids = questions.map((q) => q.id);
    expect(ids).toContain('cultural_exchange_goals');
  });
});

// ── computeSectionCompletion ──────────────────────────────────────────────────

describe('computeSectionCompletion', () => {
  it('reports 0/N when no answers given', () => {
    const fullCtx = deriveContext({});
    const items = buildRepeatItems({});

    const result = computeSectionCompletion('family_goals', ALL_QUESTIONS, fullCtx, items);
    expect(result.answered).toBe(0);
    expect(result.required).toBeGreaterThan(0);
    expect(result.complete).toBe(false);
  });

  it('correctly counts answered required questions', () => {
    const answers = {
      family_name: 'The Johnson Family',
      family_intro: 'We are a fun family in Boston.',
      primary_language: 'english',
      childcare_style: 'balanced',
      household_style: 3,
      cultural_exchange_emphasis: 2,
      au_pair_cultural_participation: 'welcome_but_own_space',
      communication_style: 'collaborative',
      check_in_frequency: 'monthly',
      top_priorities: ['safe_reliable_care', 'cultural_exchange'],
    };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const result = computeSectionCompletion('family_goals', ALL_QUESTIONS, fullCtx, items);
    expect(result.answered).toBeGreaterThan(0);
  });
});

// ── stepIndex assignment ───────────────────────────────────────────────────────

describe('stepIndex', () => {
  it('assigns sequential stepIndex values starting at 0', () => {
    const fullCtx = deriveContext({});
    const items = buildRepeatItems({});
    const questions = computeApplicableQuestions('family_goals', ALL_QUESTIONS, fullCtx, items);

    questions.forEach((q, i) => {
      expect(q.stepIndex).toBe(i);
    });
  });

  it('interpolates child name into question text', () => {
    const answers = { children_list: [makeChild('Emma', 14)] };
    const fullCtx = deriveContext(answers);
    const items = buildRepeatItems(answers);

    const questions = computeApplicableQuestions('responsibilities', ALL_QUESTIONS, fullCtx, items);
    const napQ = questions.find((q) => q.id === 'child_nap_schedule_0');
    expect(napQ?.text).toContain('Emma');
  });
});
