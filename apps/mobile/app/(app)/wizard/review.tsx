import { ScrollView, View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useWizardStore } from '../../../store/wizard.store';
import { ALL_SECTIONS, SECTION_ORDER } from '@pair/question-definitions';

export default function WizardReviewScreen() {
  const router = useRouter();
  const { sectionStatus } = useWizardStore();

  const allComplete = SECTION_ORDER.every((id) => sectionStatus[id] === 'complete');

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Review &amp; Generate</Text>
        <Text style={styles.subtitle}>
          Check your sections below, then generate your household guide.
        </Text>

        {ALL_SECTIONS.map((section) => {
          const status = sectionStatus[section.id] ?? 'not_started';
          const isComplete = status === 'complete';
          return (
            <TouchableOpacity
              key={section.id}
              style={[styles.row, isComplete && styles.rowComplete]}
              onPress={() => router.push(`/(app)/wizard/${section.id}`)}
            >
              <Text style={styles.rowIcon}>{section.icon}</Text>
              <View style={styles.rowContent}>
                <Text style={styles.rowTitle}>{section.title}</Text>
                <Text style={[styles.rowStatus, isComplete && styles.rowStatusComplete]}>
                  {isComplete ? '✓ Complete' : status === 'in_progress' ? 'In progress' : 'Not started'}
                </Text>
              </View>
              <Text style={styles.rowChevron}>›</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.generateButton, !allComplete && styles.generateButtonDisabled]}
          onPress={() => router.push('/(app)/wizard/complete')}
          disabled={!allComplete}
        >
          <Text style={styles.generateButtonText}>
            {allComplete ? 'Generate Household Guide →' : 'Complete all sections to generate'}
          </Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  content: { padding: 20, gap: 10 },
  title: { fontSize: 26, fontWeight: '700', color: '#1a2744', marginBottom: 4 },
  subtitle: { fontSize: 15, color: '#64748b', lineHeight: 22, marginBottom: 8 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    gap: 12,
    borderWidth: 2,
    borderColor: '#e2e8f0',
  },
  rowComplete: { borderColor: '#14b8a6' },
  rowIcon: { fontSize: 22 },
  rowContent: { flex: 1 },
  rowTitle: { fontSize: 15, fontWeight: '600', color: '#1a2744' },
  rowStatus: { fontSize: 12, color: '#94a3b8', marginTop: 2 },
  rowStatusComplete: { color: '#14b8a6', fontWeight: '600' },
  rowChevron: { fontSize: 20, color: '#94a3b8' },
  footer: { padding: 20, borderTopWidth: 1, borderTopColor: '#e2e8f0' },
  generateButton: { backgroundColor: '#1a2744', borderRadius: 14, padding: 18, alignItems: 'center' },
  generateButtonDisabled: { backgroundColor: '#94a3b8' },
  generateButtonText: { color: '#ffffff', fontSize: 15, fontWeight: '700', textAlign: 'center' },
});
