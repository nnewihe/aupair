import { serve } from 'https://deno.land/std@0.177.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { computeApplicableQuestions, deriveContext, buildRepeatItems } from '../../packages/wizard-engine/src/index.ts';
import { ALL_QUESTIONS } from '../../packages/question-definitions/src/index.ts';
import type { SectionId } from '../../packages/types/src/index.ts';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const url = new URL(req.url);
    const sectionId = url.searchParams.get('sectionId') as SectionId | null;
    const householdId = url.searchParams.get('householdId');

    if (!sectionId || !householdId) {
      return new Response(JSON.stringify({ error: 'sectionId and householdId required' }), {
        status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );

    // Fetch all answers for this household
    const { data: rows, error } = await supabase
      .from('wizard_answers')
      .select('question_id, repeat_index, answer_json')
      .eq('household_id', householdId);

    if (error) throw error;

    // Reconstruct flat answers map
    const answers: Record<string, unknown> = {};
    for (const row of rows ?? []) {
      const key = row.repeat_index === 0 ? row.question_id : `${row.question_id}_${row.repeat_index}`;
      answers[key] = row.answer_json;
    }
    // children_list is stored as a single JSON blob at repeat_index 0
    const childrenRow = rows?.find((r) => r.question_id === 'children_list');
    if (childrenRow) {
      answers['children_list'] = childrenRow.answer_json;
    }

    const context = deriveContext(answers);
    const repeatItems = buildRepeatItems(answers);
    const questions = computeApplicableQuestions(sectionId, ALL_QUESTIONS, context, repeatItems);

    return new Response(JSON.stringify({ questions, context }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
