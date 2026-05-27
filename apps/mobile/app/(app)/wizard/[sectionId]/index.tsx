import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ALL_SECTIONS } from '@pair/question-definitions';
import type { SectionId } from '@pair/types';

export default function SectionIntroScreen() {
  const { sectionId } = useLocalSearchParams<{ sectionId: SectionId }>();
  const router = useRouter();

  const section = ALL_SECTIONS.find((s) => s.id === sectionId);
  if (!section) return null;

  const sectionIndex = ALL_SECTIONS.findIndex((s) => s.id === sectionId);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <TouchableOpacity style={styles.back} onPress={() => router.back()}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>

        <View style={styles.badge}>
          <Text style={styles.badgeText}>
            {sectionIndex + 1} of {ALL_SECTIONS.length}
          </Text>
        </View>

        <Text style={styles.icon}>{section.icon}</Text>
        <Text style={styles.title}>{section.title}</Text>
        <Text style={styles.description}>{section.description}</Text>

        <View style={styles.metaRow}>
          <View style={styles.metaPill}>
            <Text style={styles.metaText}>~{section.estimatedMinutes} minutes</Text>
          </View>
          <View style={styles.metaPill}>
            <Text style={styles.metaText}>Auto-saved</Text>
          </View>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={styles.startButton}
          onPress={() => router.push(`/(app)/wizard/${sectionId}/0`)}
        >
          <Text style={styles.startButtonText}>Start this section →</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1a2744' },
  content: { padding: 24, gap: 16, flexGrow: 1 },
  back: { alignSelf: 'flex-start', paddingVertical: 4 },
  backText: { color: '#94a3b8', fontSize: 15 },
  badge: {
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 4,
    alignSelf: 'flex-start',
  },
  badgeText: { color: '#94a3b8', fontSize: 12, fontWeight: '500' },
  icon: { fontSize: 56, marginTop: 16 },
  title: { fontSize: 32, fontWeight: '700', color: '#ffffff', lineHeight: 38 },
  description: { fontSize: 16, color: '#94a3b8', lineHeight: 24 },
  metaRow: { flexDirection: 'row', gap: 8, marginTop: 8 },
  metaPill: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  metaText: { color: '#94a3b8', fontSize: 13, fontWeight: '500' },
  footer: { padding: 24 },
  startButton: {
    backgroundColor: '#14b8a6',
    borderRadius: 14,
    padding: 18,
    alignItems: 'center',
  },
  startButtonText: { color: '#ffffff', fontSize: 17, fontWeight: '700' },
});
