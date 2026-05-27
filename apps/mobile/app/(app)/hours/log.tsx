import { useState, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useWizardStore } from '../../../store/wizard.store';
import { useWorkLogs, getWeekStart, parseMinutes } from '../../../hooks/useWorkLogs';

// ── Helpers ──────────────────────────────────────────────────

function toDateString(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function formatDisplayDate(date: Date): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (toDateString(date) === toDateString(today)) return 'Today';
  if (toDateString(date) === toDateString(yesterday)) return 'Yesterday';
  return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function formatMinutes(minutes: number): string {
  if (minutes <= 0) return '';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} hr` : `${h} hr ${m} min`;
}

function toHM(hour: number, minute: number): string {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

// ── StepControl ──────────────────────────────────────────────

function StepControl({
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  const increment = () => {
    const next = value + step;
    onChange(next > max ? min : next);
  };
  const decrement = () => {
    const prev = value - step;
    // Snap down to nearest valid multiple when wrapping
    onChange(prev < min ? max - ((max - min) % step) : prev);
  };

  return (
    <View style={styles.stepControl}>
      <TouchableOpacity onPress={increment} style={styles.stepBtn} hitSlop={8}>
        <Text style={styles.stepArrow}>▲</Text>
      </TouchableOpacity>
      <Text style={styles.stepValue}>{String(value).padStart(2, '0')}</Text>
      <TouchableOpacity onPress={decrement} style={styles.stepBtn} hitSlop={8}>
        <Text style={styles.stepArrow}>▼</Text>
      </TouchableOpacity>
    </View>
  );
}

// ── TimePicker ───────────────────────────────────────────────

function TimePicker({
  label,
  hour,
  minute,
  onHourChange,
  onMinuteChange,
}: {
  label: string;
  hour: number;
  minute: number;
  onHourChange: (h: number) => void;
  onMinuteChange: (m: number) => void;
}) {
  return (
    <View style={styles.timePickerRow}>
      <Text style={styles.timePickerLabel}>{label}</Text>
      <View style={styles.timePickerControls}>
        <StepControl value={hour} min={0} max={23} onChange={onHourChange} />
        <Text style={styles.colon}>:</Text>
        <StepControl value={minute} min={0} max={55} step={5} onChange={onMinuteChange} />
      </View>
    </View>
  );
}

// ── DateSelector ─────────────────────────────────────────────

function DateSelector({ date, onChange }: { date: Date; onChange: (d: Date) => void }) {
  const prev = () => {
    const d = new Date(date);
    d.setDate(d.getDate() - 1);
    onChange(d);
  };
  const next = () => {
    const d = new Date(date);
    d.setDate(d.getDate() + 1);
    // Don't allow future dates
    if (d <= new Date()) onChange(d);
  };
  const isToday = toDateString(date) === toDateString(new Date());

  return (
    <View style={styles.dateSelector}>
      <TouchableOpacity onPress={prev} style={styles.dateArrow}>
        <Text style={styles.dateArrowText}>‹</Text>
      </TouchableOpacity>
      <Text style={styles.dateText}>{formatDisplayDate(date)}</Text>
      <TouchableOpacity onPress={next} style={[styles.dateArrow, isToday && styles.dateArrowDisabled]} disabled={isToday}>
        <Text style={[styles.dateArrowText, isToday && styles.dateArrowTextDisabled]}>›</Text>
      </TouchableOpacity>
    </View>
  );
}

// ── Screen ───────────────────────────────────────────────────

export default function LogHoursScreen() {
  const router = useRouter();
  const { householdId } = useWizardStore();

  const [date, setDate] = useState(new Date());
  const [startHour, setStartHour] = useState(9);
  const [startMinute, setStartMinute] = useState(0);
  const [endHour, setEndHour] = useState(17);
  const [endMinute, setEndMinute] = useState(0);
  const [notes, setNotes] = useState('');

  const weekStart = getWeekStart(date);
  const { addLog } = useWorkLogs(householdId, weekStart);

  const startTime = toHM(startHour, startMinute);
  const endTime = toHM(endHour, endMinute);
  const durationMinutes = parseMinutes(startTime, endTime);
  const isValid = durationMinutes > 0;

  const handleSave = useCallback(() => {
    if (!isValid) {
      Alert.alert('Invalid time range', 'End time must be after start time.');
      return;
    }
    if (!householdId) return;

    addLog.mutate(
      {
        logDate: toDateString(date),
        startTime,
        endTime,
        notes: notes.trim() || undefined,
      },
      {
        onSuccess: () => router.back(),
        onError: () => Alert.alert('Error', 'Could not save entry. Please try again.'),
      },
    );
  }, [addLog, date, startTime, endTime, notes, householdId, isValid, router]);

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.cancelBtn}>
          <Text style={styles.cancelText}>Cancel</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Log Hours</Text>
        <View style={styles.cancelBtn} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Date */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>Date</Text>
          <DateSelector date={date} onChange={setDate} />
        </View>

        <View style={styles.divider} />

        {/* Time pickers */}
        <View style={styles.section}>
          <TimePicker
            label="Start"
            hour={startHour}
            minute={startMinute}
            onHourChange={setStartHour}
            onMinuteChange={setStartMinute}
          />
          <TimePicker
            label="End"
            hour={endHour}
            minute={endMinute}
            onHourChange={setEndHour}
            onMinuteChange={setEndMinute}
          />
        </View>

        {/* Duration preview */}
        <View style={styles.durationRow}>
          {isValid ? (
            <Text style={styles.durationText}>
              Duration: <Text style={styles.durationHighlight}>{formatMinutes(durationMinutes)}</Text>
            </Text>
          ) : (
            <Text style={styles.durationError}>End time must be after start time</Text>
          )}
        </View>

        <View style={styles.divider} />

        {/* Notes */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>Notes</Text>
          <TextInput
            style={styles.notesInput}
            placeholder="Optional — e.g. school run, playdate, evening babysit"
            placeholderTextColor="#94a3b8"
            value={notes}
            onChangeText={setNotes}
            multiline
            returnKeyType="done"
          />
        </View>

        {/* Save */}
        <TouchableOpacity
          style={[styles.saveButton, (!isValid || addLog.isPending) && styles.saveButtonDisabled]}
          onPress={handleSave}
          disabled={!isValid || addLog.isPending}
        >
          <Text style={styles.saveButtonText}>
            {addLog.isPending ? 'Saving…' : 'Save Entry'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#ffffff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  cancelBtn: { width: 64 },
  cancelText: { fontSize: 15, color: '#64748b' },
  title: { fontSize: 17, fontWeight: '700', color: '#1a2744' },

  content: { padding: 20, gap: 0, paddingBottom: 40 },

  section: {
    backgroundColor: '#ffffff',
    borderRadius: 14,
    padding: 16,
    gap: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  sectionLabel: { fontSize: 12, fontWeight: '600', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.8 },

  divider: { height: 12 },

  // Date selector
  dateSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dateArrow: { padding: 8 },
  dateArrowDisabled: { opacity: 0.3 },
  dateArrowText: { fontSize: 24, color: '#1a2744', fontWeight: '600' },
  dateArrowTextDisabled: { color: '#94a3b8' },
  dateText: { fontSize: 18, fontWeight: '600', color: '#1a2744' },

  // Time picker
  timePickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  timePickerLabel: { fontSize: 16, fontWeight: '600', color: '#1a2744', width: 48 },
  timePickerControls: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  colon: { fontSize: 28, fontWeight: '700', color: '#1a2744', marginHorizontal: 4 },

  // Step control
  stepControl: { alignItems: 'center', gap: 4 },
  stepBtn: { padding: 6 },
  stepArrow: { fontSize: 14, color: '#64748b' },
  stepValue: { fontSize: 32, fontWeight: '700', color: '#1a2744', width: 56, textAlign: 'center' },

  // Duration
  durationRow: { paddingHorizontal: 4, paddingVertical: 8, alignItems: 'center' },
  durationText: { fontSize: 14, color: '#64748b' },
  durationHighlight: { fontWeight: '700', color: '#14b8a6' },
  durationError: { fontSize: 13, color: '#ef4444' },

  // Notes
  notesInput: {
    fontSize: 15,
    color: '#1a2744',
    minHeight: 80,
    textAlignVertical: 'top',
    lineHeight: 22,
  },

  // Save button
  saveButton: {
    marginTop: 24,
    backgroundColor: '#1a2744',
    borderRadius: 14,
    padding: 18,
    alignItems: 'center',
  },
  saveButtonDisabled: { backgroundColor: '#94a3b8' },
  saveButtonText: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
});
