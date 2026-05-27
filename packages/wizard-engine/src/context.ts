import type { WizardContext, RepeatItem, AnswerValue } from '@pair/types';

interface RawAnswers {
  [questionId: string]: AnswerValue;
}

interface ChildListEntry {
  id: string;
  name: string;
  dateOfBirth: string;
  specialNeeds: boolean;
}

function ageMonthsFromDOB(dob: string): number {
  const birth = new Date(dob);
  const now = new Date();
  return (
    (now.getFullYear() - birth.getFullYear()) * 12 +
    (now.getMonth() - birth.getMonth())
  );
}

export function deriveContext(answers: RawAnswers): WizardContext {
  const children = (answers['children_list'] as ChildListEntry[] | undefined) ?? [];
  const childCount = children.length;

  const ageBuckets = children.map((c) => ageMonthsFromDOB(c.dateOfBirth));

  const hasChildUnder2 = ageBuckets.some((a) => a < 24);
  const hasChildUnder5 = ageBuckets.some((a) => a < 60);
  const hasSchoolAgeChild = ageBuckets.some((a) => a >= 60 && a < 156);
  const hasTeenager = ageBuckets.some((a) => a >= 156);
  const specialNeedsFlag = children.some((c) => c.specialNeeds);

  // Derive household style from scale answer (1–5)
  const styleScale = answers['household_style'] as number | undefined;
  const householdStyle: WizardContext['householdStyle'] =
    styleScale == null ? 'moderate'
    : styleScale <= 2 ? 'relaxed'
    : styleScale >= 4 ? 'structured'
    : 'moderate';

  // Derive cultural emphasis from scale answer (1–5)
  const culturalScale = answers['cultural_exchange_emphasis'] as number | undefined;
  const culturalEmphasis: WizardContext['culturalEmphasis'] =
    culturalScale == null ? 'medium'
    : culturalScale <= 2 ? 'low'
    : culturalScale >= 4 ? 'high'
    : 'medium';

  const rawComm = answers['communication_style'] as string | undefined;
  const communicationStyle: WizardContext['communicationStyle'] =
    rawComm === 'direct' ? 'direct'
    : rawComm === 'written_first' ? 'written_first'
    : 'collaborative';

  const hasCar = (answers['has_car_access'] as boolean | undefined) ?? false;
  const hasSchoolPickup = children.some(
    (_, i) => answers[`child_school_pickup_${i}`] === true,
  );

  return {
    childCount,
    hasChildUnder2,
    hasChildUnder5,
    hasSchoolAgeChild,
    hasTeenager,
    specialNeedsFlag,
    householdStyle,
    culturalEmphasis,
    communicationStyle,
    hasCar,
    hasSchoolPickup,
    answers,
  };
}

export function buildRepeatItems(answers: RawAnswers): RepeatItem[] {
  const children = (answers['children_list'] as ChildListEntry[] | undefined) ?? [];
  return children.map((c, i) => ({
    id: c.id,
    name: c.name,
    ageMonths: ageMonthsFromDOB(c.dateOfBirth),
    specialNeeds: c.specialNeeds,
    properties: {
      age_months: ageMonthsFromDOB(c.dateOfBirth),
      age_years: Math.floor(ageMonthsFromDOB(c.dateOfBirth) / 12),
      special_needs: c.specialNeeds,
      index: i,
    },
  }));
}
