import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMemo, useRef, useCallback } from 'react';
import type { SectionId } from '@pair/types';
import { ALL_QUESTIONS, ALL_SECTIONS, SECTION_ORDER } from '@pair/question-definitions';
import { computeApplicableQuestions } from '@pair/wizard-engine';
import { useWizardStore } from '../../../../store/wizard.store';
import { QuestionStep } from '../../../../components/wizard/QuestionStep';
import { RepeatContext } from '../../../../components/wizard/RepeatContext';
import { WizardProgressBar } from '../../../../components/wizard/WizardProgressBar';
import { useSaveAnswers } from '../../../../hooks/useSaveAnswers';

export default function WizardStepScreen() {
  const { sectionId, stepIndex: stepIndexParam } = useLocalSearchParams<{
    sectionId: SectionId;
    stepIndex: string;
  }>();
  const stepIndex = parseInt(stepIndexParam ?? '0', 10);
  const router = useRouter();
  const { context, repeatItems, answers, setAnswer } = useWizardStore();
  const { saveAnswer } = useSaveAnswers();

  const questions = useMemo(
    () => computeApplicableQuestions(sectionId, ALL_QUESTIONS, context, repeatItems),
    [sectionId, context, repeatItems],
  );

  const question = questions[stepIndex];
  const isLastStep = stepIndex === questions.length - 1;
  const section = ALL_SECTIONS.find((s) => s.id === sectionId);

  const handleAnswer = useCallback(
    (value: unknown) => {
      if (!question) return;
      setAnswer(question.id, value as never);
      saveAnswer(question.id, value, question.repeatIndex);
    },
    [question, setAnswer, saveAnswer],
  );

  const handleNext = useCallback(() => {
    if (isLastStep) {
      const currentSectionIdx = SECTION_ORDER.indexOf(sectionId);
      const nextSection = SECTION_ORDER[currentSectionIdx + 1];
      if (nextSection) {
        router.push(`/(app)/wizard/${nextSection}`);
      } else {
        router.push('/(app)/wizard/review');
      }
    } else {
      router.push(`/(app)/wizard/${sectionId}/${stepIndex + 1}`);
    }
  }, [isLastStep, sectionId, stepIndex, router]);

  if (!question || !section) {
    return null;
  }

  const currentValue = answers[question.id];
  const canProceed = !question.required || (currentValue !== null && currentValue !== undefined);

  return (
    <SafeAreaView style={styles.container}>
      <WizardProgressBar
        sectionId={sectionId}
        stepIndex={stepIndex}
        totalSteps={questions.length}
        onBack={() => {
          if (stepIndex === 0) router.back();
          else router.push(`/(app)/wizard/${sectionId}/${stepIndex - 1}`);
        }}
      />

      {question.repeatLabel && (
        <RepeatContext name={question.repeatLabel} />
      )}

      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.questionHeader}>
          <Text style={styles.questionText}>{question.text}</Text>
          {question.subtext && (
            <Text style={styles.questionSubtext}>{question.subtext}</Text>
          )}
          {!question.required && (
            <Text style={styles.optionalTag}>Optional</Text>
          )}
        </View>

        <QuestionStep
          question={question}
          value={currentValue}
          onChange={handleAnswer}
        />
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.nextButton, !canProceed && styles.nextButtonDisabled]}
          onPress={handleNext}
          disabled={!canProceed}
        >
          <Text style={styles.nextButtonText}>
            {isLastStep ? 'Complete section →' : 'Next →'}
          </Text>
        </TouchableOpacity>
        {question.required && (
          <TouchableOpacity onPress={handleNext} style={styles.skipLink}>
            <Text style={styles.skipText}>Skip for now</Text>
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  content: { padding: 24, gap: 20, paddingBottom: 40 },
  questionHeader: { gap: 8 },
  questionText: { fontSize: 22, fontWeight: '700', color: '#1a2744', lineHeight: 30 },
  questionSubtext: { fontSize: 14, color: '#64748b', lineHeight: 20 },
  optionalTag: { fontSize: 12, color: '#94a3b8', fontStyle: 'italic' },
  footer: { padding: 24, gap: 8, borderTopWidth: 1, borderTopColor: '#e2e8f0' },
  nextButton: {
    backgroundColor: '#1a2744',
    borderRadius: 14,
    padding: 18,
    alignItems: 'center',
  },
  nextButtonDisabled: { backgroundColor: '#cbd5e1' },
  nextButtonText: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
  skipLink: { alignItems: 'center', paddingVertical: 4 },
  skipText: { color: '#94a3b8', fontSize: 14 },
});
