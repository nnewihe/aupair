import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useState } from 'react';
import * as Linking from 'expo-linking';
import { useWizardStore } from '../../../store/wizard.store';
import { supabase } from '../../../lib/supabase';
import { ShareCard } from '../../../components/guide/ShareCard';

export default function GuideScreen() {
  const { householdId } = useWizardStore();
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  async function generateGuide() {
    if (!householdId) return;
    setGenerating(true);
    try {
      const { data, error } = await supabase.functions.invoke('guide-generate', {
        body: { householdId },
      });
      if (error) throw error;
      setShareUrl(data.shareUrl);
    } catch (err) {
      Alert.alert('Error', 'Could not generate guide. Please try again.');
    } finally {
      setGenerating(false);
    }
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Your Household Guide</Text>
        <Text style={styles.subtitle}>
          A personalised guide for your au pair — ready to share, print, or download.
        </Text>

        {shareUrl ? (
          <ShareCard url={shareUrl} onRegenerate={generateGuide} />
        ) : (
          <View style={styles.emptyState}>
            <Text style={styles.emptyIcon}>📄</Text>
            <Text style={styles.emptyTitle}>No guide yet</Text>
            <Text style={styles.emptyBody}>
              Complete all six wizard sections to generate your household guide.
            </Text>
            <TouchableOpacity
              style={[styles.generateButton, generating && styles.buttonDisabled]}
              onPress={generateGuide}
              disabled={generating}
            >
              {generating ? (
                <ActivityIndicator color="#ffffff" />
              ) : (
                <Text style={styles.generateButtonText}>Generate Guide</Text>
              )}
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  content: { padding: 24, gap: 20, flexGrow: 1 },
  title: { fontSize: 26, fontWeight: '700', color: '#1a2744' },
  subtitle: { fontSize: 15, color: '#64748b', lineHeight: 22 },
  emptyState: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, marginTop: 48 },
  emptyIcon: { fontSize: 56 },
  emptyTitle: { fontSize: 20, fontWeight: '700', color: '#1a2744' },
  emptyBody: { fontSize: 15, color: '#64748b', textAlign: 'center', lineHeight: 22 },
  generateButton: {
    backgroundColor: '#1a2744',
    borderRadius: 14,
    padding: 18,
    alignItems: 'center',
    width: '100%',
    marginTop: 8,
  },
  buttonDisabled: { opacity: 0.6 },
  generateButtonText: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
});
