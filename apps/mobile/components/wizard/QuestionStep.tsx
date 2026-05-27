import type { ResolvedQuestion, AnswerValue } from '@pair/types';
import { SingleChoice } from './inputs/SingleChoice';
import { MultiChoice } from './inputs/MultiChoice';
import { ScaleInput } from './inputs/ScaleInput';
import { FreeTextInput } from './inputs/FreeTextInput';
import { NumberInput } from './inputs/NumberInput';
import { BooleanInput } from './inputs/BooleanInput';
import { StructuredList } from './inputs/StructuredList';
import { MultiTextInput } from './inputs/MultiTextInput';

interface Props {
  question: ResolvedQuestion;
  value: AnswerValue;
  onChange: (value: AnswerValue) => void;
}

export function QuestionStep({ question, value, onChange }: Props) {
  switch (question.answerType) {
    case 'single_choice':
      return (
        <SingleChoice
          options={question.options ?? []}
          value={value as string | null}
          onChange={onChange}
        />
      );
    case 'multi_choice':
      return (
        <MultiChoice
          options={question.options ?? []}
          value={(value as string[]) ?? []}
          onChange={onChange}
        />
      );
    case 'scale':
      return (
        <ScaleInput
          config={question.scaleConfig!}
          value={value as number | null}
          onChange={onChange}
        />
      );
    case 'free_text':
      return (
        <FreeTextInput
          value={(value as string) ?? ''}
          onChange={onChange}
          placeholder={question.placeholder}
        />
      );
    case 'number':
      return (
        <NumberInput
          value={value as number | null}
          onChange={onChange}
          placeholder={question.placeholder}
        />
      );
    case 'boolean':
      return (
        <BooleanInput
          value={value as boolean | null}
          onChange={onChange}
        />
      );
    case 'structured_list':
      return (
        <StructuredList
          questionId={question.id}
          value={(value as Record<string, unknown>[]) ?? []}
          onChange={onChange}
        />
      );
    case 'multi_text':
      return (
        <MultiTextInput
          value={(value as string[]) ?? []}
          onChange={onChange}
          placeholder={question.placeholder}
        />
      );
    default:
      return null;
  }
}
