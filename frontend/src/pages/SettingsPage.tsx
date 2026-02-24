import { useState, useEffect, useCallback } from 'react';
import {
  Settings, Save, Key, CheckCircle, Shield, Activity, Lock, Database, Zap,
  Building2, Mail, Phone, Globe, Clock, Bell, Trash2, Eye, RefreshCw,
  AlertTriangle, Archive, Calendar, Server,
} from 'lucide-react';
import { motion } from 'framer-motion';
import {
  setApiKey, getApiKey, clearApiKey,
  fetchTenantSettings, updateTenantSettings,
  updateRetentionPolicy, previewRetentionCleanup, executeRetentionCleanup,
} from '../api/client';
import type { TenantSettings, RetentionCleanupResult } from '../types/api';

// ── Plan badge color helper ──────────────────────────────────────

const PLAN_COLORS: Record<string, { bg: string; text: string }> = {
  starter: { bg: 'bg-slate-500/20', text: 'text-slate-300' },
  professional: { bg: 'bg-cyan-500/20', text: 'text-cyan-400' },
  enterprise: { bg: 'bg-violet-500/20', text: 'text-violet-400' },
};

function timeAgo(iso: string | null): string {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ══════════════════════════════════════════════════════════════════
//  SETTINGS PAGE
// ══════════════════════════════════════════════════════════════════

export function SettingsPage() {
  // API key (local storage)
  const [apiKeyInput, setApiKeyInput] = useState(getApiKey() || '');
  const [keySaved, setKeySaved] = useState(false);

  // Tenant settings (server)
  const [tenant, setTenant] = useState<TenantSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Retention
  const [retSaving, setRetSaving] = useState(false);
  const [retSaved, setRetSaved] = useState(false);
  const [preview, setPreview] = useState<RetentionCleanupResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [cleanResult, setCleanResult] = useState<RetentionCleanupResult | null>(null);

  // Editable fields
  const [name, setName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [timezone, setTimezone] = useState('UTC');
  const [alertEmail, setAlertEmail] = useState('');

  // Retention fields
  const [infDays, setInfDays] = useState<string>('');
  const [alertDays, setAlertDays] = useState<string>('');
  const [webhookDays, setWebhookDays] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchTenantSettings();
      setTenant(data);
      setName(data.name || '');
      setContactEmail(data.contact_email || '');
      setContactPhone(data.contact_phone || '');
      setTimezone(data.timezone || 'UTC');
      setAlertEmail(data.alert_email || '');
      setInfDays(data.retention.inference_retention_days?.toString() || '');
      setAlertDays(data.retention.alert_retention_days?.toString() || '');
      setWebhookDays(data.retention.webhook_delivery_retention_days?.toString() || '');
    } catch {
      /* API key not set or invalid */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSaveKey = () => {
    if (apiKeyInput.trim()) {
      setApiKey(apiKeyInput.trim());
    } else {
      clearApiKey();
    }
    setKeySaved(true);
    setTimeout(() => { setKeySaved(false); load(); }, 1500);
  };

  const handleSaveSettings = async () => {
    if (!tenant) return;
    setSaving(true);
    try {
      const updates: Record<string, string> = {};
      if (name !== tenant.name) updates.name = name;
      if (contactEmail !== (tenant.contact_email || '')) updates.contact_email = contactEmail || '';
      if (contactPhone !== (tenant.contact_phone || '')) updates.contact_phone = contactPhone || '';
      if (timezone !== tenant.timezone) updates.timezone = timezone;
      if (alertEmail !== (tenant.alert_email || '')) updates.alert_email = alertEmail || '';

      if (Object.keys(updates).length > 0) {
        const updated = await updateTenantSettings(updates);
        setTenant(updated);
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  };

  const handleSaveRetention = async () => {
    setRetSaving(true);
    try {
      const policy: Record<string, number | null> = {};
      policy.inference_retention_days = infDays ? parseInt(infDays) : null;
      policy.alert_retention_days = alertDays ? parseInt(alertDays) : null;
      policy.webhook_delivery_retention_days = webhookDays ? parseInt(webhookDays) : null;

      await updateRetentionPolicy(policy);
      setRetSaved(true);
      setTimeout(() => setRetSaved(false), 2500);
      load();
    } catch {
      /* ignore */
    } finally {
      setRetSaving(false);
    }
  };

  const handlePreview = async () => {
    setPreviewing(true);
    try {
      const result = await previewRetentionCleanup();
      setPreview(result);
    } catch {
      /* ignore */
    } finally {
      setPreviewing(false);
    }
  };

  const handleCleanup = async () => {
    setCleaning(true);
    try {
      const result = await executeRetentionCleanup();
      setCleanResult(result);
      setPreview(null);
      load();
    } catch {
      /* ignore */
    } finally {
      setCleaning(false);
    }
  };

  const pc = PLAN_COLORS[tenant?.plan || 'starter'] || PLAN_COLORS.starter;

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-100 tracking-tight flex items-center gap-3">
          <Settings className="w-7 h-7 text-cyan-400" />
          Settings
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Manage your tenant configuration, data retention, and notification preferences
        </p>
      </div>

      <div className="space-y-6">

        {/* ── API Key Configuration ───────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
          className="glass-card p-6">
          <SectionHeader icon={Key} label="API Key" sub="Authentication for dashboard requests" />
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
              style={{ background: 'rgba(30, 41, 59, 0.5)', border: '1px solid var(--border-default)' }}
              onFocus={(e) => { e.target.style.borderColor = 'rgba(6, 182, 212, 0.4)'; }}
              onBlur={(e) => { e.target.style.borderColor = 'var(--border-default)'; }}
            />
            <button onClick={handleSaveKey}
              className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
              style={{ background: keySaved ? 'rgba(16, 185, 129, 0.3)' : 'var(--gradient-brand)' }}>
              {keySaved ? <CheckCircle className="h-4 w-4 text-emerald-300" /> : <Save className="h-4 w-4" />}
              {keySaved ? 'Saved!' : 'Save'}
            </button>
          </div>
        </motion.div>

        {/* ── Tenant Info (from server) ───────────────────────────── */}
        {tenant && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.05 }}
            className="glass-card p-6">
            <div className="flex items-center justify-between mb-5">
              <SectionHeader icon={Building2} label="Organization" sub="Tenant identity and contact information" />
              <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${pc.bg} ${pc.text}`}>
                {tenant.plan}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <InputField label="Organization Name" icon={Building2} value={name} onChange={setName} />
              <InputField label="Contact Email" icon={Mail} value={contactEmail} onChange={setContactEmail} placeholder="admin@hospital.org" />
              <InputField label="Contact Phone" icon={Phone} value={contactPhone} onChange={setContactPhone} placeholder="+1 (555) 123-4567" />
              <InputField label="Alert Email" icon={Bell} value={alertEmail} onChange={setAlertEmail} placeholder="alerts@hospital.org" />
              <div>
                <label className="text-xs text-slate-400 mb-1.5 flex items-center gap-1.5 font-medium">
                  <Globe className="w-3 h-3" /> Timezone
                </label>
                <select value={timezone} onChange={(e) => setTimezone(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-sm text-slate-200 bg-transparent focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                  style={{ background: 'rgba(30, 41, 59, 0.5)', border: '1px solid var(--border-default)' }}>
                  {['UTC', 'US/Eastern', 'US/Central', 'US/Mountain', 'US/Pacific',
                    'Europe/London', 'Europe/Berlin', 'Asia/Tokyo', 'Asia/Kolkata',
                    'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
                  ].map(tz => <option key={tz} value={tz}>{tz}</option>)}
                </select>
              </div>
              <div className="flex items-end">
                <InfoBox icon={Server} label="Data Residency" value={tenant.data_residency} />
              </div>
            </div>

            <div className="flex justify-end mt-5">
              <button onClick={handleSaveSettings} disabled={saving}
                className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
                style={{ background: saved ? 'rgba(16, 185, 129, 0.3)' : 'var(--gradient-brand)' }}>
                {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle className="w-4 h-4 text-emerald-300" /> : <Save className="w-4 h-4" />}
                {saved ? 'Saved!' : 'Save Settings'}
              </button>
            </div>
          </motion.div>
        )}

        {/* ── Security Info (read-only) ──────────────────────────── */}
        {tenant && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.1 }}
            className="glass-card p-6">
            <SectionHeader icon={Lock} label="Security" sub="Encryption and key rotation status" />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <InfoBox icon={Lock} label="Encryption Key Version" value={`v${tenant.encryption_key_version}`} />
              <InfoBox icon={Calendar} label="Last Key Rotation" value={timeAgo(tenant.last_key_rotation)} />
              <InfoBox icon={RefreshCw} label="Total Rotations" value={tenant.key_rotation_count.toString()} />
              <InfoBox icon={Shield} label="Tenant Status" value={tenant.is_active ? 'Active' : 'Inactive'}
                color={tenant.is_active ? 'text-emerald-400' : 'text-red-400'} />
            </div>
          </motion.div>
        )}

        {/* ── Data Retention Policy ──────────────────────────────── */}
        {tenant && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.15 }}
            className="glass-card p-6">
            <SectionHeader icon={Archive} label="Data Retention" sub="Configure how long to keep records" />
            <p className="text-xs text-slate-500 mb-5 flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
              HIPAA requires minimum 6-year retention for medical records. Inference data minimum is 365 days.
              Set to blank (empty) to keep data forever.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <RetentionField label="Inference Records" value={infDays} onChange={setInfDays}
                hint="Min: 365 days (HIPAA)" min={365} />
              <RetentionField label="Resolved Alerts" value={alertDays} onChange={setAlertDays}
                hint="Min: 30 days" min={30} />
              <RetentionField label="Webhook Deliveries" value={webhookDays} onChange={setWebhookDays}
                hint="Min: 7 days" min={7} />
            </div>

            {/* Metadata row */}
            <div className="flex items-center justify-between mt-4 text-xs text-slate-500">
              <div className="flex items-center gap-4">
                <span>Policy updated: {timeAgo(tenant.retention.policy_updated_at)}</span>
                <span>Last cleanup: {timeAgo(tenant.retention.last_cleanup_at)}</span>
                <span className="text-slate-600">Auto-cleanup runs daily at 2:00 AM UTC</span>
              </div>
            </div>

            <div className="flex items-center gap-3 mt-5">
              <button onClick={handleSaveRetention} disabled={retSaving}
                className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
                style={{ background: retSaved ? 'rgba(16, 185, 129, 0.3)' : 'var(--gradient-brand)' }}>
                {retSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : retSaved ? <CheckCircle className="w-4 h-4 text-emerald-300" /> : <Save className="w-4 h-4" />}
                {retSaved ? 'Saved!' : 'Save Policy'}
              </button>

              <button onClick={handlePreview} disabled={previewing}
                className="flex items-center gap-2 glass-card-static px-4 py-2.5 text-sm font-medium text-slate-300 hover:text-cyan-400 rounded-xl transition-colors">
                {previewing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
                Preview Cleanup
              </button>

              {preview && preview.total_deleted > 0 && (
                <button onClick={handleCleanup} disabled={cleaning}
                  className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium text-red-400 hover:text-red-300 transition-colors"
                  style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                  {cleaning ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                  Delete {preview.total_deleted.toLocaleString()} Records
                </button>
              )}
            </div>

            {/* Preview / Result panels */}
            {preview && (
              <div className="mt-4 p-4 rounded-xl" style={{ background: 'rgba(30, 41, 59, 0.5)', border: '1px solid var(--border-subtle)' }}>
                <p className="text-xs font-semibold text-slate-300 mb-2 flex items-center gap-2">
                  <Eye className="w-3.5 h-3.5 text-cyan-400" /> Cleanup Preview (Dry Run)
                </p>
                <CleanupSummary data={preview} />
              </div>
            )}

            {cleanResult && (
              <div className="mt-4 p-4 rounded-xl" style={{ background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                <p className="text-xs font-semibold text-emerald-400 mb-2 flex items-center gap-2">
                  <CheckCircle className="w-3.5 h-3.5" /> Cleanup Completed
                </p>
                <CleanupSummary data={cleanResult} />
              </div>
            )}
          </motion.div>
        )}

        {/* ── About ──────────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.2 }}
          className="glass-card p-6">
          <SectionHeader icon={Activity} label="About LumeOps" sub="Version 0.1.0" />
          <p className="text-sm text-slate-400 leading-relaxed mb-5">
            HIPAA-compliant Healthcare AI Observability Platform. Monitor, secure, and audit
            your ML inference pipelines with enterprise-grade tooling.
          </p>
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

        {/* Loading placeholder */}
        {loading && !tenant && (
          <div className="glass-card p-12 text-center">
            <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin mx-auto mb-3" />
            <p className="text-slate-400">Loading settings...</p>
            <p className="text-xs text-slate-600 mt-1">Make sure your API key is configured above</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Reusable Components ──────────────────────────────────────────

function SectionHeader({ icon: Icon, label, sub }: {
  icon: React.ComponentType<{ className?: string }>; label: string; sub: string;
}) {
  return (
    <div className="flex items-center gap-3 mb-2">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500/15 to-violet-500/10">
        <Icon className="h-4 w-4 text-cyan-400" />
      </div>
      <div>
        <h3 className="font-semibold text-slate-200">{label}</h3>
        <p className="text-[11px] text-slate-500">{sub}</p>
      </div>
    </div>
  );
}

function InputField({ label, icon: Icon, value, onChange, placeholder }: {
  label: string; icon: React.ComponentType<{ className?: string }>;
  value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="text-xs text-slate-400 mb-1.5 flex items-center gap-1.5 font-medium">
        <Icon className="w-3 h-3" /> {label}
      </label>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-colors"
        style={{ background: 'rgba(30, 41, 59, 0.5)', border: '1px solid var(--border-default)' }} />
    </div>
  );
}

function InfoBox({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ className?: string }>; label: string; value: string; color?: string;
}) {
  return (
    <div className="rounded-xl p-3" style={{ background: 'rgba(30, 41, 59, 0.3)', border: '1px solid var(--border-subtle)' }}>
      <div className="text-[10px] text-slate-500 flex items-center gap-1 mb-1">
        <Icon className="w-3 h-3" /> {label}
      </div>
      <div className={`text-sm font-mono font-medium ${color || 'text-white'}`}>{value}</div>
    </div>
  );
}

function RetentionField({ label, value, onChange, hint, min }: {
  label: string; value: string; onChange: (v: string) => void; hint: string; min: number;
}) {
  const numVal = parseInt(value);
  const isInvalid = value !== '' && (isNaN(numVal) || numVal < min);

  return (
    <div>
      <label className="text-xs text-slate-400 mb-1.5 flex items-center gap-1.5 font-medium">
        <Clock className="w-3 h-3" /> {label}
      </label>
      <div className="relative">
        <input type="number" value={value} onChange={(e) => onChange(e.target.value)}
          placeholder="Forever"
          min={min}
          className={`w-full rounded-lg px-3 py-2 pr-14 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 transition-colors ${
            isInvalid ? 'focus:ring-red-500/50' : 'focus:ring-cyan-500/50'
          }`}
          style={{ background: 'rgba(30, 41, 59, 0.5)', border: `1px solid ${isInvalid ? 'rgba(239, 68, 68, 0.4)' : 'var(--border-default)'}` }} />
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500">days</span>
      </div>
      <p className={`text-[10px] mt-1 ${isInvalid ? 'text-red-400' : 'text-slate-600'}`}>{hint}</p>
    </div>
  );
}

function CleanupSummary({ data }: { data: RetentionCleanupResult }) {
  return (
    <div className="grid grid-cols-4 gap-3 text-sm">
      <div>
        <div className="text-[10px] text-slate-500">Inferences</div>
        <div className="font-mono text-white">{data.inferences_deleted.toLocaleString()}</div>
      </div>
      <div>
        <div className="text-[10px] text-slate-500">Alerts</div>
        <div className="font-mono text-white">{data.alerts_deleted.toLocaleString()}</div>
      </div>
      <div>
        <div className="text-[10px] text-slate-500">Webhook Logs</div>
        <div className="font-mono text-white">{data.webhook_deliveries_deleted.toLocaleString()}</div>
      </div>
      <div>
        <div className="text-[10px] text-slate-500">Total</div>
        <div className={`font-mono font-bold ${data.total_deleted > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
          {data.total_deleted.toLocaleString()}
        </div>
      </div>
    </div>
  );
}
