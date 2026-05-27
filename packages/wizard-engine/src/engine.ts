import type { Question, ResolvedQuestion, SectionId, WizardContext, RepeatItem } from '@pair/types';
import { evaluateConditionGroup } from './evaluator';

const REPEAT_CONTEXT_PREFIX = '_repeat_context.';

function resolveRepeatContext(
  sourceQuestionId: string,
  item: RepeatItem,
  context: WizardContext,
): number | boolean | string | null {
  if (!sourceQuestionId.startsWith(REPEAT_CONTEXT_PREFIX)) {
    return null;
  }
  const key = sourceQuestionId.slice(REPEAT_CONTEXT_PREFIX.length);
  const val = item.properties[key];
  return val !== undefined ? (val as number | boolean | string) : null;
}

function interpolateText(text: string, item: RepeatItem | null): string {
  if (!item) return text;
  return text.replace(/\{childName\}/g, item.name);
}

function isApplicable(
  question: Question,
  context: WizardContext,
  repeatItem: RepeatItem | null,
): boolean {
  if (!question.showIf) return true;

  // Build an augmented context that overlays repeat-context keys
  const augmented: WizardContext = repeatItem
    ? {
        ...context,
        answers: {
          ...context.answers,
          // Inject _repeat_context.* keys into answers so evaluator can find them
          ...Object.fromEntries(
            Object.entries(repeatItem.properties).map(([k, v]) => [
              `${REPEAT_CONTEXT_PREFIX}${k}`,
              v,
            ]),
          ),
        },
      }
    : context;

  return evaluateConditionGroup(question.showIf, augmented);
}

/**
 * Compute the ordered list of applicable questions for a given section.
 * Questions tagged with `repeatFor` are expanded once per repeat item.
 * Non-applicable questions (failed showIf) are excluded.
 *
 * @returns Ordered, resolved questions with stepIndex and repeatIndex assigned.
 */
export function computeApplicableQuestions(
  sectionId: SectionId,
  allQuestions: Question[],
  context: WizardContext,
  repeatItems: RepeatItem[],
): ResolvedQuestion[] {
  const sectionQuestions = allQuestions.filter((q) => q.sectionId === sectionId);
  const resolved: ResolvedQuestion[] = [];
  let stepIndex = 0;

  for (const question of sectionQuestions) {
    if (question.repeatFor) {
      // Per-repeat-item questions
      for (let i = 0; i < repeatItems.length; i++) {
        const item = repeatItems[i]!;
        if (!isApplicable(question, context, item)) continue;

        resolved.push({
          ...question,
          id: `${question.id}_${i}`,
          text: interpolateText(question.text, item),
          subtext: question.subtext ? interpolateText(question.subtext, item) : undefined,
          stepIndex: stepIndex++,
          repeatIndex: i,
          repeatLabel: item.name,
        });
      }
    } else {
      // Non-repeating question
      if (!isApplicable(question, context, null)) continue;

      resolved.push({
        ...question,
        stepIndex: stepIndex++,
        repeatIndex: 0,
      });
    }
  }

  return resolved;
}

/**
 * Compute completion status for a section: how many required questions are answered.
 */
export function computeSectionCompletion(
  sectionId: SectionId,
  allQuestions: Question[],
  context: WizardContext,
  repeatItems: RepeatItem[],
): { answered: number; required: number; complete: boolean } {
  const applicable = computeApplicableQuestions(sectionId, allQuestions, context, repeatItems);
  const required = applicable.filter((q) => q.required);
  const answered = required.filter((q) => {
    const val = context.answers[q.id];
    if (val === null || val === undefined) return false;
    if (typeof val === 'string') return val.trim().length > 0;
    if (Array.isArray(val)) return val.length > 0;
    return true;
  });

  return {
    answered: answered.length,
    required: required.length,
    complete: answered.length === required.length,
  };
}
