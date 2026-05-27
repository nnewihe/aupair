import { TextInput, StyleSheet } from 'react-native';

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function FreeTextInput({ value, onChange, placeholder }: Props) {
  return (
    <TextInput
      style={styles.input}
      value={value}
      onChangeText={onChange}
      placeholder={placeholder ?? 'Type your answer here…'}
      placeholderTextColor="#94a3b8"
      multiline
      textAlignVertical="top"
      scrollEnabled={false}
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
    fontSize: 15,
    color: '#1a2744',
    lineHeight: 22,
    minHeight: 120,
  },
});
