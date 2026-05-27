import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, Switch } from 'react-native';
import { useState } from 'react';

interface ChildEntry {
  id: string;
  name: string;
  dateOfBirth: string;
  specialNeeds: boolean;
}

interface Props {
  questionId: string;
  value: Record<string, unknown>[];
  onChange: (value: Record<string, unknown>[]) => void;
}

// For now, StructuredList handles the children_list question specifically.
// Future: generalise via a schema per-questionId.
export function StructuredList({ questionId, value, onChange }: Props) {
  const children = value as ChildEntry[];

  function addChild() {
    const newChild: ChildEntry = {
      id: `child-${Date.now()}`,
      name: '',
      dateOfBirth: '',
      specialNeeds: false,
    };
    onChange([...children, newChild] as Record<string, unknown>[]);
  }

  function updateChild(index: number, updates: Partial<ChildEntry>) {
    const next = children.map((c, i) => (i === index ? { ...c, ...updates } : c));
    onChange(next as Record<string, unknown>[]);
  }

  function removeChild(index: number) {
    onChange(children.filter((_, i) => i !== index) as Record<string, unknown>[]);
  }

  return (
    <View style={styles.container}>
      {children.map((child, i) => (
        <View key={child.id} style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Child {i + 1}</Text>
            <TouchableOpacity onPress={() => removeChild(i)}>
              <Text style={styles.removeText}>Remove</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>Name</Text>
            <TextInput
              style={styles.input}
              value={child.name}
              onChangeText={(name) => updateChild(i, { name })}
              placeholder="Child's name"
              placeholderTextColor="#94a3b8"
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>Date of birth</Text>
            <TextInput
              style={styles.input}
              value={child.dateOfBirth}
              onChangeText={(dateOfBirth) => updateChild(i, { dateOfBirth })}
              placeholder="YYYY-MM-DD"
              placeholderTextColor="#94a3b8"
              keyboardType="numbers-and-punctuation"
            />
          </View>

          <View style={styles.switchRow}>
            <View style={styles.switchLabel}>
              <Text style={styles.fieldLabel}>Additional needs</Text>
              <Text style={styles.switchHint}>
                Enables relevant follow-up questions
              </Text>
            </View>
            <Switch
              value={child.specialNeeds}
              onValueChange={(specialNeeds) => updateChild(i, { specialNeeds })}
              trackColor={{ false: '#e2e8f0', true: '#14b8a6' }}
              thumbColor="#ffffff"
            />
          </View>
        </View>
      ))}

      {children.length < 6 && (
        <TouchableOpacity style={styles.addButton} onPress={addChild}>
          <Text style={styles.addButtonText}>+ Add a child</Text>
        </TouchableOpacity>
      )}

      {children.length === 0 && (
        <Text style={styles.emptyNote}>
          Add each child the au pair will care for. The wizard will tailor follow-up questions to their age.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 12 },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 14,
    borderWidth: 2,
    borderColor: '#e2e8f0',
    padding: 16,
    gap: 12,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardTitle: { fontSize: 15, fontWeight: '700', color: '#1a2744' },
  removeText: { fontSize: 13, color: '#ef4444', fontWeight: '500' },
  field: { gap: 4 },
  fieldLabel: { fontSize: 13, fontWeight: '600', color: '#475569' },
  input: {
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: '#e2e8f0',
    padding: 12,
    fontSize: 15,
    color: '#1a2744',
    backgroundColor: '#f8fafc',
  },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  switchLabel: { flex: 1, gap: 2 },
  switchHint: { fontSize: 12, color: '#94a3b8' },
  addButton: {
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#e2e8f0',
    borderStyle: 'dashed',
    padding: 16,
    alignItems: 'center',
  },
  addButtonText: { fontSize: 15, color: '#64748b', fontWeight: '500' },
  emptyNote: { fontSize: 14, color: '#94a3b8', textAlign: 'center', lineHeight: 20 },
});
