export interface FamilyGoalsData {
  familyName: string;
  childcareStyle: string;
  culturalExchangeGoals: string;
  communicationPreferences: string;
  householdStyle: string;
  primaryLanguage: string;
  additionalLanguages: string[];
  familyIntro: string;
}

export interface ChildGuideData {
  name: string;
  ageDisplay: string;
  dietaryRestrictions: string[];
  allergies: string[];
  medicalNotes: string;
  emotionalRegulationApproach: string;
  preferredActivities: string[];
  schoolName: string;
  schoolPickupTime: string;
  communicationStyle: string;
  napSchedule?: string;
  bottleOrBreastfeedingNotes?: string;
}

export interface ResponsibilitiesData {
  childcareDuties: string[];
  schoolPickupInstructions: string;
  laundryInstructions: string;
  foodPrepResponsibilities: string;
  overnightCareNotes: string;
  seasonalTasks: string[];
  additionalTasks: string[];
}

export interface HousemateExpectationsData {
  mealsPolicy: string;
  kitchenCleanupExpectations: string;
  roomStandards: string;
  commonAreaExpectations: string;
  curfew: string;
  visitorPolicy: string;
  overnightGuestPolicy: string;
  personalSpaceNotes: string;
}

export interface HouseholdInfoData {
  wifiName: string;
  wifiPassword: string;
  appliances: Array<{ name: string; instructions: string }>;
  hvacInstructions: string;
  securitySystem: string;
  emergencyContacts: Array<{ name: string; relationship: string; phone: string }>;
  nearestHospital: string;
  doctorInfo: string;
  importantAddresses: Array<{ label: string; address: string }>;
  safetyNotes: string;
}

export interface ScreenTimeChildData {
  childName: string;
  dailyLimitMinutes: number;
  approvedApps: string[];
  restrictedContent: string;
  deviceRules: string;
}

export interface ScreenTimeData {
  overallPhilosophy: string;
  perChild: ScreenTimeChildData[];
}

export interface DisciplineChildData {
  childName: string;
  specialApproach?: string;
}

export interface DisciplineData {
  overallPhilosophy: string;
  approachSteps: string[];
  hardRules: string[];
  positiveReinforcement: string;
  perChild: DisciplineChildData[];
}

export interface GuideData {
  generatedAt: string;
  householdId: string;
  familyGoals: FamilyGoalsData;
  children: ChildGuideData[];
  responsibilities: ResponsibilitiesData;
  housemateExpectations: HousemateExpectationsData;
  householdInfo: HouseholdInfoData;
  screenTime: ScreenTimeData;
  discipline: DisciplineData;
}
