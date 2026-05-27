export type SectionId =
  | 'family_goals'
  | 'responsibilities'
  | 'housemate_expectations'
  | 'household_info'
  | 'screen_time_media'
  | 'discipline_philosophy';

export type ModuleId =
  | 'scheduling'
  | 'performance_review'
  | 'summer_planner'
  | 'compliance'
  | 'handover';

export type AnswerType =
  | 'single_choice'
  | 'multi_choice'
  | 'scale'
  | 'free_text'
  | 'number'
  | 'date'
  | 'boolean'
  | 'structured_list'
  | 'time'
  | 'multi_text';

export type AnswerValue =
  | string
  | number
  | boolean
  | string[]
  | Record<string, unknown>
  | null;

export interface QuestionOption {
  value: string;
  label: string;
  description?: string;
}

export interface ScaleConfig {
  min: number;
  max: number;
  minLabel: string;
  maxLabel: string;
}

export interface Condition {
  sourceQuestionId: string;
  operator: 'eq' | 'neq' | 'gt' | 'lt' | 'gte' | 'lte' | 'includes' | 'excludes' | 'any';
  value: string | number | boolean | string[];
}

export interface ConditionGroup {
  logic: 'AND' | 'OR';
  conditions: Array<Condition | ConditionGroup>;
}

export interface Question {
  id: string;
  sectionId: SectionId;
  text: string;
  subtext?: string;
  answerType: AnswerType;
  options?: QuestionOption[];
  scaleConfig?: ScaleConfig;
  required: boolean;
  showIf?: ConditionGroup;
  repeatFor?: string;
  tags?: string[];
  documentLabel?: string;
  feedsIntoModules?: ModuleId[];
  placeholder?: string;
}

export interface ResolvedQuestion extends Question {
  stepIndex: number;
  repeatIndex: number;
  repeatLabel?: string;
}

export interface Section {
  id: SectionId;
  title: string;
  description: string;
  icon: string;
  estimatedMinutes: number;
  questions: Question[];
}

export interface WizardContext {
  childCount: number;
  hasChildUnder2: boolean;
  hasChildUnder5: boolean;
  hasSchoolAgeChild: boolean;
  hasTeenager: boolean;
  specialNeedsFlag: boolean;
  householdStyle: 'relaxed' | 'moderate' | 'structured';
  culturalEmphasis: 'low' | 'medium' | 'high';
  communicationStyle: 'direct' | 'collaborative' | 'written_first';
  hasCar: boolean;
  hasSchoolPickup: boolean;
  answers: Record<string, AnswerValue>;
}

export interface RepeatItem {
  id: string;
  name: string;
  ageMonths: number;
  specialNeeds: boolean;
  properties: Record<string, AnswerValue>;
}

export type SectionCompletionStatus = 'not_started' | 'in_progress' | 'complete';

export interface WizardProgress {
  householdId: string;
  currentSectionId: SectionId;
  currentStepIndex: number;
  sectionStatus: Record<SectionId, SectionCompletionStatus>;
  lastSavedAt: string;
}
