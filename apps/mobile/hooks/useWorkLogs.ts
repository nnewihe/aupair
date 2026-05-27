import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '../lib/supabase';
import type { WorkLog, DaySummary, WeekSummary, NewWorkLogEntry } from '@pair/types';

export function parseMinutes(startTime: string, endTime: string): number {
  const [sh, sm] = startTime.split(':').map(Number);
  const [eh, em] = endTime.split(':').map(Number);
  return eh * 60 + em - (sh * 60 + sm);
}

export function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr + 'T00:00:00');
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function getWeekStart(date: Date): string {
  const d = new Date(date);
  const day = d.getDay();
  // Adjust to Monday (day 1); Sunday (0) goes back 6 days
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

function buildWeekSummary(logs: WorkLog[], weekStart: string): WeekSummary {
  const days: DaySummary[] = Array.from({ length: 7 }, (_, i) => {
    const date = addDays(weekStart, i);
    const entries = logs.filter((l) => l.logDate === date);
    const totalMinutes = entries.reduce(
      (sum, e) => sum + parseMinutes(e.startTime, e.endTime),
      0,
    );
    return { date, entries, totalMinutes, isOverDailyLimit: totalMinutes > 600 };
  });

  const totalMinutes = days.reduce((sum, d) => sum + d.totalMinutes, 0);
  return { weekStart, days, totalMinutes, isOverWeeklyLimit: totalMinutes > 2700 };
}

export function useWorkLogs(householdId: string | null, weekStart: string) {
  const weekEnd = addDays(weekStart, 6);
  const queryClient = useQueryClient();
  const queryKey = ['work_logs', householdId, weekStart] as const;

  const { data: logs = [], isLoading } = useQuery({
    queryKey,
    enabled: !!householdId,
    queryFn: async () => {
      const { data, error } = await supabase
        .from('work_logs')
        .select('*')
        .eq('household_id', householdId!)
        .gte('log_date', weekStart)
        .lte('log_date', weekEnd)
        .order('log_date', { ascending: true })
        .order('start_time', { ascending: true });

      if (error) throw error;

      return (data ?? []).map(
        (row): WorkLog => ({
          id: row.id,
          householdId: row.household_id,
          logDate: row.log_date,
          startTime: (row.start_time as string).slice(0, 5),
          endTime: (row.end_time as string).slice(0, 5),
          notes: row.notes ?? undefined,
          createdAt: row.created_at,
          updatedAt: row.updated_at,
        }),
      );
    },
  });

  const addLog = useMutation({
    mutationFn: async (entry: NewWorkLogEntry) => {
      const { error } = await supabase.from('work_logs').insert({
        household_id: householdId!,
        log_date: entry.logDate,
        start_time: entry.startTime,
        end_time: entry.endTime,
        notes: entry.notes ?? null,
      });
      if (error) throw error;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const deleteLog = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from('work_logs').delete().eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const summary = buildWeekSummary(logs, weekStart);

  return { logs, isLoading, summary, addLog, deleteLog };
}
