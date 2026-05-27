import { View, Text, TextInput, TouchableOpacity, StyleSheet } from 'react-native';

interface Props {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
}

export function MultiTextInput({ value, onChange, placeholder }: Props) {
  function updateItem(index: number, text: string) {
    const next = [...value];
    next[index] = text;
    onChange(next);
  }

  function removeItem(index: number) {
    onChange(value.filter((_, i) => i !== index));
  }

  function addItem() {
    onChange([...value, '']);
  }

  return (
    <View style={styles.container}>
      {value.map((item, i) => (
        <View key={i} style={styles.row}>
          <TextInput
            style={styles.input}
            value={item}
            onChangeText={(text) => updateItem(i, text)}
            placeholder={placeholder ?? 'Add an item…'}
            placeholderTextColor="#94a3b8"
            returnKeyType="next"
          />
          <TouchableOpacity onPress={() => removeItem(i)} style={styles.remove}>
            <Text style={styles.removeText}>✕</Text>
          </TouchableOpacity>
        </View>
      ))}
      <TouchableOpacity style={styles.addButton} onPress={addItem}>
        <Text style={styles.addButtonText}>+ Add another</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 8 },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  input: {
    flex: 1,
    backgroundColor: '#ffffff',
    borderRadius: 10,
    borderWidth: 2,
    borderColor: '#e2e8f0',
    padding: 14,
    fontSize: 15,
    color: '#1a2744',
  },
  remove: { padding: 8 },
  removeText: { color: '#94a3b8', fontSize: 16 },
  addButton: {
    borderRadius: 10,
    borderWidth: 2,
    borderColor: '#e2e8f0',
    borderStyle: 'dashed',
    padding: 14,
    alignItems: 'center',
  },
  addButtonText: { color: '#64748b', fontSize: 14, fontWeight: '500' },
});
