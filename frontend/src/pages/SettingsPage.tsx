import { useState } from 'react';
import { Save, Key, CheckCircle, Shield, Activity, Lock, Database, Zap } from 'lucide-react';
import { motion } from 'framer-motion';
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
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">Configure your LumeOps dashboard</p>
      </div>

      <div className="max-w-2xl space-y-6">
        {/* API Key Configuration */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="glass-card p-6"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500/15 to-violet-500/10">
              <Key className="h-4 w-4 text-cyan-400" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-200">API Key</h3>
              <p className="text-[11px] text-slate-500">Authentication for dashboard requests</p>
            </div>
          </div>
          <p className="mb-5 text-sm text-slate-500 leading-relaxed">
            Enter your LumeOps API key to authenticate dashboard requests.
            Your key is stored locally in your browser and never sent to third parties.
          </p>
          <div className="flex gap-3">
            <input
              type="password"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder="lum_sk_..."
              className="flex-1 rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none transition-colors"
              style={{
                background: 'rgba(30, 41, 59, 0.5)',
                border: '1px solid var(--border-default)',
              }}
              onFocus={(e) => { e.target.style.borderColor = 'rgba(6, 182, 212, 0.4)'; }}
              onBlur={(e) => { e.target.style.borderColor = 'var(--border-default)'; }}
            />
            <button
              onClick={handleSave}
              className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
              style={{ background: saved ? 'rgba(16, 185, 129, 0.3)' : 'var(--gradient-brand)' }}
            >
              {saved ? <CheckCircle className="h-4 w-4 text-emerald-300" /> : <Save className="h-4 w-4" />}
              {saved ? 'Saved!' : 'Save'}
            </button>
          </div>
        </motion.div>

        {/* About */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className="glass-card p-6"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500/15 to-violet-500/10">
              <Activity className="h-4 w-4 text-cyan-400" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-200">About LumeOps</h3>
              <p className="text-[11px] text-slate-500">Version 0.1.0 (MVP)</p>
            </div>
          </div>
          <p className="text-sm text-slate-400 leading-relaxed mb-5">
            HIPAA-compliant Healthcare AI Observability Platform. Monitor, secure, and audit
            your ML inference pipelines with enterprise-grade tooling.
          </p>

          {/* Feature grid */}
          <div className="grid grid-cols-2 gap-3">
            {[
              { icon: Shield, label: 'PII Redaction', desc: 'Automatic PHI detection' },
              { icon: Lock, label: 'Encryption', desc: 'AES-128-CBC at rest' },
              { icon: Database, label: 'Audit Trail', desc: 'Tamper-proof logging' },
              { icon: Zap, label: 'Real-time', desc: 'WebSocket streaming' },
            ].map(({ icon: Icon, label, desc }) => (
              <div key={label} className="rounded-xl p-3 flex items-start gap-2.5"
                style={{ background: 'rgba(30, 41, 59, 0.3)', border: '1px solid var(--border-subtle)' }}>
                <Icon className="h-4 w-4 text-cyan-400/70 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-medium text-slate-300">{label}</p>
                  <p className="text-[10px] text-slate-500">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
