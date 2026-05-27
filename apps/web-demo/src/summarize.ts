import type { AnswerValue } from '@pair/types';

type Answers = Record<string, AnswerValue>;

// ── Helpers ──────────────────────────────────────────────────────────────────

function clean(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function str(v: AnswerValue | undefined): string {
  if (typeof v === 'string') return v.trim();
  if (typeof v === 'number') return String(v);
  return '';
}

// Use for single_choice / multi_choice option values (snake_case → Title Case, always capitalise first letter)
function lbl(v: AnswerValue | undefined): string {
  const s = str(v);
  const cleaned = s.includes('_') && !s.includes(' ') ? clean(s) : s;
  return cleaned.length > 0 ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : cleaned;
}

function arr(v: AnswerValue | undefined): string[] {
  if (Array.isArray(v)) return (v as string[]).map(s => String(s).trim()).filter(Boolean);
  return [];
}

function lblArr(v: AnswerValue | undefined): string[] {
  return arr(v).map(s => {
    const cleaned = s.includes('_') && !s.includes(' ') ? clean(s) : s;
    return cleaned.length > 0 ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : cleaned;
  });
}

function joinList(items: string[]): string {
  if (items.length === 0) return '';
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`;
}

function bool(v: AnswerValue | undefined): boolean | null {
  if (v === true || v === 'yes') return true;
  if (v === false || v === 'no') return false;
  return null;
}

interface Child { name: string; dateOfBirth: string; specialNeeds: boolean; }

function children(answers: Answers): Child[] {
  const v = answers['children_list'];
  return Array.isArray(v) ? (v as Child[]) : [];
}

function ageLabel(dateOfBirth: string): string {
  if (!dateOfBirth) return '';
  const months = Math.floor((Date.now() - new Date(dateOfBirth).getTime()) / (1000 * 60 * 60 * 24 * 30.44));
  if (months < 12) return `${months} month${months !== 1 ? 's' : ''} old`;
  const yrs = Math.floor(months / 12);
  return `${yrs} year${yrs !== 1 ? 's' : ''} old`;
}

// Build a paragraph from an array of sentences, filtering blanks
function para(sentences: (string | null | undefined)[]): string {
  return sentences.filter(Boolean).join(' ');
}

// Build a structured block: "Label: value" or "Label: value. Notes." style
function item(label: string, value: string | null | undefined, notes?: string | null): string | null {
  if (!value) return null;
  return notes ? `${label}: ${value}. ${notes}.` : `${label}: ${value}.`;
}

// ── Section 1: Family Goals ───────────────────────────────────────────────────

export function summarizeFamilyGoals(answers: Answers): string {
  const name = str(answers['family_name']) || 'Your family';
  const intro = str(answers['family_intro']);
  const primaryLang = lbl(answers['primary_language']);
  const extraLangs = lblArr(answers['additional_languages']);
  const childcareStyle = lbl(answers['childcare_style']);
  const householdScale = typeof answers['household_style'] === 'number' ? answers['household_style'] as number : null;
  const culturalScale = typeof answers['cultural_exchange_emphasis'] === 'number' ? answers['cultural_exchange_emphasis'] as number : null;
  const culturalGoals = str(answers['cultural_exchange_goals']);
  const participation = lbl(answers['au_pair_cultural_participation']);
  const commStyle = lbl(answers['communication_style']);
  const checkIn = lbl(answers['check_in_frequency']);
  const priorities = lblArr(answers['top_priorities']);

  const householdStyleLabel = householdScale !== null
    ? householdScale <= 2 ? 'very relaxed and go-with-the-flow'
    : householdScale <= 3 ? 'moderately structured — a balance of routine and flexibility'
    : householdScale === 4 ? 'fairly structured with clear expectations'
    : 'very structured with consistent rules and routines'
    : null;

  const culturalLabel = culturalScale !== null
    ? culturalScale <= 2 ? 'not a central priority — the role is primarily practical childcare'
    : culturalScale <= 3 ? 'moderately important — they appreciate genuine exchange but don\'t require it'
    : culturalScale === 4 ? 'quite important to this family'
    : 'central to why this family hosts — they want a genuine, two-way cultural experience'
    : null;

  const participationSentence: Record<string, string> = {
    full_member: 'The au pair is considered a full family member — expected to join meals, outings, and family events.',
    welcome_but_own_space: 'The au pair is welcome at family events but also has full independence in their own time.',
    professional: 'The family prefers a more professional arrangement with a clear boundary between working and personal time.',
  };

  const parts: string[] = [];

  // Opening — family intro
  if (intro) {
    parts.push(`${name} describes themselves like this: "${intro}".`);
  } else {
    parts.push(`This section introduces ${name}.`);
  }

  // Language
  const langSentence = extraLangs.length > 0
    ? `The main language at home is ${primaryLang || 'English'}, and the family also speaks ${joinList(extraLangs)}.`
    : primaryLang
    ? `The main language spoken at home is ${primaryLang}.`
    : null;
  if (langSentence) parts.push(langSentence);

  // Childcare style
  if (childcareStyle) {
    parts.push(`Their approach to childcare is ${childcareStyle.toLowerCase()}.`);
  }

  // Household feel
  if (householdStyleLabel) {
    parts.push(`The overall feel of the household is ${householdStyleLabel}.`);
  }

  // Cultural exchange
  if (culturalLabel) {
    parts.push(`Cultural exchange is ${culturalLabel}.`);
  }
  if (culturalGoals) {
    parts.push(`In terms of what they hope the children will gain: "${culturalGoals}".`);
  }

  // Au pair participation
  const participationKey = str(answers['au_pair_cultural_participation']);
  const participationText = participationSentence[participationKey];
  if (participationText) parts.push(participationText);

  // Communication
  if (commStyle) {
    parts.push(`For communication, the family prefers a ${commStyle.toLowerCase()} style.`);
  }
  if (checkIn) {
    parts.push(`Formal check-ins with the au pair will happen ${checkIn.toLowerCase()}.`);
  }

  // Priorities
  if (priorities.length > 0) {
    parts.push(`Their top priorities for this au pair year are: ${joinList(priorities)}.`);
  }

  return para(parts);
}

// ── Section 2: Responsibilities ───────────────────────────────────────────────

export function summarizeResponsibilities(answers: Answers): string {
  const kids = children(answers);
  const duties = lblArr(answers['childcare_duties_overview']);
  const laundry = lbl(answers['children_laundry']);
  const laundryNotes = str(answers['laundry_instructions']);
  const foodPrep = lblArr(answers['food_prep_responsibility']);
  const foodNotes = str(answers['food_prep_notes']);
  const hasCar = bool(answers['has_car_access']);
  const carDuties = lblArr(answers['car_driving_expectations']);
  const seasonal = lblArr(answers['seasonal_tasks']);
  const seasonalOther = str(answers['seasonal_tasks_other']);

  const parts: string[] = [];

  // Children overview
  if (kids.length === 0) {
    parts.push('No children have been added to the profile yet.');
  } else {
    const childDesc = kids.map(c =>
      `${c.name} (${ageLabel(c.dateOfBirth)}${c.specialNeeds ? ', additional needs' : ''})`
    ).join(', ');
    parts.push(`The au pair will care for ${kids.length} child${kids.length > 1 ? 'ren' : ''}: ${childDesc}.`);
  }

  // Per-child details
  kids.forEach((child, i) => {
    const pickup = bool(answers[`child_school_pickup_${i}`]);
    const pickupDetails = str(answers[`child_school_pickup_details_${i}`]);
    const nap = str(answers[`child_nap_schedule_${i}`]);
    const feeding = str(answers[`child_feeding_routine_${i}`]);
    const bedtime = str(answers[`child_bedtime_routine_${i}`]);
    const pottyStatus = lbl(answers[`child_potty_status_${i}`]);
    const pottyNotes = str(answers[`child_potty_notes_${i}`]);
    const homeworkYes = bool(answers[`child_homework_support_${i}`]);
    const homeworkDetails = str(answers[`child_homework_details_${i}`]);
    const afterSchool = str(answers[`child_after_school_routine_${i}`]);

    const childParts: string[] = [`For ${child.name}:`];

    if (pickup === true && pickupDetails) childParts.push(`Pick-up — ${pickupDetails}`);
    else if (pickup === true) childParts.push('School or daycare pick-up is required.');
    else if (pickup === false) childParts.push('No school pick-up required.');

    if (nap) childParts.push(`Nap schedule — ${nap}`);
    if (feeding) childParts.push(`Feeding routine — ${feeding}`);
    if (bedtime) childParts.push(`Bedtime routine — ${bedtime}`);
    if (pottyStatus) childParts.push(`Potty status: ${pottyStatus}${pottyNotes ? `. ${pottyNotes}` : ''}`);
    if (afterSchool) childParts.push(`After-school routine — ${afterSchool}`);
    if (homeworkYes === true && homeworkDetails) childParts.push(`Homework support — ${homeworkDetails}`);
    else if (homeworkYes === true) childParts.push('Homework support is expected.');
    else if (homeworkYes === false) childParts.push('No homework support required.');

    if (childParts.length > 1) parts.push(childParts.join(' '));
  });

  // General childcare duties
  if (duties.length > 0) {
    parts.push(`General childcare duties include: ${joinList(duties)}.`);
  }

  // Laundry
  if (laundry) {
    parts.push(laundryNotes
      ? `Children's laundry: ${laundry}. ${laundryNotes}.`
      : `Children's laundry: ${laundry}.`
    );
  }

  // Food prep
  if (foodPrep.length > 0) {
    parts.push(foodNotes
      ? `Food preparation responsibilities: ${joinList(foodPrep)}. ${foodNotes}.`
      : `Food preparation responsibilities: ${joinList(foodPrep)}.`
    );
  }

  // Car
  if (hasCar === true) {
    parts.push(carDuties.length > 0
      ? `The au pair will have access to a family car and will drive the children to: ${joinList(carDuties)}.`
      : 'The au pair will have access to a family car.'
    );
  } else if (hasCar === false) {
    parts.push('The au pair will not have access to a family car.');
  }

  // Seasonal tasks
  if (seasonal.length > 0 || seasonalOther) {
    const all = seasonalOther ? [...seasonal, seasonalOther] : seasonal;
    parts.push(`There are also seasonal or additional tasks to help with: ${joinList(all)}.`);
  }

  return para(parts);
}

// ── Section 3: Housemate Expectations ────────────────────────────────────────

export function summarizeHousemateExpectations(answers: Answers): string {
  const meals = lbl(answers['meals_policy']);
  const mealsNuance = str(answers['meals_nuance']);
  const kitchen = lbl(answers['kitchen_cleanup']);
  const kitchenNotes = str(answers['kitchen_cleanup_notes']);
  const room = lbl(answers['room_standards']);
  const roomNotes = str(answers['room_standards_notes']);
  const commonAreas = str(answers['common_areas']);
  const curfew = lbl(answers['personal_curfew']);
  const curfewNotes = str(answers['curfew_notes']);
  const weekendCurfew = lbl(answers['weekend_curfew']);
  const visitors = lbl(answers['visitor_policy']);
  const visitorNotes = str(answers['visitor_notes']);
  const overnight = lbl(answers['overnight_guests']);
  const quiet = str(answers['noise_quiet_hours']);
  const smoking = lbl(answers['smoking_policy']);
  const other = str(answers['personal_space_philosophy']);

  const parts: string[] = [];

  parts.push('Here is what day-to-day life in the home looks like for the au pair.');

  // Meals
  const mealsMap: Record<string, string> = {
    full_family_meals: 'All meals are provided — the au pair eats with or alongside the family, and groceries are fully covered.',
    family_groceries: 'The au pair may use family groceries freely and is welcome at all family meals.',
    designated_food: 'The family buys specific food for the au pair. Family food is kept separate.',
    stipend_covers: 'The au pair is responsible for their own food — the stipend accounts for this.',
  };
  const mealKey = str(answers['meals_policy']);
  const mealText = mealsMap[mealKey] || (meals ? `Meals policy: ${meals}.` : null);
  if (mealText) parts.push(mealText);
  if (mealsNuance) parts.push(mealsNuance);

  // Kitchen
  if (kitchen) {
    parts.push(kitchenNotes
      ? `Kitchen clean-up expectation: ${kitchen}. ${kitchenNotes}.`
      : `Kitchen clean-up expectation: ${kitchen}.`
    );
  }

  // Room and bathroom
  if (room) {
    parts.push(roomNotes
      ? `Room and bathroom standards: ${room}. ${roomNotes}.`
      : `Room and bathroom standards: ${room}.`
    );
  }

  // Common areas
  if (commonAreas) {
    parts.push(`Common areas (living room, kitchen, garden): ${commonAreas}`);
  }

  // Curfew
  const curfewMap: Record<string, string> = {
    no_curfew: 'There is no set weekday curfew, as long as work is not affected.',
    midnight: 'On weekdays, the au pair should be home by midnight.',
    eleven_pm: 'On weekdays, the au pair should be home by 11pm.',
    ten_pm: 'On weekdays, the au pair should be home by 10pm.',
  };
  const curfewKey = str(answers['personal_curfew']);
  const curfewText = curfewMap[curfewKey] || (curfew ? `Weekday curfew: ${curfew}.` : null);
  if (curfewText) parts.push(curfewText);
  if (curfewNotes) parts.push(curfewNotes);

  // Weekend curfew
  const weekendKey = str(answers['weekend_curfew']);
  if (weekendKey === 'no_curfew') parts.push('On weekend nights, there is no curfew.');
  else if (weekendKey === 'same_as_weekday') parts.push('The weekend curfew is the same as weekdays.');
  else if (weekendKey === 'later') parts.push('On weekends the curfew is later — see any notes above.');

  // Visitors
  const visitorMap: Record<string, string> = {
    open: 'Guests are welcome any time, as long as the family is given advance notice.',
    limited_times: 'Guests are welcome during daytime and early evening. Late-night visitors should be discussed first.',
    discuss_first: 'Any guests coming to the home should be discussed with the family beforehand.',
    no_visitors: 'The family prefers the home to be a private family space — no regular visitors.',
  };
  const visitorKey = str(answers['visitor_policy']);
  const visitorText = visitorMap[visitorKey] || (visitors ? `Visitor policy: ${visitors}.` : null);
  if (visitorText) parts.push(visitorText);
  if (visitorNotes) parts.push(visitorNotes);

  // Overnight guests
  const overnightMap: Record<string, string> = {
    allowed_with_notice: 'Occasional overnight guests are allowed with advance notice.',
    limited: 'Overnight guests are allowed occasionally and by agreement — not regularly.',
    not_allowed: 'Overnight guests in the au pair\'s room are not permitted.',
  };
  const overnightKey = str(answers['overnight_guests']);
  const overnightText = overnightMap[overnightKey] || (overnight ? `Overnight guests: ${overnight}.` : null);
  if (overnightText) parts.push(overnightText);

  // Quiet hours
  if (quiet) {
    parts.push(`Quiet hours: ${quiet}.`);
  }

  // Smoking
  const smokingMap: Record<string, string> = {
    no_smoking: 'Smoking is not allowed on or near the property.',
    outside_only: 'Smoking is permitted outside only, and never near the children.',
    not_a_concern: 'There is no specific restriction on smoking.',
  };
  const smokingKey = str(answers['smoking_policy']);
  const smokingText = smokingMap[smokingKey] || null;
  if (smokingText) parts.push(smokingText);

  // Other / personal space
  if (other) {
    parts.push(other);
  }

  return para(parts);
}

// ── Section 4: Household Info ─────────────────────────────────────────────────

export function summarizeHouseholdInfo(answers: Answers): string {
  const wifi = str(answers['wifi_name']);
  const hasWifiPwd = !!str(answers['wifi_password']);
  const appliances = lblArr(answers['appliances_overview']);
  const washingMachine = str(answers['washing_machine_instructions']);
  const dryer = str(answers['dryer_instructions']);
  const dishwasher = str(answers['dishwasher_instructions']);
  const oven = str(answers['oven_instructions']);
  const alarm = str(answers['alarm_system_instructions']);
  const carSeat = str(answers['car_seat_instructions']);
  const otherAppliances = str(answers['other_appliance_notes']);
  const hvac = str(answers['hvac_instructions']);
  const emergency = answers['emergency_contacts'];
  const hospital = str(answers['nearest_hospital']);
  const doctor = str(answers['doctor_info']);
  const keyAddresses = answers['key_addresses'];
  const safety = str(answers['safety_notes']);
  const houseOther = str(answers['house_rules_other']);

  const parts: string[] = [];

  parts.push('This section covers the practical details the au pair needs to know about the home.');

  // WiFi
  if (wifi) {
    parts.push(`WiFi network name: ${wifi}${hasWifiPwd ? ' (password is noted in the guide)' : ''}.`);
  }

  // Appliances overview
  if (appliances.length > 0) {
    parts.push(`Appliances the au pair needs to know how to use: ${joinList(appliances)}.`);
  }

  // Appliance-specific instructions
  if (washingMachine) parts.push(`Washing machine: ${washingMachine}.`);
  if (dryer) parts.push(`Dryer: ${dryer}.`);
  if (dishwasher) parts.push(`Dishwasher: ${dishwasher}.`);
  if (oven) parts.push(`Oven: ${oven}.`);
  if (alarm) parts.push(`Security alarm: ${alarm}.`);
  if (carSeat) parts.push(`Car seat: ${carSeat}.`);
  if (otherAppliances) parts.push(`Other appliances or systems: ${otherAppliances}.`);

  // Heating and cooling
  if (hvac) {
    parts.push(`Heating and cooling: ${hvac}.`);
  }

  // Emergency contacts
  if (Array.isArray(emergency) && (emergency as Record<string, string>[]).length > 0) {
    const contacts = (emergency as Record<string, string>[])
      .map(c => [c.name, c.phone, c.role].filter(Boolean).join(' — '))
      .filter(Boolean);
    if (contacts.length > 0) {
      parts.push(`Emergency contacts: ${contacts.join('; ')}.`);
    }
  }

  if (hospital) parts.push(`Nearest hospital or urgent care: ${hospital}.`);
  if (doctor) parts.push(`Children's doctor: ${doctor}.`);

  // Key addresses
  if (Array.isArray(keyAddresses) && (keyAddresses as Record<string, string>[]).length > 0) {
    const addrs = (keyAddresses as Record<string, string>[])
      .map(a => [a.name, a.address].filter(Boolean).join(': '))
      .filter(Boolean);
    if (addrs.length > 0) {
      parts.push(`Key locations: ${addrs.join('; ')}.`);
    }
  }

  // Safety notes
  if (safety) parts.push(`Safety notes: ${safety}.`);

  // Other house notes
  if (houseOther) parts.push(houseOther);

  return para(parts);
}

// ── Section 5: Screen Time & Media ────────────────────────────────────────────

export function summarizeScreenTime(answers: Answers): string {
  const philosophy = lbl(answers['screen_time_philosophy']);
  const philosophyNotes = str(answers['screen_time_philosophy_notes']);
  const noScreen = lblArr(answers['no_screen_situations']);
  const auPairPhone = lbl(answers['au_pair_phone_during_care']);
  const auPairPhoneNotes = str(answers['au_pair_phone_notes']);
  const kids = children(answers);

  const parts: string[] = [];

  // Overall philosophy
  if (philosophy) {
    parts.push(`The family's overall approach to screen time is "${philosophy.toLowerCase()}".`);
  }
  if (philosophyNotes) {
    parts.push(philosophyNotes);
  }

  // No-screen situations
  if (noScreen.length > 0) {
    parts.push(`Screens are never allowed during: ${joinList(noScreen)}.`);
  }

  // Per-child screen time
  kids.forEach((child, i) => {
    const limit = lbl(answers[`child_daily_screen_limit_${i}`]);
    const approved = str(answers[`child_approved_content_${i}`]);
    const restricted = str(answers[`child_restricted_content_${i}`]);
    const devices = lblArr(answers[`child_device_rules_${i}`]);
    const gaming = str(answers[`child_gaming_rules_${i}`]);
    const social = lbl(answers[`child_social_media_${i}`]);

    const childParts: string[] = [`For ${child.name}:`];

    if (limit) childParts.push(`daily screen limit is ${limit.toLowerCase()}`);
    if (approved) childParts.push(`approved content — ${approved}`);
    if (restricted) childParts.push(`not allowed — ${restricted}`);
    if (devices.length > 0) childParts.push(`approved devices: ${joinList(devices)}`);
    if (gaming) childParts.push(`gaming rules — ${gaming}`);
    if (social) childParts.push(`social media policy: ${social}`);

    if (childParts.length > 1) parts.push(childParts.join('. ') + '.');
  });

  // Au pair phone policy
  const phoneMap: Record<string, string> = {
    no_phone: 'The au pair\'s own phone should be put away during working hours, except for emergencies.',
    emergencies_only: 'The au pair may use their phone for emergencies and child-related communication only — not personal browsing or social media.',
    reasonable_use: 'Reasonable phone use is fine, as long as the children are safe and engaged.',
    flexible: 'The family trusts the au pair to use their phone responsibly without it affecting care.',
  };
  const phoneKey = str(answers['au_pair_phone_during_care']);
  const phoneText = phoneMap[phoneKey] || (auPairPhone ? `Au pair phone during care: ${auPairPhone}.` : null);
  if (phoneText) parts.push(phoneText);
  if (auPairPhoneNotes) parts.push(auPairPhoneNotes);

  return para(parts);
}

// ── Section 6: Discipline Philosophy ─────────────────────────────────────────

export function summarizeDiscipline(answers: Answers): string {
  const overall = str(answers['discipline_overall_philosophy']);
  const styles = lblArr(answers['discipline_style']);
  const priorNotice = bool(answers['prior_notice_approach']);
  const priorNoticeNotes = str(answers['prior_notice_notes']);
  const timeout = bool(answers['timeout_approach']);
  const timeoutNotes = str(answers['timeout_notes']);
  const positive = str(answers['positive_reinforcement_approach']);
  const hardRules = arr(answers['hard_rules']);
  const physical = lbl(answers['physical_discipline_stance']);
  const whatNot = str(answers['what_not_to_do']);
  const escalation = str(answers['escalation_protocol']);
  const debrief = lbl(answers['discipline_debrief']);
  const anythingElse = str(answers['discipline_anything_else']);
  const kids = children(answers);

  const physicalMap: Record<string, string> = {
    absolutely_not: 'Physical discipline of any kind is absolutely not allowed, under any circumstances.',
    not_by_au_pair: 'Physical discipline is not to be used by the au pair. The family handles these situations.',
    discuss: 'The family would like to discuss this topic directly.',
  };

  const debriefMap: Record<string, string> = {
    realtime: 'For anything significant, the au pair should text the parents immediately.',
    end_of_day: 'Discipline incidents should be shared in an end-of-day verbal update.',
    app_log: 'The au pair should log incidents in the app — parents will review.',
    only_if_major: 'Only major incidents need to be communicated — the family trusts the au pair\'s judgement for small things.',
  };

  const parts: string[] = [];

  // Overall philosophy
  if (overall) {
    parts.push(overall);
  } else {
    parts.push('The family has shared how they approach discipline and behaviour at home.');
  }

  // Discipline styles
  if (styles.length > 0) {
    parts.push(`Their preferred approaches are: ${joinList(styles)}.`);
  }

  // Advance warnings
  if (priorNotice === true) {
    parts.push(priorNoticeNotes
      ? `The family uses advance warnings before transitions or consequences. ${priorNoticeNotes}.`
      : 'The family uses advance warnings before transitions or consequences (for example, a 5-minute warning before screen time ends).'
    );
  } else if (priorNotice === false) {
    parts.push('The family does not typically use advance warnings before consequences.');
  }

  // Time-out
  if (timeout === true) {
    parts.push(timeoutNotes
      ? `Time-out or a cool-down space is used in this household. ${timeoutNotes}.`
      : 'Time-out or a cool-down space is used when children need to calm down.'
    );
  } else if (timeout === false) {
    parts.push('The family does not use time-out as a discipline tool.');
  }

  // Positive reinforcement
  if (positive) {
    parts.push(`Positive reinforcement: ${positive}.`);
  }

  // Hard rules
  if (hardRules.filter(Boolean).length > 0) {
    const ruleList = hardRules.filter(Boolean).map((r, i) => `${i + 1}. ${r}`).join(' ');
    parts.push(`The non-negotiable household rules are: ${ruleList}.`);
  }

  // Physical discipline
  const physKey = str(answers['physical_discipline_stance']);
  const physText = physicalMap[physKey] || null;
  if (physText) parts.push(physText);

  // What not to do
  if (whatNot) {
    parts.push(`The au pair should please never: ${whatNot}.`);
  }

  // Escalation
  if (escalation) {
    parts.push(`If a situation escalates beyond what the au pair can handle: ${escalation}.`);
  }

  // Debrief / communication
  const debriefKey = str(answers['discipline_debrief']);
  const debriefText = debriefMap[debriefKey] || null;
  if (debriefText) parts.push(debriefText);

  // Per-child special needs discipline
  kids.filter(c => c.specialNeeds).forEach((child, idx) => {
    const i = kids.indexOf(child);
    const snDiscipline = str(answers[`child_special_needs_discipline_${i}`]);
    const hasTherapist = bool(answers[`child_therapist_coordination_${i}`]);
    const therapistNotes = str(answers[`child_therapist_notes_${i}`]);

    if (snDiscipline) {
      parts.push(`For ${child.name} specifically (additional needs): ${snDiscipline}.`);
    }
    if (hasTherapist === true && therapistNotes) {
      parts.push(`${child.name} works with a specialist — ${therapistNotes}.`);
    } else if (hasTherapist === true) {
      parts.push(`${child.name} works with a therapist or specialist — the family will share the details directly.`);
    }
  });

  // Anything else
  if (anythingElse) {
    parts.push(anythingElse);
  }

  return para(parts);
}

export function generateAllSummaries(answers: Answers): Record<string, string> {
  return {
    family_goals: summarizeFamilyGoals(answers),
    responsibilities: summarizeResponsibilities(answers),
    housemate_expectations: summarizeHousemateExpectations(answers),
    household_info: summarizeHouseholdInfo(answers),
    screen_time_media: summarizeScreenTime(answers),
    discipline_philosophy: summarizeDiscipline(answers),
  };
}
