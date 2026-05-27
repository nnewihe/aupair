import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import type { ScaleConfig } from '@pair/types';

interface Props {
  config: ScaleConfig;
  value: number | null;
  onChange: (value: number) => void;
}

export function ScaleInput({ config, value, onChange }: Props) {
  const steps = Array.from(
    { length: config.max - config.min + 1 },
    (_, i) => config.min + i,
  );

  return (
    <View style={styles.container}>
      <View style={styles.steps}>
        {steps.map((step) => {
          const selected = value === step;
          return (
            <TouchableOpacity
              key={step}
              style={[styles.step, selected && styles.stepSelected]}
              onPress={() => onChange(step)}
            >
              <Text style={[styles.stepText, selected && styles.stepTextSelected]}>
                {step}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <View style={styles.labels}>
        <Text style={styles.labelMin}>{config.minLabel}</Text>
        <Text style={styles.labelMax}>{config.maxLabel}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 12 },
  steps: { flexDirection: 'row', gap: 8, justifyContent: 'center' },
  step: {
    width: 52,
    height: 52,
    borderRadius: 12,
    backgroundColor: '#ffffff',
    borderWidth: 2,
    borderColor: '#e2e8f0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepSelected: { borderColor: '#14b8a6', backgroundColor: '#14b8a6' },
  stepText: { fontSize: 18, fontWeight: '600', color: '#1a2744' },
  stepTextSelected: { color: '#ffffff' },
  labels: { flexDirection: 'row', justifyContent: 'space-between' },
  labelMin: { fontSize: 12, color: '#64748b', flex: 1, maxWidth: '45%' },
  labelMax: { fontSize: 12, color: '#64748b', flex: 1, maxWidth: '45%', textAlign: 'right' },
});
