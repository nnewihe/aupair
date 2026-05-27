export interface Household {
  id: string;
  familyName: string;
  state: string;
  createdAt: string;
  updatedAt: string;
  shareToken: string | null;
  shareTokenCreatedAt: string | null;
  wizardCompletedAt: string | null;
}

export interface ChildProfile {
  id: string;
  householdId: string;
  name: string;
  dateOfBirth: string;
  ageMonths: number;
  specialNeeds: boolean;
  specialNeedsDescription?: string;
  dietaryRestrictions: string[];
  allergies: string[];
  medicalNotes?: string;
  schoolName?: string;
  schoolPickupTime?: string;
  communicationNotes?: string;
  emotionalRegulationNotes?: string;
  preferredActivities: string[];
  sortOrder: number;
}

export interface WizardAnswer {
  id: string;
  householdId: string;
  questionId: string;
  repeatIndex: number;
  answerJson: unknown;
  updatedAt: string;
}

export interface ShareToken {
  householdId: string;
  token: string;
  createdAt: string;
  revokedAt: string | null;
}
