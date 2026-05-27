import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity,
  KeyboardAvoidingView, Platform, Alert, StyleSheet,
} from 'react-native';
import { supabase } from '../../lib/supabase';

export default function LoginScreen() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function sendMagicLink() {
    if (!email.trim()) return;
    setLoading(true);
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim().toLowerCase(),
      options: { emailRedirectTo: 'pair://auth/callback' },
    });
    setLoading(false);
    if (error) {
      Alert.alert('Error', error.message);
    } else {
      setSent(true);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.inner}>
        <Text style={styles.logo}>Pair</Text>
        <Text style={styles.tagline}>The au pair relationship platform</Text>

        {sent ? (
          <View style={styles.sentBox}>
            <Text style={styles.sentTitle}>Check your email</Text>
            <Text style={styles.sentBody}>
              We sent a sign-in link to {email}. Tap it to open the app.
            </Text>
          </View>
        ) : (
          <>
            <Text style={styles.label}>Email address</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="send"
              onSubmitEditing={sendMagicLink}
            />
            <TouchableOpacity
              style={[styles.button, loading && styles.buttonDisabled]}
              onPress={sendMagicLink}
              disabled={loading || !email.trim()}
            >
              <Text style={styles.buttonText}>
                {loading ? 'Sending…' : 'Send sign-in link'}
              </Text>
            </TouchableOpacity>
            <Text style={styles.footnote}>
              No password needed. We'll email you a secure link.
            </Text>
          </>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1a2744' },
  inner: { flex: 1, justifyContent: 'center', paddingHorizontal: 32 },
  logo: { fontSize: 48, fontWeight: '700', color: '#ffffff', letterSpacing: -1, marginBottom: 4 },
  tagline: { fontSize: 16, color: '#94a3b8', marginBottom: 48 },
  label: { fontSize: 14, color: '#cbd5e1', marginBottom: 8 },
  input: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: '#1a2744',
    marginBottom: 16,
  },
  button: {
    backgroundColor: '#14b8a6',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginBottom: 16,
  },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: '#ffffff', fontSize: 16, fontWeight: '600' },
  footnote: { fontSize: 13, color: '#64748b', textAlign: 'center' },
  sentBox: { alignItems: 'center', gap: 12 },
  sentTitle: { fontSize: 22, fontWeight: '700', color: '#ffffff' },
  sentBody: { fontSize: 15, color: '#94a3b8', textAlign: 'center', lineHeight: 22 },
});
