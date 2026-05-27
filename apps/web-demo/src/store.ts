import { useState, useCallback } from 'react';
import { SECTIONS, SECTION_IDS } from './engine/sections';
import type { ToneOption, ChildInfo } from './engine/sections';

const STORAGE_KEY = 'pair_static_wizard_v1';

export interface SectionState {
  answers: Record<string, unknown>; // questionId -> value (null = skipped optional)
  summary: string;
  complete: boolean;
}

export interface WizardState {
  tone: ToneOption | null;
  children: ChildInfo[]; // populated when children_list is answered
  currentChildIndex: number; // which child we're answering per-child questions for
  currentChildQuestionIndex: number; // which per-child question we're on
  sections: Record<string, SectionState>;
  currentSectionId: string;
}

function emptySectionState(): SectionState {
  return { answers: {}, summary: '', complete: false };
}

function defaultState(): WizardState {
  const sections: Record<string, SectionState> = {};
  for (const s of SECTIONS) sections[s.id] = emptySectionState();
  return {
    tone: null,
    children: [],
    currentChildIndex: 0,
    currentChildQuestionIndex: 0,
    sections,
    currentSectionId: SECTION_IDS[0],
  };
}

function loadState(): WizardState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    const parsed = JSON.parse(raw) as WizardState;
    // Ensure all sections present (handles schema upgrades)
    for (const s of SECTIONS) {
      if (!parsed.sections[s.id]) parsed.sections[s.id] = emptySectionState();
    }
    // Ensure new fields are present
    if (parsed.tone === undefined) parsed.tone = null;
    if (!parsed.children) parsed.children = [];
    if (parsed.currentChildIndex === undefined) parsed.currentChildIndex = 0;
    if (parsed.currentChildQuestionIndex === undefined) parsed.currentChildQuestionIndex = 0;
    return parsed;
  } catch {
    return defaultState();
  }
}

function saveState(state: WizardState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {}
}

export interface WizardStore {
  state: WizardState;
  setTone: (tone: ToneOption) => void;
  setAnswer: (sectionId: string, questionId: string, value: unknown) => void;
  setChildren: (children: ChildInfo[]) => void;
  advanceChildQuestion: (totalPerChildQuestions: number) => void;
  setSummary: (sectionId: string, summary: string) => void;
  markSectionComplete: (sectionId: string) => void;
  resetSection: (sectionId: string) => void;
  goToSection: (id: string) => void;
  resetAll: () => void;
}

export function useWizardStore(): WizardStore {
  const [state, setState] = useState<WizardState>(loadState);

  const update = useCallback((updater: (prev: WizardState) => WizardState) => {
    setState(prev => {
      const next = updater(prev);
      saveState(next);
      return next;
    });
  }, []);

  const setTone = useCallback((tone: ToneOption) => {
    update(prev => ({ ...prev, tone }));
  }, [update]);

  const setAnswer = useCallback((sectionId: string, questionId: string, value: unknown) => {
    update(prev => ({
      ...prev,
      sections: {
        ...prev.sections,
        [sectionId]: {
          ...prev.sections[sectionId],
          answers: {
            ...prev.sections[sectionId].answers,
            [questionId]: value,
          },
        },
      },
    }));
  }, [update]);

  const setChildren = useCallback((children: ChildInfo[]) => {
    update(prev => ({ ...prev, children }));
  }, [update]);

  const advanceChildQuestion = useCallback((totalPerChildQuestions: number) => {
    update(prev => {
      if (prev.currentChildQuestionIndex + 1 < totalPerChildQuestions) {
        return { ...prev, currentChildQuestionIndex: prev.currentChildQuestionIndex + 1 };
      } else {
        return {
          ...prev,
          currentChildIndex: prev.currentChildIndex + 1,
          currentChildQuestionIndex: 0,
        };
      }
    });
  }, [update]);

  const setSummary = useCallback((sectionId: string, summary: string) => {
    update(prev => ({
      ...prev,
      sections: {
        ...prev.sections,
        [sectionId]: { ...prev.sections[sectionId], summary },
      },
    }));
  }, [update]);

  const markSectionComplete = useCallback((sectionId: string) => {
    update(prev => ({
      ...prev,
      sections: {
        ...prev.sections,
        [sectionId]: { ...prev.sections[sectionId], complete: true },
      },
    }));
  }, [update]);

  const goToSection = useCallback((id: string) => {
    update(prev => ({ ...prev, currentSectionId: id }));
  }, [update]);

  const resetSection = useCallback((sectionId: string) => {
    update(prev => {
      const next = {
        ...prev,
        sections: {
          ...prev.sections,
          [sectionId]: emptySectionState(),
        },
      };
      // If resetting the children section, also clear the children list and indices
      if (sectionId === 'children') {
        next.children = [];
        next.currentChildIndex = 0;
        next.currentChildQuestionIndex = 0;
      }
      return next;
    });
  }, [update]);

  const resetAll = useCallback(() => {
    const fresh = defaultState();
    saveState(fresh);
    setState(fresh);
  }, []);

  return {
    state,
    setTone,
    setAnswer,
    setChildren,
    advanceChildQuestion,
    setSummary,
    markSectionComplete,
    resetSection,
    goToSection,
    resetAll,
  };
}

export function getFamilyName(state: WizardState): string {
  const names = state.sections['family']?.answers['parent_names'] as string | undefined;
  return names || 'Our Family';
}
