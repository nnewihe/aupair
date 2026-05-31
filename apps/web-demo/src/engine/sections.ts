export type InputType = 'text' | 'textarea' | 'multi-select' | 'single-select' | 'toggle' | 'children-list' | 'text-list' | 'date-range-list' | 'textarea-and-date-range-list';

export interface QuestionOption {
  value: string;
  group?: string;
  freeText?: boolean;
}

export interface FollowUpQuestion {
  triggerValue: string;
  id: string;
  text: string;
  inputType: InputType;
  options?: QuestionOption[];
  placeholder?: string;
  optional?: boolean;
}

export interface Question {
  id: string;
  text: string;
  subtext?: string;
  inputType: InputType;
  options?: QuestionOption[];
  optional?: boolean;
  placeholder?: string;
  followUp?: FollowUpQuestion;
  starterBullets?: string[];
}

export interface ChildInfo {
  name: string;
  age: string;
}

export interface DateRange {
  start: string;
  end: string;
}

export interface TextAndDateRanges {
  text: string;
  ranges: DateRange[];
}

export interface Section {
  id: string;
  title: string;
  icon: string;
  description?: string;
  questions: Question[];
  repeatingPerChild?: boolean;
  estimatedMinutes: number;
}

export type ToneOption = 'warm' | 'balanced' | 'directive';

export const TONE_OPTIONS: { value: ToneOption; label: string; description: string }[] = [
  { value: 'warm', label: 'Warm & conversational', description: 'Friendly, personal tone — feels like advice from a friend' },
  { value: 'balanced', label: 'Balanced & professional', description: 'Clear and warm, suitable for any audience' },
  { value: 'directive', label: 'Clear & directive', description: 'Crisp and direct — unambiguous expectations' },
];

// Per-child questions — asked once per child after children_list is answered
export const PER_CHILD_QUESTIONS: Question[] = [
  {
    id: 'dietary_restrictions',
    text: 'Dietary restrictions or allergies',
    subtext: 'Select all that apply',
    inputType: 'multi-select',
    options: [
      { value: 'None' },
      { value: 'Nut allergy', freeText: true },
      { value: 'Dairy-free' },
      { value: 'Gluten-free' },
      { value: 'Vegetarian' },
      { value: 'Vegan' },
      { value: 'Kosher' },
      { value: 'Halal' },
      { value: 'Other', freeText: true },
    ],
  },
  {
    id: 'medical_info',
    text: 'Any important medical information?',
    subtext: 'e.g. current medication, conditions the au pair must be aware of',
    inputType: 'textarea',
    placeholder: 'Include anything relevant to the au pair\'s day-to-day care...',
  },
  {
    id: 'potty_trained',
    text: 'Is this child potty trained?',
    inputType: 'single-select',
    options: [{ value: 'Yes' }, { value: 'In progress' }, { value: 'No' }],
  },
  {
    id: 'favourite_activities',
    text: "What are this child's favourite activities?",
    subtext: 'Select all that apply',
    inputType: 'multi-select',
    options: [
      { value: 'Arts & crafts' },
      { value: 'Puzzles' },
      { value: 'Building toys (e.g., Magna-Tiles, marble runs, LEGO)' },
      { value: 'Pretend play and imaginative games' },
      { value: 'Board games and card games' },
      { value: 'Reading' },
      { value: 'Bike riding / scooter' },
      { value: 'Playground and outdoor play' },
      { value: 'Sports (e.g., soccer, tennis, swimming)' },
      { value: 'Screen time / TV / games' },
      { value: 'Music or singing' },
      { value: 'Cooking or baking together' },
      { value: 'Other', freeText: true },
    ],
  },
  {
    id: 'personality',
    text: "How would you describe this child's personality?",
    subtext: 'Select all that apply',
    inputType: 'multi-select',
    options: [
      { value: 'High-energy and loves to move', group: 'Energy & pace' },
      { value: 'Active but can settle', group: 'Energy & pace' },
      { value: 'Calm and steady', group: 'Energy & pace' },
      { value: 'Quiet and reflective', group: 'Energy & pace' },
      { value: 'Warm and affectionate', group: 'Social style' },
      { value: 'Bubbly and talkative', group: 'Social style' },
      { value: 'Shy initially but opens up over time', group: 'Social style' },
      { value: 'Comfortable with new people straight away', group: 'Social style' },
      { value: 'Prefers one-on-one over group settings', group: 'Social style' },
      { value: 'Loves to lead and direct play', group: 'Play & learning style' },
      { value: 'Happy to follow and go with the flow', group: 'Play & learning style' },
      { value: 'Prefers independent play', group: 'Play & learning style' },
      { value: 'Thrives with a playmate', group: 'Play & learning style' },
      { value: 'Intellectually curious — loves to ask questions', group: 'Play & learning style' },
      { value: 'Loves to read', group: 'Play & learning style' },
      { value: 'Enjoys being challenged', group: 'Play & learning style' },
      { value: 'Competitive', group: 'Play & learning style' },
      { value: 'Collaborative', group: 'Play & learning style' },
      { value: 'Easy-going and adaptable', group: 'Temperament' },
      { value: 'Strong-willed and determined', group: 'Temperament' },
      { value: 'Sensitive — takes things to heart', group: 'Temperament' },
      { value: 'Emotionally expressive', group: 'Temperament' },
      { value: 'Even-keeled — rarely melts down', group: 'Temperament' },
    ],
  },
  {
    id: 'daily_needs',
    text: 'What does this child need most day-to-day?',
    subtext: 'Select all that apply',
    inputType: 'multi-select',
    options: [
      { value: 'Consistent daily routine — changes need advance notice' },
      { value: 'Planned activities — open-ended time is hard' },
      { value: 'Room for spontaneity — too much structure creates friction' },
      { value: 'One-on-one time with a caregiver during the day' },
      { value: 'Independent play time built into the day' },
      { value: 'Regular time outdoors' },
      { value: 'Physical activity to expend energy' },
      { value: 'Quiet wind-down time before transitions' },
      { value: 'Clear expectations upfront — surprises are hard' },
    ],
  },
  {
    id: 'emotional_regulation',
    text: "What approach works best to support this child's emotional regulation?",
    subtext: 'Select all that apply',
    inputType: 'multi-select',
    options: [
      { value: 'Give advance notice before transitions or changes' },
      { value: 'Offer choices rather than directives' },
      { value: 'Use positive incentives — work with parents on the right ones' },
      { value: 'Maintain clear, calm, and consistent boundaries' },
      { value: 'Explain the reasoning behind decisions and rules' },
      { value: 'Distract and redirect quickly when upset' },
      { value: 'Give physical comfort (hug, close proximity)' },
      { value: 'Give space to process before re-engaging' },
    ],
  },
  {
    id: 'meltdown_approach',
    text: 'How do you handle a meltdown with this child?',
    subtext: 'Describe your approach so the au pair can follow your lead',
    inputType: 'textarea',
    optional: true,
    placeholder: 'Walk through what you typically do when this child is really upset...',
  },
  {
    id: 'child_discipline',
    text: 'What is your approach to discipline for this child?',
    subtext: 'Include any hard rules (e.g., no physical discipline, no raised voices)',
    inputType: 'textarea',
    placeholder: 'Be as specific as possible — this is what the au pair will follow...',
  },
];

export const SECTIONS: Section[] = [
  {
    id: 'family',
    title: 'Your Family',
    icon: '🏡',
    estimatedMinutes: 2,
    description: "Required to seed the AI's voice and framing. Complete this section first; all others can be done in any order.",
    questions: [
      {
        id: 'parent_names',
        text: 'What are your first names?',
        inputType: 'text',
        placeholder: 'e.g. Sarah and James',
      },
      {
        id: 'family_vibe',
        text: "How would you describe your family's vibe?",
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: 'Warm and relaxed' },
          { value: 'Structured and routine-driven' },
          { value: 'Busy but flexible' },
          { value: 'Calm and quiet' },
          { value: 'High-energy and active' },
          { value: 'Close-knit — we do most things together' },
        ],
      },
      {
        id: 'au_pair_priorities',
        text: 'What matters most to you about having an au pair?',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: 'Reliable, consistent childcare' },
          { value: 'A positive role model for our children' },
          { value: "Cultural exchange and broadening our children's worldview" },
          { value: 'Flexibility around our work schedules' },
          { value: 'Support with the daily household routine' },
          { value: 'A genuine member of the family during their time with us' },
        ],
      },
      {
        id: 'communication_style',
        text: 'How do you typically prefer to communicate as a household?',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: 'Instant messaging (e.g., WhatsApp, iMessage) for day-to-day updates' },
          { value: 'Brief daily check-ins — a quick verbal debrief at handover' },
          { value: 'A weekly scheduled meeting to review the week ahead' },
          { value: 'As-needed — we raise things when they come up' },
        ],
      },
      {
        id: 'family_intro_notes',
        text: "Is there anything you'd like the au pair to know about your family upfront?",
        inputType: 'textarea',
        optional: true,
        placeholder: 'Anything that would help them feel welcome and prepared from day one...',
      },
    ],
  },
  {
    id: 'children',
    title: 'Your Children',
    icon: '👨‍👩‍👧‍👦',
    estimatedMinutes: 3,
    description: 'These fields populate each child\'s profile and feed into scheduling, handover documents, and performance reviews.',
    repeatingPerChild: true,
    questions: [
      {
        id: 'children_list',
        text: 'Tell us about your children.',
        subtext: "Add each child's name and age.",
        inputType: 'children-list',
      },
    ],
  },
  {
    id: 'responsibilities',
    title: 'Childcare Responsibilities',
    icon: '📋',
    estimatedMinutes: 3,
    questions: [
      {
        id: 'childcare_duties',
        text: "What are the au pair's primary childcare duties?",
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: 'Morning routine — getting children up, dressed, and fed' },
          { value: 'School drop-off' },
          { value: 'School pick-up' },
          { value: 'Engage the children after school' },
          { value: 'Take care of the baby / infant during the day' },
          { value: 'Take children to activities (classes, sports, appointments)' },
          { value: 'Homework support' },
          { value: 'Bedtime routine' },
          { value: 'Nap supervision' },
        ],
      },
      {
        id: 'household_tasks',
        text: 'What additional household tasks are expected?',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: "Children's laundry only" },
          { value: 'Meal preparation for the children' },
          { value: "Kitchen clean-up after children's meals" },
          { value: 'Grocery runs' },
          { value: 'None — childcare only' },
        ],
      },
      {
        id: 'weekday_schedule',
        text: 'What does a typical weekday look like?',
        subtext: "Describe the usual flow — e.g. school drop-off at 8am, free until 3pm pick-up, homework and snack, dinner prep for kids",
        inputType: 'textarea',
        placeholder: "Walk us through a typical weekday from the au pair's perspective...",
      },
      {
        id: 'weekend_different',
        text: 'Is the weekend schedule different?',
        inputType: 'toggle',
        followUp: {
          triggerValue: 'yes',
          id: 'weekend_schedule',
          text: 'Describe the weekend schedule.',
          inputType: 'textarea',
          placeholder: 'Walk us through a typical weekend day...',
        },
      },
      {
        id: 'unsupervised_time',
        text: 'When is the au pair typically alone with the children?',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: 'Weekday mornings' },
          { value: 'Weekday afternoons / after school' },
          { value: 'Full weekdays (both parents working)' },
          { value: 'Weekend days' },
          { value: 'Evening cover while parents are out' },
          { value: 'Overnight when parents travel' },
          { value: 'Rarely — one or both parents are usually home' },
        ],
      },
    ],
  },
  {
    id: 'house_rules',
    title: 'House Rules & Housemate Expectations',
    icon: '🏠',
    estimatedMinutes: 3,
    description: 'The au pair lives in your home. These questions set clear expectations and reduce friction on the small things that cause the most tension.',
    questions: [
      {
        id: 'cleanliness_standards',
        text: 'Cleanliness standards',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: 'Keep your personal space (bedroom, bathroom) clean and tidy' },
          { value: 'Clean up immediately after yourself in shared spaces' },
          { value: 'No dishes left in the sink overnight' },
          { value: 'Wipe down kitchen surfaces after use' },
          { value: "Vacuum or sweep if you've made a mess" },
          { value: 'Leave shared bathrooms clean and dry after use' },
          { value: 'Other', freeText: true },
        ],
      },
      {
        id: 'food_arrangements',
        text: 'Food arrangements',
        subtext: 'Select all that apply — be as specific as possible to avoid ambiguity',
        inputType: 'multi-select',
        options: [
          { value: 'We eat family meals together when possible and you are welcome to join' },
          { value: "You're welcome to eat any shared family food in the fridge and pantry" },
          { value: "We'll purchase specific groceries for you during the weekly shop — let us know what you need within a reasonable budget" },
          { value: "You're welcome to cook your preferred food on your own time" },
          { value: 'You are expected to prepare your own breakfast and lunch' },
          { value: 'We typically order dinner for the adults (including you!) — we all pick cuisines together' },
          { value: 'Other', freeText: true },
        ],
      },
      {
        id: 'common_spaces',
        text: 'Common spaces (living room, kitchen, shared areas)',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: "Common spaces are shared and you're welcome to use them" },
          { value: 'Please keep common areas tidy — items returned to where they belong' },
          { value: 'Evenings after a set time are family / adult time — please give us space' },
          { value: "You're welcome to watch TV in shared spaces when the children are in bed" },
          { value: 'Other', freeText: true },
        ],
      },
      {
        id: 'room_bathroom',
        text: 'Your room and bathroom',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: 'Your room is your private space — we will always knock' },
          { value: 'Please keep your room reasonably tidy' },
          { value: 'You have your own private bathroom' },
          { value: 'You share a bathroom — please coordinate and leave it clean after use' },
          { value: 'Other', freeText: true },
        ],
      },
      {
        id: 'guest_policy',
        text: 'Guest and visitor policy',
        inputType: 'single-select',
        options: [
          { value: 'No overnight guests' },
          { value: 'Occasional overnight guests with advance notice' },
          { value: 'Daytime guests welcome; overnight requires discussion' },
        ],
      },
      {
        id: 'curfew',
        text: 'Curfew or quiet hours?',
        inputType: 'toggle',
        followUp: {
          triggerValue: 'yes',
          id: 'curfew_details',
          text: 'What are the curfew or quiet hours?',
          inputType: 'text',
          placeholder: 'e.g. Quiet hours after 10pm on weeknights, midnight on weekends',
        },
      },
      {
        id: 'car_use',
        text: 'Car use',
        inputType: 'multi-select',
        options: [
          { value: 'No personal use of the family car' },
          { value: 'Family car available for personal use with advance notice' },
          { value: 'Family car available within agreed geographic limits' },
          { value: 'Au pair will drive a dedicated car provided by the family' },
        ],
      },
      {
        id: 'car_use_notes',
        text: 'Any additional notes about car use?',
        inputType: 'textarea',
        optional: true,
        placeholder: 'e.g. Please return the car with at least a quarter tank of fuel...',
      },
    ],
  },
  {
    id: 'benefits',
    title: 'Benefits & Practical Details',
    icon: '✨',
    estimatedMinutes: 2,
    questions: [
      {
        id: 'phone_arrangement',
        text: 'Phone arrangement',
        inputType: 'single-select',
        options: [
          { value: 'We provide a phone and a plan' },
          { value: 'We provide a plan only — au pair expected to use their own phone' },
        ],
      },
      {
        id: 'additional_benefits',
        text: 'Additional benefits offered',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: 'Gym or fitness membership' },
          { value: 'Streaming services (e.g., Netflix, Disney+)' },
          { value: 'Transportation allowance or subway/bus card' },
        ],
      },
      {
        id: 'additional_benefits_custom',
        text: 'Any other benefits to add?',
        subtext: 'Add one per row',
        inputType: 'text-list',
        optional: true,
      },
      {
        id: 'vacation_policy',
        text: 'Vacation policy',
        subtext: 'Standard J-1 entitlement is 2 weeks paid vacation over the course of the year.',
        inputType: 'single-select',
        options: [
          { value: 'Standard — 2 weeks paid per year' },
          { value: 'Above standard — 2 weeks plus additional days' },
        ],
        followUp: {
          triggerValue: 'Above standard — 2 weeks plus additional days',
          id: 'vacation_extra_details',
          text: 'Please specify the additional days.',
          inputType: 'text',
          placeholder: 'e.g. Three additional personal days, taken with two weeks notice',
        },
      },
      {
        id: 'vacation_blocks',
        text: 'How can the 2-week vacation entitlement be taken?',
        subtext: 'The 2-week paid vacation entitlement is a legal requirement and cannot be reduced.',
        inputType: 'single-select',
        options: [
          { value: 'As a single continuous 2-week block' },
          { value: 'As two separate 1-week blocks' },
          { value: 'Flexible — to be agreed between us' },
        ],
      },
      {
        id: 'vacation_together',
        text: 'Does the au pair take vacation at the same time as the family?',
        inputType: 'single-select',
        options: [
          { value: 'Yes — vacation is taken together with the family' },
          { value: 'No — the au pair schedules time off independently' },
        ],
      },
      {
        id: 'vacation_blackout_dates',
        text: 'Are there blackout dates when the au pair cannot take vacation?',
        inputType: 'textarea-and-date-range-list',
        optional: true,
      },
      {
        id: 'vacation_notice',
        text: 'How much advance notice does the au pair need to give when requesting vacation?',
        inputType: 'single-select',
        options: [
          { value: 'Same day' },
          { value: '1 week' },
          { value: '2 weeks' },
          { value: '1 month' },
          { value: '3 months' },
          { value: 'None' },
        ],
      },
      {
        id: 'bonus_philosophy',
        text: 'Bonus and recognition philosophy',
        subtext: 'Optional — but sets mutual expectations upfront and removes awkwardness later',
        inputType: 'textarea',
        optional: true,
        placeholder: 'e.g. We recognise exceptional effort with a bonus at the end of each quarter...',
      },
    ],
  },
  {
    id: 'parenting',
    title: 'Parenting Style & Philosophy',
    icon: '💬',
    estimatedMinutes: 2,
    description: "These answers anchor the AI's voice in the family brief and feed into the quarterly performance review criteria.",
    questions: [
      {
        id: 'discipline_approach',
        text: 'Discipline approach',
        subtext: 'Select all that apply',
        inputType: 'multi-select',
        options: [
          { value: "Natural consequences — we let children experience the result of their choices" },
          { value: 'Loss of privileges' },
          { value: 'Time-outs or time away to calm down' },
          { value: "Choices-based — we offer two acceptable options rather than issuing directives" },
          { value: "Calm, rational discussion appropriate to the child's age" },
          { value: 'Incentive and reward systems — in collaboration with the au pair' },
          { value: 'Physical discipline is never permitted under any circumstances' },
          { value: 'Raised voices are not part of our approach' },
        ],
      },
      {
        id: 'screen_time_weekdays',
        text: 'Screen time — weekdays',
        subtext: 'How much screen time per day on weekdays?',
        inputType: 'single-select',
        options: [
          { value: 'No screens' },
          { value: 'Up to 30–60 minutes per day' },
          { value: 'Flexible depending on the day' },
        ],
      },
      {
        id: 'screen_time_weekends',
        text: 'Screen time — weekends',
        subtext: 'How much screen time per day on weekends?',
        inputType: 'single-select',
        options: [
          { value: 'No screens' },
          { value: 'Up to 30–60 minutes per day' },
          { value: 'Flexible depending on the day' },
        ],
      },
      {
        id: 'exceptional_childcare',
        text: 'What does exceptional childcare look like to you?',
        subtext: 'This is the most important question in this section. Your answer becomes the foundation for the au pair\'s performance criteria. Be specific.',
        inputType: 'textarea',
        placeholder: 'Describe what outstanding care looks like in your home...',
        starterBullets: [
          'You notice what a child needs before they ask — and act on it without being prompted.',
          'You get down to their level: on the floor, in the game, fully present — not watching from the side.',
          'You bring your own ideas for activities and don\'t wait to be told what to do with the children.',
          'You communicate proactively — a quick message when something goes well, or if something\'s off.',
          'You follow our routines consistently, even when it\'s easier not to (bedtime, screen limits, food rules).',
          'The children feel genuinely safe and happy with you — not just supervised.',
          'You treat this home as your own and the children as people worth investing in, not just a job.',
        ],
      },
      {
        id: 'cultural_values',
        text: 'Are there cultural norms, household values, or important context the au pair should understand?',
        subtext: 'e.g. Religious observance, dietary practices, approach to technology, how conflict is handled in the family',
        inputType: 'textarea',
        optional: true,
        placeholder: "Share anything that would help the au pair understand your family's values and context...",
      },
    ],
  },
];

export const SECTION_IDS = SECTIONS.map(s => s.id);

export function getSectionById(id: string): Section | undefined {
  return SECTIONS.find(s => s.id === id);
}
