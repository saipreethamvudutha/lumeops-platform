import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { DashboardPage } from './pages/DashboardPage';
import { InferencesPage } from './pages/InferencesPage';
import { CompliancePage } from './pages/CompliancePage';
import { ApiKeysPage } from './pages/ApiKeysPage';
import { WebhooksPage } from './pages/WebhooksPage';
import { SettingsPage } from './pages/SettingsPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/inferences" element={<InferencesPage />} />
          <Route path="/compliance" element={<CompliancePage />} />
          <Route path="/api-keys" element={<ApiKeysPage />} />
          <Route path="/webhooks" element={<WebhooksPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
