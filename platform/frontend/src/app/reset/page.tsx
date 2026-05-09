import { Suspense } from 'react';
import { ResetPage } from '@/components/ResetPage';

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ResetPage />
    </Suspense>
  );
}
