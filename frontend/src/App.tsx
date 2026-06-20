import { Navigate, Route, Routes } from 'react-router';
import { Navigation } from './sections/Navigation';
import { ProjectsPage } from './pages/ProjectsPage';
import { ProjectCreatePage } from './pages/ProjectCreatePage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { InboxPage } from './pages/InboxPage';
import { KnowledgePage } from './pages/KnowledgePage';
import { AgentsPage } from './pages/AgentsPage';
import { NetworkPage } from './pages/NetworkPage';
import { BossDashboardPage } from './pages/BossDashboardPage';
import { SettingsPage } from './pages/SettingsPage';

function App() {
  return (
    <div className="min-h-screen bg-[#FAF8F5] text-stone-900 overflow-x-hidden">
      <Navigation />
      <Routes>
        <Route path="/" element={<Navigate to="/projects" replace />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/projects/new" element={<ProjectCreatePage />} />
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/network" element={<NetworkPage />} />
        <Route path="/boss" element={<BossDashboardPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        {/* Legacy redirects */}
        <Route path="/landing" element={<Navigate to="/projects" replace />} />
        <Route path="/designers" element={<Navigate to="/network" replace />} />
        <Route path="/ai-design" element={<Navigate to="/agents" replace />} />
        <Route path="*" element={<Navigate to="/projects" replace />} />
      </Routes>
    </div>
  );
}

export default App;
