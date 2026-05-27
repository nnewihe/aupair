import { View, Text, StyleSheet } from 'react-native';

interface Props {
  name: string;
}

export function RepeatContext({ name }: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.label}>Now answering for</Text>
      <Text style={styles.name}>{name}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 20,
    paddingVertical: 8,
    backgroundColor: '#f0fdf4',
    borderBottomWidth: 1,
    borderBottomColor: '#d1fae5',
  },
  label: { fontSize: 13, color: '#64748b' },
  name: { fontSize: 13, fontWeight: '700', color: '#065f46' },
});
