import { TextInput, StyleSheet } from 'react-native';

interface Props {
  value: number | null;
  onChange: (value: number | null) => void;
  placeholder?: string;
}

export function NumberInput({ value, onChange, placeholder }: Props) {
  return (
    <TextInput
      style={styles.input}
      value={value !== null ? String(value) : ''}
      onChangeText={(text) => {
        const parsed = parseInt(text, 10);
        onChange(isNaN(parsed) ? null : parsed);
      }}
      placeholder={placeholder ?? '0'}
      placeholderTextColor="#94a3b8"
      keyboardType="number-pad"
    />
  );
}

const styles = StyleSheet.create({
  input: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#e2e8f0',
    padding: 16,
    fontSize: 22,
    color: '#1a2744',
    fontWeight: '600',
    textAlign: 'center',
  },
});
