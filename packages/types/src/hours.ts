export interface WorkLog {
  id: string;
  householdId: string;
  logDate: string; // 'YYYY-MM-DD'
  startTime: string; // 'HH:MM' 24-hour
  endTime: string; // 'HH:MM' 24-hour
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

export interface DaySummary {
  date: string; // 'YYYY-MM-DD'
  entries: WorkLog[];
  totalMinutes: number;
  isOverDailyLimit: boolean; // > 600 min (10h J-1 limit)
}

export interface WeekSummary {
  weekStart: string; // Monday 'YYYY-MM-DD'
  days: DaySummary[];
  totalMinutes: number;
  isOverWeeklyLimit: boolean; // > 2700 min (45h J-1 limit)
}

export type NewWorkLogEntry = Pick<WorkLog, 'logDate' | 'startTime' | 'endTime' | 'notes'>;
