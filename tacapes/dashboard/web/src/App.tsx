import { Route, Routes } from 'react-router-dom';

import { MissionListPage } from '@/pages/MissionList';
import { MissionDetailPage } from '@/pages/MissionDetail';

/**
 * Top-level router. Sprint 1 ships two pages: the list and the detail.
 * Sprint 2 will add `/missions/:id/tickers/:ticker` as a dedicated drill page.
 */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<MissionListPage />} />
      <Route path="/missions/:id" element={<MissionDetailPage />} />
    </Routes>
  );
}
