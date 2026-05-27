import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ALL_SECTIONS, SECTION_ORDER } from '@pair/question-definitions';
import type { SectionId } from '@pair/types';
import { useWizardStore } from '../../store/wizard.store';

interface Props {
  sectionId: SectionId;
  stepIndex: number;
  totalSteps: number;
  onBack: () => void;
}

export function WizardProgressBar({ sectionId, stepIndex, totalSteps, onBack }: Props) {
  const { isSaving } = useWizardStore();
  const sectionIndex = SECTION_ORDER.indexOf(sectionId);
  const section = ALL_SECTIONS.find((s) => s.id === sectionId);

  // Overall progress: (sections done + fraction of current section)
  const sectionFraction = totalSteps > 0 ? (stepIndex + 1) / totalSteps : 0;
  const totalSections = SECTION_ORDER.length;
  const overallProgress = (sectionIndex + sectionFraction) / totalSections;

  return (
    <View style={styles.container}>
      <View style={styles.topRow}>
        <TouchableOpacity onPress={onBack} hitSlop={12}>
          <Text style={styles.back}>←</Text>
        </TouchableOpacity>
        <View style={styles.sectionInfo}>
          <Text style={styles.sectionTitle}>{section?.title}</Text>
          <Text style={styles.stepCount}>{stepIndex + 1} / {totalSteps}</Text>
        </View>
        {isSaving ? (
          <Text style={styles.saving}>Saving…</Text>
        ) : (
          <Text style={styles.saved}>✓ Saved</Text>
        )}
      </View>

      {/* Section progress dots */}
      <View style={styles.dots}>
        {SECTION_ORDER.map((id, i) => (
          <View
            key={id}
            style={[
              styles.dot,
              i < sectionIndex && styles.dotComplete,
              i === sectionIndex && styles.dotActive,
            ]}
          />
        ))}
      </View>

      {/* Step progress within section */}
      <View style={styles.stepBar}>
        <View style={[styles.stepFill, { width: `${sectionFraction * 100}%` }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#ffffff',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
    gap: 10,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  back: { fontSize: 20, color: '#1a2744', width: 32 },
  sectionInfo: { alignItems: 'center', flex: 1 },
  sectionTitle: { fontSize: 13, fontWeight: '600', color: '#1a2744' },
  stepCount: { fontSize: 11, color: '#94a3b8', marginTop: 1 },
  saving: { fontSize: 12, color: '#f59e0b', width: 52, textAlign: 'right' },
  saved: { fontSize: 12, color: '#10b981', width: 52, textAlign: 'right' },
  dots: { flexDirection: 'row', gap: 4, justifyContent: 'center' },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#e2e8f0' },
  dotActive: { backgroundColor: '#1a2744', width: 18 },
  dotComplete: { backgroundColor: '#14b8a6' },
  stepBar: { height: 3, backgroundColor: '#e2e8f0', borderRadius: 2 },
  stepFill: { height: 3, backgroundColor: '#14b8a6', borderRadius: 2 },
});
