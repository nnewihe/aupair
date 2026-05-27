import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import type { QuestionOption } from '@pair/types';

interface Props {
  options: QuestionOption[];
  value: string | null;
  onChange: (value: string) => void;
}

export function SingleChoice({ options, value, onChange }: Props) {
  return (
    <View style={styles.container}>
      {options.map((option) => {
        const selected = value === option.value;
        return (
          <TouchableOpacity
            key={option.value}
            style={[styles.option, selected && styles.optionSelected]}
            onPress={() => onChange(option.value)}
            activeOpacity={0.7}
          >
            <View style={styles.optionLeft}>
              <View style={[styles.radio, selected && styles.radioSelected]}>
                {selected && <View style={styles.radioDot} />}
              </View>
              <View style={styles.optionText}>
                <Text style={[styles.label, selected && styles.labelSelected]}>
                  {option.label}
                </Text>
                {option.description && (
                  <Text style={styles.description}>{option.description}</Text>
                )}
              </View>
            </View>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 8 },
  option: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    borderWidth: 2,
    borderColor: '#e2e8f0',
  },
  optionSelected: { borderColor: '#14b8a6', backgroundColor: '#f0fdf9' },
  optionLeft: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  radio: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: '#cbd5e1',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
    flexShrink: 0,
  },
  radioSelected: { borderColor: '#14b8a6' },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#14b8a6' },
  optionText: { flex: 1, gap: 2 },
  label: { fontSize: 15, fontWeight: '600', color: '#1a2744' },
  labelSelected: { color: '#0f766e' },
  description: { fontSize: 13, color: '#64748b', lineHeight: 18 },
});
