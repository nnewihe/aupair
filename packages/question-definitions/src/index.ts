export { familyGoalsQuestions, familyGoalsSection } from './sections/family-goals';
export { responsibilitiesQuestions, responsibilitiesSection } from './sections/responsibilities';
export { housemateExpectationsQuestions, housemateExpectationsSection } from './sections/housemate-expectations';
export { householdInfoQuestions, householdInfoSection } from './sections/household-info';
export { screenTimeMediaQuestions, screenTimeMediaSection } from './sections/screen-time-media';
export { disciplinePhilosophyQuestions, disciplinePhilosophySection } from './sections/discipline-philosophy';

import { familyGoalsSection } from './sections/family-goals';
import { responsibilitiesSection } from './sections/responsibilities';
import { housemateExpectationsSection } from './sections/housemate-expectations';
import { householdInfoSection } from './sections/household-info';
import { screenTimeMediaSection } from './sections/screen-time-media';
import { disciplinePhilosophySection } from './sections/discipline-philosophy';
import type { Question, Section } from '@pair/types';

export const ALL_SECTIONS: Section[] = [
  familyGoalsSection,
  responsibilitiesSection,
  housemateExpectationsSection,
  householdInfoSection,
  screenTimeMediaSection,
  disciplinePhilosophySection,
];

export const ALL_QUESTIONS: Question[] = ALL_SECTIONS.flatMap((s) => s.questions);

export const SECTION_ORDER = ALL_SECTIONS.map((s) => s.id);
