import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { useWizardStore } from '../../../store/wizard.store';

export default function WizardIndex() {
  const router = useRouter();
  const { currentSectionId, currentStepIndex } = useWizardStore();

  useEffect(() => {
    router.replace(`/(app)/wizard/${currentSectionId}/${currentStepIndex}`);
  }, []);

  return null;
}
