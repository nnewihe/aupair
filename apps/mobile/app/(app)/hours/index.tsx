import { useState, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  Alert,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useWizardStore } from '../../../store/wizard.store';
import { useWorkLogs, getWeekStart, addDays, parseMinutes } from '../../../hooks/useWorkLogs';
import type { DaySummary } from '@pair/types';

const DAILY_LIMIT_MIN = 600; // 10h
const WEEKLY_LIMIT_MIN = 2700; // 45h

const DAY_ABBR = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function formatMinutes(minutes: number): string {
  if (minutes === 0) return '0h';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function formatWeekRange(weekStart: string): string {
  const start = new Date(weekStart + 'T00:00:00');
  const end = new Date(weekStart + 'T00:00:00');
  end.setDate(end.getDate() + 6);
  const startStr = start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const endStr = end.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  return `${startStr} – ${endStr}`;
}

function complianceColor(minutes: number, limitMin: number, warnThreshold = 0.78): string {
  if (minutes > limitMin) return '#ef4444'; // over limit
  if (minutes > limitMin * warnThreshold) return '#f59e0b'; // approaching
  return '#14b8a6'; // on track
}

function DaySection({
  day,
  onDelete,
}: {
  day: DaySummary;
  onDelete: (id: string) => void;
}) {
  const hasEntries = day.entries.length > 0;
  const dotColor = !hasEntries
    ? '#e2e8f0'
    : complianceColor(day.totalMinutes, DAILY_LIMIT_MIN, 0.8);

  return (
    <View style={styles.daySection}>
      <View style={styles.dayHeader}>
        <View style={styles.dayLeft}>
          <View style={[styles.dayDot, { backgroundColor: dotColor }]} />
          <Text style={styles.dayName}>{formatDate(day.date)}</Text>
        </View>
        <Text style={[styles.dayTotal, { color: hasEntries ? '#1a2744' : '#cbd5e1' }]}>
          {formatMinutes(day.totalMinutes)}
        </Text>
      </View>

      {hasEntries && (
        <View style={styles.entriesList}>
          {day.entries.map((entry) => {
            const mins = parseMinutes(entry.startTime, entry.endTime);
            return (
              <View key={entry.id} style={styles.entryRow}>
                <View style={styles.entryLeft}>
                  <Text style={styles.entryTime}>
                    {entry.startTime} – {entry.endTime}
                  </Text>
                  <Text style={styles.entryDuration}>{formatMinutes(mins)}</Text>
                  {entry.notes ? (
                    <Text style={styles.entryNotes} numberOfLines={1}>
                      {entry.notes}
                    </Text>
                  ) : null}
                </View>
                <TouchableOpacity
                  style={styles.deleteBtn}
                  onPress={() =>
                    Alert.alert('Delete entry', 'Remove this log entry?', [
                      { text: 'Cancel', style: 'cancel' },
                      { text: 'Delete', style: 'destructive', onPress: () => onDelete(entry.id) },
                    ])
                  }
                >
                  <Text style={styles.deleteBtnText}>✕</Text>
                </TouchableOpacity>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}

export default function HoursScreen() {
  const router = useRouter();
  const { householdId } = useWizardStore();

  const todayWeekStart = getWeekStart(new Date());
  const [weekStart, setWeekStart] = useState(todayWeekStart);

  const { summary, isLoading, deleteLog } = useWorkLogs(householdId, weekStart);

  const prevWeek = useCallback(() => setWeekStart((w) => addDays(w, -7)), []);
  const nextWeek = useCallback(() => setWeekStart((w) => addDays(w, 7)), []);
  const isCurrentWeek = weekStart === todayWeekStart;

  const weeklyColor = complianceColor(summary.totalMinutes, WEEKLY_LIMIT_MIN);
  const weeklyPct = Math.min(summary.totalMinutes / WEEKLY_LIMIT_MIN, 1);

  const handleDelete = useCallback(
    (id: string) => deleteLog.mutate(id),
    [deleteLog],
  );

  return (
    <SafeAreaView style={styles.container}>
      {/* Week selector */}
      <View style={styles.weekNav}>
        <TouchableOpacity onPress={prevWeek} style={styles.navBtn}>
          <Text style={styles.navArrow}>‹</Text>
        </TouchableOpacity>
        <View style={styles.weekLabel}>
          <Text style={styles.weekRange}>{formatWeekRange(weekStart)}</Text>
          {isCurrentWeek && <Text style={styles.thisWeekBadge}>This week</Text>}
        </View>
        <TouchableOpacity onPress={nextWeek} style={styles.navBtn}>
          <Text style={styles.navArrow}>›</Text>
        </TouchableOpacity>
      </View>

      {isLoading ? (
        <ActivityIndicator style={styles.loader} color="#14b8a6" />
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          {/* Weekly summary card */}
          <View style={styles.summaryCard}>
            <View style={styles.summaryTop}>
              <View>
                <Text style={styles.summaryHours}>{formatMinutes(summary.totalMinutes)}</Text>
                <Text style={styles.summaryLimit}>of 45h weekly limit</Text>
              </View>
              {summary.isOverWeeklyLimit && (
                <View style={styles.overLimitBadge}>
                  <Text style={styles.overLimitText}>Over limit</Text>
                </View>
              )}
            </View>
            <View style={styles.weeklyBar}>
              <View
                style={[
                  styles.weeklyBarFill,
                  { width: `${weeklyPct * 100}%`, backgroundColor: weeklyColor },
                ]}
              />
            </View>
            <View style={styles.dayDots}>
              {summary.days.map((day, i) => (
                <View key={day.date} style={styles.dayDotCol}>
                  <View
                    style={[
                      styles.miniDot,
                      {
                        backgroundColor:
                          day.totalMinutes > 0
                            ? complianceColor(day.totalMinutes, DAILY_LIMIT_MIN, 0.8)
                            : '#e2e8f0',
                      },
                    ]}
                  />
                  <Text style={styles.miniDayLabel}>{DAY_ABBR[i]}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Daily breakdown */}
          <View style={styles.daysList}>
            {summary.days.map((day) => (
              <DaySection key={day.date} day={day} onDelete={handleDelete} />
            ))}
          </View>
        </ScrollView>
      )}

      {/* Log Hours FAB */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => router.push('/(app)/hours/log')}
      >
        <Text style={styles.fabText}>+ Log Hours</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  loader: { flex: 1 },

  weekNav: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#ffffff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  navBtn: { padding: 8 },
  navArrow: { fontSize: 22, color: '#1a2744', fontWeight: '600' },
  weekLabel: { flex: 1, alignItems: 'center', gap: 2 },
  weekRange: { fontSize: 15, fontWeight: '600', color: '#1a2744' },
  thisWeekBadge: { fontSize: 11, color: '#14b8a6', fontWeight: '500' },

  content: { padding: 16, gap: 16, paddingBottom: 100 },

  summaryCard: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 18,
    gap: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  summaryTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  summaryHours: { fontSize: 28, fontWeight: '700', color: '#1a2744' },
  summaryLimit: { fontSize: 13, color: '#64748b', marginTop: 2 },
  overLimitBadge: {
    backgroundColor: '#fee2e2',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  overLimitText: { fontSize: 12, fontWeight: '600', color: '#dc2626' },
  weeklyBar: { height: 6, backgroundColor: '#e2e8f0', borderRadius: 3 },
  weeklyBarFill: { height: 6, borderRadius: 3 },
  dayDots: { flexDirection: 'row', justifyContent: 'space-between' },
  dayDotCol: { alignItems: 'center', gap: 4 },
  miniDot: { width: 8, height: 8, borderRadius: 4 },
  miniDayLabel: { fontSize: 10, color: '#94a3b8', fontWeight: '500' },

  daysList: { gap: 8 },

  daySection: {
    backgroundColor: '#ffffff',
    borderRadius: 14,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  dayHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 14,
  },
  dayLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  dayDot: { width: 8, height: 8, borderRadius: 4 },
  dayName: { fontSize: 14, fontWeight: '600', color: '#1a2744' },
  dayTotal: { fontSize: 14, fontWeight: '600' },

  entriesList: {
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  entryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#f8fafc',
  },
  entryLeft: { flex: 1, gap: 2 },
  entryTime: { fontSize: 14, color: '#1a2744', fontWeight: '500' },
  entryDuration: { fontSize: 12, color: '#64748b' },
  entryNotes: { fontSize: 12, color: '#94a3b8', fontStyle: 'italic' },
  deleteBtn: { padding: 8 },
  deleteBtnText: { fontSize: 14, color: '#94a3b8' },

  fab: {
    position: 'absolute',
    bottom: 24,
    left: 20,
    right: 20,
    backgroundColor: '#1a2744',
    borderRadius: 14,
    padding: 18,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 6,
  },
  fabText: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
});
