import { serve } from 'https://deno.land/std@0.177.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// ── HTML Template ────────────────────────────────────────────────────────────

function renderGuideHtml(data: Record<string, unknown>): string {
  const family = data.familyGoals as Record<string, unknown>;
  const children = (data.children as Record<string, unknown>[]) ?? [];
  const responsibilities = data.responsibilities as Record<string, unknown>;
  const housemate = data.housemateExpectations as Record<string, unknown>;
  const household = data.householdInfo as Record<string, unknown>;
  const screenTime = data.screenTime as Record<string, unknown>;
  const discipline = data.discipline as Record<string, unknown>;

  const childCards = children
    .map(
      (child) => `
      <div class="child-card">
        <h3>${child.name} <span class="age">${child.ageDisplay}</span></h3>
        ${child.dietaryRestrictions ? `<p><strong>Diet:</strong> ${(child.dietaryRestrictions as string[]).join(', ')}</p>` : ''}
        ${child.allergies ? `<p><strong>Allergies:</strong> ${(child.allergies as string[]).join(', ')}</p>` : ''}
        ${child.medicalNotes ? `<p><strong>Medical:</strong> ${child.medicalNotes}</p>` : ''}
        ${child.schoolName ? `<p><strong>School:</strong> ${child.schoolName} · Pick-up: ${child.schoolPickupTime}</p>` : ''}
        ${child.napSchedule ? `<p><strong>Nap schedule:</strong> ${child.napSchedule}</p>` : ''}
        ${child.emotionalRegulationApproach ? `<p><strong>Emotional regulation:</strong> ${child.emotionalRegulationApproach}</p>` : ''}
      </div>`,
    )
    .join('');

  const screenTimePerChild = (screenTime?.perChild as Record<string, unknown>[] ?? [])
    .map(
      (c) => `
      <div class="child-section">
        <h4>${c.childName}</h4>
        <p><strong>Daily limit:</strong> ${c.dailyLimitMinutes} minutes</p>
        <p><strong>Approved:</strong> ${c.approvedApps}</p>
        <p><strong>Restricted:</strong> ${c.restrictedContent}</p>
        ${c.deviceRules ? `<p><strong>Devices:</strong> ${c.deviceRules}</p>` : ''}
      </div>`,
    )
    .join('');

  const disciplinePerChild = (discipline?.perChild as Record<string, unknown>[] ?? [])
    .filter((c) => c.specialApproach)
    .map(
      (c) => `
      <div class="child-section">
        <h4>${c.childName}</h4>
        <p>${c.specialApproach}</p>
      </div>`,
    )
    .join('');

  const hardRules = ((discipline?.hardRules as string[]) ?? [])
    .map((r) => `<li>${r}</li>`)
    .join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Household Guide — ${family?.familyName ?? 'Our Family'}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #f8fafc;
      color: #1a2744;
      line-height: 1.6;
    }
    .hero {
      background: #1a2744;
      color: #ffffff;
      padding: 48px 32px;
      text-align: center;
    }
    .hero h1 { font-size: 36px; font-weight: 800; letter-spacing: -1px; }
    .hero .subtitle { color: #94a3b8; margin-top: 8px; font-size: 16px; }
    .hero .generated { color: #64748b; margin-top: 16px; font-size: 13px; }
    .container { max-width: 720px; margin: 0 auto; padding: 32px 20px; }
    section { margin-bottom: 48px; }
    h2 {
      font-size: 22px;
      font-weight: 700;
      color: #1a2744;
      border-bottom: 2px solid #14b8a6;
      padding-bottom: 8px;
      margin-bottom: 20px;
    }
    h3 { font-size: 17px; font-weight: 700; margin-bottom: 8px; color: #1a2744; }
    h4 { font-size: 15px; font-weight: 600; color: #0f766e; margin-bottom: 6px; }
    p { margin-bottom: 10px; font-size: 15px; }
    .age { font-size: 14px; color: #64748b; font-weight: 400; margin-left: 6px; }
    .child-card {
      background: #ffffff;
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 16px;
      border: 1px solid #e2e8f0;
    }
    .child-section { margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #f1f5f9; }
    .child-section:last-child { border-bottom: none; }
    ul { padding-left: 20px; margin-bottom: 10px; }
    li { margin-bottom: 4px; font-size: 15px; }
    .intro-block {
      background: #ffffff;
      border-radius: 12px;
      padding: 20px;
      border: 1px solid #e2e8f0;
      font-size: 15px;
      line-height: 1.7;
    }
    .meta-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
    .tag {
      background: #f0fdf9;
      color: #0f766e;
      border-radius: 20px;
      padding: 4px 14px;
      font-size: 13px;
      font-weight: 500;
    }
    footer {
      text-align: center;
      padding: 32px;
      color: #94a3b8;
      font-size: 13px;
      border-top: 1px solid #e2e8f0;
    }
    @media print {
      body { background: white; }
      .hero { padding: 32px; }
      section { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <div class="hero">
    <h1>${family?.familyName ?? 'Our Family'} — Household Guide</h1>
    <p class="subtitle">Prepared for your au pair</p>
    <p class="generated">Generated ${new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })} · Pair</p>
  </div>

  <div class="container">

    <section>
      <h2>About Our Family</h2>
      ${family?.familyIntro ? `<div class="intro-block">${family.familyIntro}</div>` : ''}
      <div class="meta-tags" style="margin-top: 12px;">
        ${family?.householdStyle ? `<span class="tag">${family.householdStyle} household</span>` : ''}
        ${family?.communicationPreferences ? `<span class="tag">Communication: ${family.communicationPreferences}</span>` : ''}
        ${family?.primaryLanguage ? `<span class="tag">Primary language: ${family.primaryLanguage}</span>` : ''}
      </div>
      ${family?.culturalExchangeGoals ? `<p><strong>Cultural exchange goals:</strong> ${family.culturalExchangeGoals}</p>` : ''}
    </section>

    ${children.length > 0 ? `
    <section>
      <h2>Our Children</h2>
      ${childCards}
    </section>` : ''}

    <section>
      <h2>Responsibilities</h2>
      ${responsibilities?.childcareDuties ? `<p><strong>Childcare duties:</strong> ${(responsibilities.childcareDuties as string[]).join(', ')}</p>` : ''}
      ${responsibilities?.schoolPickupInstructions ? `<div><h3>School pick-up</h3><p>${responsibilities.schoolPickupInstructions}</p></div>` : ''}
      ${responsibilities?.laundryInstructions ? `<div><h3>Laundry</h3><p>${responsibilities.laundryInstructions}</p></div>` : ''}
      ${responsibilities?.foodPrepResponsibilities ? `<div><h3>Food preparation</h3><p>${responsibilities.foodPrepResponsibilities}</p></div>` : ''}
      ${responsibilities?.seasonalTasks?.length ? `<div><h3>Seasonal tasks</h3><ul>${(responsibilities.seasonalTasks as string[]).map((t) => `<li>${t}</li>`).join('')}</ul></div>` : ''}
    </section>

    <section>
      <h2>Living in Our Home</h2>
      ${housemate?.mealsPolicy ? `<p><strong>Meals:</strong> ${housemate.mealsPolicy}</p>` : ''}
      ${housemate?.mealsNuance ? `<p>${housemate.mealsNuance}</p>` : ''}
      ${housemate?.kitchenCleanupExpectations ? `<p><strong>Kitchen clean-up:</strong> ${housemate.kitchenCleanupExpectations}</p>` : ''}
      ${housemate?.roomStandards ? `<p><strong>Room and bathroom:</strong> ${housemate.roomStandards}</p>` : ''}
      ${housemate?.curfew ? `<p><strong>Curfew:</strong> ${housemate.curfew}</p>` : ''}
      ${housemate?.visitorPolicy ? `<p><strong>Visitors:</strong> ${housemate.visitorPolicy}</p>` : ''}
      ${housemate?.overnightGuestPolicy ? `<p><strong>Overnight guests:</strong> ${housemate.overnightGuestPolicy}</p>` : ''}
    </section>

    <section>
      <h2>Household Reference</h2>
      ${household?.wifiName ? `<p><strong>WiFi:</strong> ${household.wifiName} · Password: ${household.wifiPassword}</p>` : ''}
      ${household?.hvacInstructions ? `<p><strong>Heating & cooling:</strong> ${household.hvacInstructions}</p>` : ''}
      ${household?.nearestHospital ? `<p><strong>Nearest hospital:</strong> ${household.nearestHospital}</p>` : ''}
      ${household?.doctorInfo ? `<p><strong>Children's doctor:</strong> ${household.doctorInfo}</p>` : ''}
      ${household?.safetyNotes ? `<p><strong>Safety:</strong> ${household.safetyNotes}</p>` : ''}
    </section>

    ${screenTimePerChild ? `
    <section>
      <h2>Screen Time &amp; Media</h2>
      ${screenTime?.overallPhilosophy ? `<div class="intro-block" style="margin-bottom:20px">${screenTime.overallPhilosophy}</div>` : ''}
      ${screenTimePerChild}
    </section>` : ''}

    <section>
      <h2>Our Discipline Approach</h2>
      ${discipline?.overallPhilosophy ? `<div class="intro-block" style="margin-bottom:20px">${discipline.overallPhilosophy}</div>` : ''}
      ${hardRules ? `<div><h3>Hard rules</h3><ul>${hardRules}</ul></div>` : ''}
      ${discipline?.positiveReinforcement ? `<p><strong>Positive reinforcement:</strong> ${discipline.positiveReinforcement}</p>` : ''}
      ${disciplinePerChild ? `<div><h3>Per-child notes</h3>${disciplinePerChild}</div>` : ''}
    </section>

  </div>

  <footer>
    Generated by <strong>Pair</strong> · The au pair relationship platform
  </footer>
</body>
</html>`;
}

// ── Answer Assembly ──────────────────────────────────────────────────────────

function assembleGuideData(rows: { question_id: string; repeat_index: number; answer_json: unknown }[]) {
  const get = (id: string) => rows.find((r) => r.question_id === id && r.repeat_index === 0)?.answer_json;
  const getString = (id: string) => (get(id) as string) ?? '';
  const getArray = (id: string) => (get(id) as string[]) ?? [];
  const getBool = (id: string) => (get(id) as boolean) ?? false;

  const children = (get('children_list') as {
    id: string; name: string; dateOfBirth: string; specialNeeds: boolean;
  }[]) ?? [];

  function ageDisplay(dob: string): string {
    const birth = new Date(dob);
    const now = new Date();
    const months = (now.getFullYear() - birth.getFullYear()) * 12 + (now.getMonth() - birth.getMonth());
    if (months < 24) return `${months} months`;
    const years = Math.floor(months / 12);
    return `${years} years`;
  }

  const styleScale = get('household_style') as number ?? 3;
  const householdStyleLabel = styleScale <= 2 ? 'Relaxed' : styleScale >= 4 ? 'Structured' : 'Balanced';
  const commStyle = getString('communication_style').replace('_', ' ');

  return {
    generatedAt: new Date().toISOString(),
    familyGoals: {
      familyName: getString('family_name'),
      familyIntro: getString('family_intro'),
      householdStyle: householdStyleLabel,
      childcareStyle: getString('childcare_style').replace('_', ' '),
      culturalExchangeGoals: getString('cultural_exchange_goals'),
      communicationPreferences: commStyle,
      primaryLanguage: getString('primary_language'),
    },
    children: children.map((c) => ({
      name: c.name,
      ageDisplay: ageDisplay(c.dateOfBirth),
      specialNeeds: c.specialNeeds,
      dietaryRestrictions: [],
      allergies: [],
      medicalNotes: '',
      schoolName: '',
      schoolPickupTime: '',
      emotionalRegulationApproach: '',
      preferredActivities: [],
      napSchedule: '',
    })),
    responsibilities: {
      childcareDuties: getArray('childcare_duties_overview'),
      schoolPickupInstructions: getString('child_school_pickup_details_0'),
      laundryInstructions: getString('laundry_instructions'),
      foodPrepResponsibilities: getString('food_prep_notes'),
      seasonalTasks: getArray('seasonal_tasks'),
    },
    housemateExpectations: {
      mealsPolicy: getString('meals_policy').replace('_', ' '),
      mealsNuance: getString('meals_nuance'),
      kitchenCleanupExpectations: getString('kitchen_cleanup').replace('_', ' '),
      roomStandards: getString('room_standards').replace('_', ' '),
      curfew: getString('personal_curfew').replace('_', ' '),
      visitorPolicy: getString('visitor_policy').replace('_', ' '),
      overnightGuestPolicy: getString('overnight_guests').replace('_', ' '),
    },
    householdInfo: {
      wifiName: getString('wifi_name'),
      wifiPassword: getString('wifi_password'),
      hvacInstructions: getString('hvac_instructions'),
      nearestHospital: getString('nearest_hospital'),
      doctorInfo: getString('doctor_info'),
      safetyNotes: getString('safety_notes'),
    },
    screenTime: {
      overallPhilosophy: getString('screen_time_philosophy_notes'),
      perChild: children.map((c, i) => ({
        childName: c.name,
        dailyLimitMinutes: rows.find((r) => r.question_id === 'child_daily_screen_limit' && r.repeat_index === i)?.answer_json ?? 'Not specified',
        approvedApps: rows.find((r) => r.question_id === 'child_approved_content' && r.repeat_index === i)?.answer_json ?? '',
        restrictedContent: rows.find((r) => r.question_id === 'child_restricted_content' && r.repeat_index === i)?.answer_json ?? '',
        deviceRules: '',
      })),
    },
    discipline: {
      overallPhilosophy: getString('discipline_overall_philosophy'),
      approachSteps: getArray('discipline_style'),
      hardRules: (get('hard_rules') as string[]) ?? [],
      positiveReinforcement: getString('positive_reinforcement_approach'),
      perChild: children.map((c, i) => ({
        childName: c.name,
        specialApproach: rows.find((r) => r.question_id === 'child_special_needs_discipline' && r.repeat_index === i)?.answer_json as string ?? '',
      })),
    },
  };
}

// ── Handler ─────────────────────────────────────────────────────────────────

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { householdId } = await req.json() as { householdId: string };
    if (!householdId) {
      return new Response(JSON.stringify({ error: 'householdId required' }), {
        status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );

    // Fetch all answers
    const { data: rows, error } = await supabase
      .from('wizard_answers')
      .select('question_id, repeat_index, answer_json')
      .eq('household_id', householdId);

    if (error) throw error;

    // Assemble guide data
    const guideData = assembleGuideData(rows ?? []);
    const html = renderGuideHtml(guideData);

    // Store HTML in Supabase Storage
    const storagePath = `guides/${householdId}/guide.html`;
    const { error: uploadError } = await supabase.storage
      .from('guides')
      .upload(storagePath, html, {
        contentType: 'text/html; charset=utf-8',
        upsert: true,
      });

    if (uploadError) throw uploadError;

    // Generate share token
    const { data: tokenRow, error: tokenError } = await supabase
      .from('share_tokens')
      .insert({ household_id: householdId })
      .select('token')
      .single();

    if (tokenError) throw tokenError;

    // Record generated guide
    await supabase.from('generated_guides').insert({
      household_id: householdId,
      storage_path: storagePath,
    });

    // Update household wizard_completed_at
    await supabase
      .from('households')
      .update({ wizard_completed_at: new Date().toISOString() })
      .eq('id', householdId);

    const shareUrl = `${Deno.env.get('APP_URL') ?? 'https://pair.app'}/guide/${householdId}?t=${tokenRow.token}`;

    return new Response(
      JSON.stringify({ success: true, shareUrl, token: tokenRow.token }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } },
    );
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
