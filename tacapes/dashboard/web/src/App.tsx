import { Route, Routes } from 'react-router-dom';

import { MissionListPage } from '@/pages/MissionList';
import { MissionDetailPage } from '@/pages/MissionDetail';
import { StyleguidePage } from '@/pages/Styleguide';

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
      <Route path="/styleguide" element={<StyleguidePage />} />
    </Routes>
  );
}
