import { create } from 'zustand';
import type { SectionId, WizardContext, RepeatItem, AnswerValue, SectionCompletionStatus } from '@pair/types';
import { deriveContext, buildRepeatItems } from '@pair/wizard-engine';

interface WizardState {
  householdId: string | null;
  currentSectionId: SectionId;
  currentStepIndex: number;
  answers: Record<string, AnswerValue>;
  sectionStatus: Record<SectionId, SectionCompletionStatus>;
  isSaving: boolean;

  // Derived (recomputed on every answer change)
  context: WizardContext;
  repeatItems: RepeatItem[];

  // Actions
  setHouseholdId: (id: string) => void;
  setAnswer: (questionId: string, value: AnswerValue) => void;
  loadAnswers: (answers: Record<string, AnswerValue>) => void;
  goToSection: (sectionId: SectionId) => void;
  goToStep: (index: number) => void;
  setSaving: (saving: boolean) => void;
  setSectionStatus: (sectionId: SectionId, status: SectionCompletionStatus) => void;
}

const INITIAL_SECTION: SectionId = 'family_goals';

const emptyContext: WizardContext = {
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
};

export const useWizardStore = create<WizardState>((set, get) => ({
  householdId: null,
  currentSectionId: INITIAL_SECTION,
  currentStepIndex: 0,
  answers: {},
  sectionStatus: {
    family_goals: 'not_started',
    responsibilities: 'not_started',
    housemate_expectations: 'not_started',
    household_info: 'not_started',
    screen_time_media: 'not_started',
    discipline_philosophy: 'not_started',
  },
  isSaving: false,
  context: emptyContext,
  repeatItems: [],

  setHouseholdId: (id) => set({ householdId: id }),

  setAnswer: (questionId, value) => {
    const answers = { ...get().answers, [questionId]: value };
    const context = deriveContext(answers);
    const repeatItems = buildRepeatItems(answers);
    set({ answers, context, repeatItems });
  },

  loadAnswers: (answers) => {
    const context = deriveContext(answers);
    const repeatItems = buildRepeatItems(answers);
    set({ answers, context, repeatItems });
  },

  goToSection: (sectionId) => set({ currentSectionId: sectionId, currentStepIndex: 0 }),
  goToStep: (index) => set({ currentStepIndex: index }),
  setSaving: (saving) => set({ isSaving: saving }),
  setSectionStatus: (sectionId, status) =>
    set((state) => ({
      sectionStatus: { ...state.sectionStatus, [sectionId]: status },
    })),
}));
