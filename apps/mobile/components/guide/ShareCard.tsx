import { View, Text, TouchableOpacity, StyleSheet, Alert, Share, Platform } from 'react-native';
import * as Linking from 'expo-linking';
import * as Clipboard from 'expo-clipboard';

interface Props {
  url: string;
  onRegenerate?: () => void;
}

export function ShareCard({ url, onRegenerate }: Props) {
  async function copyLink() {
    await Clipboard.setStringAsync(url);
    Alert.alert('Copied!', 'The guide link has been copied to your clipboard.');
  }

  async function openInBrowser() {
    const canOpen = await Linking.canOpenURL(url);
    if (canOpen) {
      await Linking.openURL(url);
    } else {
      Alert.alert('Cannot open URL', url);
    }
  }

  async function shareLink() {
    await Share.share({
      message: `Here's our household guide: ${url}`,
      url: Platform.OS === 'ios' ? url : undefined,
    });
  }

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>Guide ready</Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>✓ Live</Text>
        </View>
      </View>

      <Text style={styles.description}>
        Your au pair can open this link in any browser — no app or account required.
      </Text>

      <View style={styles.urlBox}>
        <Text style={styles.url} numberOfLines={1}>{url}</Text>
      </View>

      <View style={styles.actions}>
        <TouchableOpacity style={styles.actionButton} onPress={shareLink}>
          <Text style={styles.actionIcon}>📤</Text>
          <Text style={styles.actionLabel}>Share</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.actionButton} onPress={copyLink}>
          <Text style={styles.actionIcon}>📋</Text>
          <Text style={styles.actionLabel}>Copy link</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.actionButton} onPress={openInBrowser}>
          <Text style={styles.actionIcon}>🌐</Text>
          <Text style={styles.actionLabel}>Open</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.divider} />

      <Text style={styles.tokenNote}>
        This link is private to your household. You can regenerate it at any time to revoke access for a departing au pair.
      </Text>

      {onRegenerate && (
        <TouchableOpacity style={styles.regenButton} onPress={onRegenerate}>
          <Text style={styles.regenText}>Regenerate guide</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 20,
    gap: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
  },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { fontSize: 18, fontWeight: '700', color: '#1a2744' },
  badge: { backgroundColor: '#d1fae5', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 4 },
  badgeText: { color: '#065f46', fontSize: 12, fontWeight: '600' },
  description: { fontSize: 14, color: '#64748b', lineHeight: 20 },
  urlBox: {
    backgroundColor: '#f1f5f9',
    borderRadius: 8,
    padding: 12,
  },
  url: { fontSize: 13, color: '#475569', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  actions: { flexDirection: 'row', gap: 8 },
  actionButton: {
    flex: 1,
    backgroundColor: '#f8fafc',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    padding: 12,
    alignItems: 'center',
    gap: 4,
  },
  actionIcon: { fontSize: 20 },
  actionLabel: { fontSize: 12, color: '#475569', fontWeight: '500' },
  divider: { height: 1, backgroundColor: '#f1f5f9' },
  tokenNote: { fontSize: 12, color: '#94a3b8', lineHeight: 18 },
  regenButton: { alignItems: 'center', paddingVertical: 4 },
  regenText: { fontSize: 13, color: '#14b8a6', fontWeight: '600' },
});
