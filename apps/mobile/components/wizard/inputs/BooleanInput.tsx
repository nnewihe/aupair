import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';

interface Props {
  value: boolean | null;
  onChange: (value: boolean) => void;
}

export function BooleanInput({ value, onChange }: Props) {
  return (
    <View style={styles.container}>
      {([true, false] as const).map((opt) => {
        const selected = value === opt;
        return (
          <TouchableOpacity
            key={String(opt)}
            style={[styles.option, selected && styles.optionSelected]}
            onPress={() => onChange(opt)}
          >
            <Text style={[styles.label, selected && styles.labelSelected]}>
              {opt ? 'Yes' : 'No'}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: 'row', gap: 12 },
  option: {
    flex: 1,
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#e2e8f0',
  },
  optionSelected: { borderColor: '#14b8a6', backgroundColor: '#f0fdf9' },
  label: { fontSize: 18, fontWeight: '600', color: '#1a2744' },
  labelSelected: { color: '#0f766e' },
});
