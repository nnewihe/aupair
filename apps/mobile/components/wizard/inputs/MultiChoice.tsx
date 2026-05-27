import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import type { QuestionOption } from '@pair/types';

interface Props {
  options: QuestionOption[];
  value: string[];
  onChange: (value: string[]) => void;
}

export function MultiChoice({ options, value, onChange }: Props) {
  function toggle(optionValue: string) {
    if (value.includes(optionValue)) {
      onChange(value.filter((v) => v !== optionValue));
    } else {
      onChange([...value, optionValue]);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>Select all that apply</Text>
      {options.map((option) => {
        const selected = value.includes(option.value);
        return (
          <TouchableOpacity
            key={option.value}
            style={[styles.option, selected && styles.optionSelected]}
            onPress={() => toggle(option.value)}
            activeOpacity={0.7}
          >
            <View style={[styles.checkbox, selected && styles.checkboxSelected]}>
              {selected && <Text style={styles.checkmark}>✓</Text>}
            </View>
            <View style={styles.optionText}>
              <Text style={[styles.label, selected && styles.labelSelected]}>
                {option.label}
              </Text>
              {option.description && (
                <Text style={styles.description}>{option.description}</Text>
              )}
            </View>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 8 },
  hint: { fontSize: 13, color: '#94a3b8', marginBottom: 4 },
  option: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    borderWidth: 2,
    borderColor: '#e2e8f0',
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  optionSelected: { borderColor: '#14b8a6', backgroundColor: '#f0fdf9' },
  checkbox: {
    width: 20,
    height: 20,
    borderRadius: 4,
    borderWidth: 2,
    borderColor: '#cbd5e1',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    marginTop: 1,
  },
  checkboxSelected: { borderColor: '#14b8a6', backgroundColor: '#14b8a6' },
  checkmark: { color: '#ffffff', fontSize: 11, fontWeight: '700' },
  optionText: { flex: 1, gap: 2 },
  label: { fontSize: 15, fontWeight: '500', color: '#1a2744' },
  labelSelected: { color: '#0f766e', fontWeight: '600' },
  description: { fontSize: 13, color: '#64748b', lineHeight: 18 },
});
