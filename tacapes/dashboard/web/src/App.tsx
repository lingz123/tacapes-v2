import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';

import { MissionListPage } from '@/pages/MissionList';
import { MissionDetailPage } from '@/pages/MissionDetail';

// Lazy + DEV-only import so the styleguide bundle isn't pulled into prod.
// Vite strips `import.meta.env.DEV === false` branches via dead-code
// elimination, and the lazy import only fires in dev, so the prod build
// never references this module.
const StyleguidePage = import.meta.env.DEV
  ? lazy(() => import('@/pages/Styleguide').then((m) => ({ default: m.StyleguidePage })))
  : null;

/**
 * Top-level router. Sprint 1 ships two pages: the list and the detail.
 * Sprint 2 will add `/missions/:id/tickers/:ticker` as a dedicated drill page.
 *
 * `/styleguide` is a dev-only smoke surface for the component library; it
 * gets removed before Sprint 1 close (Phase 7 of the redesign plan).
 */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<MissionListPage />} />
      <Route path="/missions/:id" element={<MissionDetailPage />} />
      {StyleguidePage && (
        <Route
          path="/styleguide"
          element={
            <Suspense fallback={null}>
              <StyleguidePage />
            </Suspense>
          }
        />
      )}
    </Routes>
  );
}
