import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { useWizardStore } from '../../../store/wizard.store';
import { supabase } from '../../../lib/supabase';
import { ShareCard } from '../../../components/guide/ShareCard';

export default function WizardCompleteScreen() {
  const router = useRouter();
  const { householdId } = useWizardStore();
  const [generating, setGenerating] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  async function generate() {
    if (!householdId) return;
    setGenerating(true);
    try {
      const { data, error } = await supabase.functions.invoke('guide-generate', {
        body: { householdId },
      });
      if (error) throw error;
      setShareUrl(data.shareUrl);
    } catch {
      Alert.alert('Error', 'Could not generate the guide. Please try again.');
    } finally {
      setGenerating(false);
    }
  }

  if (shareUrl) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.content}>
          <Text style={styles.celebrationIcon}>🎉</Text>
          <Text style={styles.title}>Your guide is ready</Text>
          <Text style={styles.subtitle}>
            Share this link with your incoming au pair. They can open it in any browser — no account needed.
          </Text>
          <ShareCard url={shareUrl} onRegenerate={generate} />
          <TouchableOpacity style={styles.doneButton} onPress={() => router.replace('/(app)/dashboard')}>
            <Text style={styles.doneButtonText}>Done →</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.celebrationIcon}>✅</Text>
        <Text style={styles.title}>All sections complete</Text>
        <Text style={styles.subtitle}>
          You've answered everything. Tap below to generate your personalised household guide — a document your au pair can read before they arrive.
        </Text>
        <TouchableOpacity
          style={[styles.generateButton, generating && styles.buttonDisabled]}
          onPress={generate}
          disabled={generating}
        >
          {generating ? (
            <>
              <ActivityIndicator color="#ffffff" />
              <Text style={styles.generateButtonText}>Generating…</Text>
            </>
          ) : (
            <Text style={styles.generateButtonText}>Generate Household Guide →</Text>
          )}
        </TouchableOpacity>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backLink}>← Back to review</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1a2744' },
  content: { flex: 1, padding: 32, justifyContent: 'center', gap: 16 },
  celebrationIcon: { fontSize: 56, textAlign: 'center' },
  title: { fontSize: 30, fontWeight: '800', color: '#ffffff', textAlign: 'center' },
  subtitle: { fontSize: 15, color: '#94a3b8', lineHeight: 24, textAlign: 'center' },
  generateButton: {
    backgroundColor: '#14b8a6',
    borderRadius: 14,
    padding: 20,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 10,
  },
  buttonDisabled: { opacity: 0.7 },
  generateButtonText: { color: '#ffffff', fontSize: 17, fontWeight: '700' },
  doneButton: {
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderRadius: 14,
    padding: 16,
    alignItems: 'center',
  },
  doneButtonText: { color: '#ffffff', fontSize: 15, fontWeight: '600' },
  backLink: { color: '#64748b', fontSize: 14, textAlign: 'center' },
});
