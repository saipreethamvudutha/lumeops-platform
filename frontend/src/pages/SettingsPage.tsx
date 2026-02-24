import { useState } from 'react';
import { Save, Key } from 'lucide-react';
import { setApiKey, getApiKey, clearApiKey } from '../api/client';

export function SettingsPage() {
  const [apiKeyInput, setApiKeyInput] = useState(getApiKey() || '');
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    if (apiKeyInput.trim()) {
      setApiKey(apiKeyInput.trim());
    } else {
      clearApiKey();
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-800">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">Configure your LumeOps dashboard</p>
      </div>

      <div className="max-w-2xl space-y-6">
        {/* API Key Configuration */}
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="flex items-center gap-3 mb-4">
            <Key className="h-5 w-5 text-blue-600" />
            <h3 className="font-semibold text-slate-800">API Key</h3>
          </div>
          <p className="mb-4 text-sm text-slate-500">
            Enter your LumeOps API key to authenticate dashboard requests.
            Your key is stored locally in your browser.
          </p>
          <div className="flex gap-3">
            <input
              type="password"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder="lum_sk_..."
              className="flex-1 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <button
              onClick={handleSave}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              <Save className="h-4 w-4" />
              {saved ? 'Saved' : 'Save'}
            </button>
          </div>
        </div>

        {/* About */}
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <h3 className="mb-2 font-semibold text-slate-800">About LumeOps</h3>
          <div className="space-y-2 text-sm text-slate-500">
            <p>HIPAA-compliant Healthcare AI Observability Platform</p>
            <p>Version 0.1.0 (MVP)</p>
            <p>Automatic PII redaction, secure storage, audit trail, and compliance reporting.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
