import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useWizardStore } from '../../../store/wizard.store';
import { ALL_SECTIONS } from '@pair/question-definitions';
import { useWorkLogs, getWeekStart } from '../../../hooks/useWorkLogs';

const STATUS_COLORS = {
  not_started: '#e2e8f0',
  in_progress: '#fef3c7',
  complete: '#d1fae5',
} as const;

const STATUS_LABELS = {
  not_started: 'Not started',
  in_progress: 'In progress',
  complete: 'Complete',
} as const;

function formatHours(minutes: number): string {
  if (minutes === 0) return '0h logged';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const total = m === 0 ? `${h}h` : `${h}h ${m}m`;
  return `${total} this week`;
}

export default function DashboardScreen() {
  const router = useRouter();
  const { sectionStatus, householdId } = useWizardStore();
  const { summary } = useWorkLogs(householdId, getWeekStart(new Date()));

  const completedCount = Object.values(sectionStatus).filter((s) => s === 'complete').length;
  const totalSections = ALL_SECTIONS.length;
  const progress = completedCount / totalSections;

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.greeting}>Your household guide</Text>
          <Text style={styles.subtitle}>
            Complete all six sections to generate your personalised guide.
          </Text>
        </View>

        <View style={styles.progressCard}>
          <View style={styles.progressHeader}>
            <Text style={styles.progressLabel}>Overall progress</Text>
            <Text style={styles.progressCount}>{completedCount}/{totalSections} sections</Text>
          </View>
          <View style={styles.progressBar}>
            <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
          </View>
        </View>

        {/* Hours Logger card */}
        <TouchableOpacity
          style={styles.hoursCard}
          onPress={() => router.push('/(app)/hours')}
        >
          <View style={styles.hoursCardLeft}>
            <Text style={styles.hoursCardIcon}>⏱</Text>
            <View>
              <Text style={styles.hoursCardTitle}>Hours Logger</Text>
              <Text style={styles.hoursCardSub}>{formatHours(summary.totalMinutes)}</Text>
            </View>
          </View>
          <View style={[styles.hoursLimitBar]}>
            <View
              style={[
                styles.hoursLimitFill,
                {
                  width: `${Math.min(summary.totalMinutes / 2700, 1) * 100}%`,
                  backgroundColor: summary.isOverWeeklyLimit ? '#ef4444' : '#14b8a6',
                },
              ]}
            />
          </View>
          <Text style={styles.hoursCardLimit}>of 45h J-1 limit</Text>
        </TouchableOpacity>

        <View style={styles.sectionList}>
          {ALL_SECTIONS.map((section) => {
            const status = sectionStatus[section.id] ?? 'not_started';
            return (
              <TouchableOpacity
                key={section.id}
                style={styles.sectionCard}
                onPress={() => router.push(`/(app)/wizard/${section.id}`)}
              >
                <View style={styles.sectionLeft}>
                  <Text style={styles.sectionIcon}>{section.icon}</Text>
                  <View>
                    <Text style={styles.sectionTitle}>{section.title}</Text>
                    <Text style={styles.sectionTime}>~{section.estimatedMinutes} min</Text>
                  </View>
                </View>
                <View style={[styles.statusPill, { backgroundColor: STATUS_COLORS[status] }]}>
                  <Text style={styles.statusText}>{STATUS_LABELS[status]}</Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>

        {completedCount === totalSections && (
          <TouchableOpacity
            style={styles.generateButton}
            onPress={() => router.push('/(app)/guide')}
          >
            <Text style={styles.generateButtonText}>Generate Household Guide</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  content: { padding: 20, gap: 20 },
  header: { gap: 4 },
  greeting: { fontSize: 26, fontWeight: '700', color: '#1a2744' },
  subtitle: { fontSize: 15, color: '#64748b', lineHeight: 22 },
  progressCard: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 16,
    gap: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  progressHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  progressLabel: { fontSize: 14, color: '#64748b', fontWeight: '500' },
  progressCount: { fontSize: 14, color: '#1a2744', fontWeight: '600' },
  progressBar: { height: 6, backgroundColor: '#e2e8f0', borderRadius: 3 },
  progressFill: { height: 6, backgroundColor: '#14b8a6', borderRadius: 3 },
  sectionList: { gap: 10 },
  sectionCard: {
    backgroundColor: '#ffffff',
    borderRadius: 14,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  sectionLeft: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  sectionIcon: { fontSize: 24 },
  sectionTitle: { fontSize: 16, fontWeight: '600', color: '#1a2744' },
  sectionTime: { fontSize: 12, color: '#94a3b8', marginTop: 2 },
  statusPill: { borderRadius: 20, paddingHorizontal: 12, paddingVertical: 4 },
  statusText: { fontSize: 12, fontWeight: '500', color: '#475569' },
  generateButton: {
    backgroundColor: '#1a2744',
    borderRadius: 14,
    padding: 18,
    alignItems: 'center',
  },
  generateButtonText: { color: '#ffffff', fontSize: 16, fontWeight: '700' },

  hoursCard: {
    backgroundColor: '#ffffff',
    borderRadius: 14,
    padding: 16,
    gap: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  hoursCardLeft: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  hoursCardIcon: { fontSize: 24 },
  hoursCardTitle: { fontSize: 16, fontWeight: '600', color: '#1a2744' },
  hoursCardSub: { fontSize: 12, color: '#64748b', marginTop: 2 },
  hoursLimitBar: { height: 4, backgroundColor: '#e2e8f0', borderRadius: 2 },
  hoursLimitFill: { height: 4, borderRadius: 2 },
  hoursCardLimit: { fontSize: 11, color: '#94a3b8' },
});
