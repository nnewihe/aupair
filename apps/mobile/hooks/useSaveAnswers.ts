import { useCallback, useRef } from 'react';
import { useWizardStore } from '../store/wizard.store';
import { supabase } from '../lib/supabase';

const DEBOUNCE_MS = 600;

export function useSaveAnswers() {
  const { householdId, setSaving } = useWizardStore();
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const saveAnswer = useCallback(
    (questionId: string, value: unknown, repeatIndex = 0) => {
      if (!householdId) return;

      // Debounce: cancel any pending save for this question
      const key = `${questionId}_${repeatIndex}`;
      if (timers.current[key]) {
        clearTimeout(timers.current[key]);
      }

      setSaving(true);

      timers.current[key] = setTimeout(async () => {
        await supabase.from('wizard_answers').upsert(
          {
            household_id: householdId,
            question_id: questionId,
            repeat_index: repeatIndex,
            answer_json: value,
          },
          { onConflict: 'household_id,question_id,repeat_index' },
        );
        setSaving(false);
      }, DEBOUNCE_MS);
    },
    [householdId, setSaving],
  );

  return { saveAnswer };
}
