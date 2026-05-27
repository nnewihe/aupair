import type { Condition, ConditionGroup, WizardContext, AnswerValue } from '@pair/types';

function resolveValue(sourceQuestionId: string, context: WizardContext): AnswerValue {
  // Special repeat-context keys are resolved by the engine before calling here
  return context.answers[sourceQuestionId] ?? null;
}

function evaluateCondition(condition: Condition, context: WizardContext): boolean {
  const actual = resolveValue(condition.sourceQuestionId, context);
  const expected = condition.value;

  switch (condition.operator) {
    case 'eq':
      return actual === expected;
    case 'neq':
      return actual !== expected;
    case 'gt':
      return typeof actual === 'number' && typeof expected === 'number' && actual > expected;
    case 'lt':
      return typeof actual === 'number' && typeof expected === 'number' && actual < expected;
    case 'gte':
      return typeof actual === 'number' && typeof expected === 'number' && actual >= expected;
    case 'lte':
      return typeof actual === 'number' && typeof expected === 'number' && actual <= expected;
    case 'includes':
      if (Array.isArray(actual)) {
        return Array.isArray(expected)
          ? expected.some((v) => (actual as string[]).includes(v as string))
          : (actual as string[]).includes(expected as string);
      }
      return false;
    case 'excludes':
      if (Array.isArray(actual)) {
        return Array.isArray(expected)
          ? !expected.some((v) => (actual as string[]).includes(v as string))
          : !(actual as string[]).includes(expected as string);
      }
      return true;
    case 'any':
      return actual !== null && actual !== undefined;
    default:
      return false;
  }
}

export function evaluateConditionGroup(
  group: ConditionGroup,
  context: WizardContext,
): boolean {
  if (group.logic === 'AND') {
    return group.conditions.every((c) =>
      'logic' in c ? evaluateConditionGroup(c, context) : evaluateCondition(c, context),
    );
  }
  return group.conditions.some((c) =>
    'logic' in c ? evaluateConditionGroup(c, context) : evaluateCondition(c, context),
  );
}
