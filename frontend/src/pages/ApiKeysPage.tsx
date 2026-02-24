import { useState, useEffect } from 'react';
import {
  Key, Copy, CheckCircle, RefreshCw, Shield, Clock, Plus, Trash2,
  AlertTriangle, Eye, X,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchApiKeys, createApiKey, revokeApiKey } from '../api/client';
import type { ApiKeyInfo, ApiKeyCreateResponse } from '../types/api';

// ── Available Scopes ──────────────────────────────────────────────
const AVAILABLE_SCOPES = [
  { value: 'ingest', label: 'Ingest', description: 'Submit inference data' },
  { value: 'read', label: 'Read', description: 'View dashboards and reports' },
  { value: 'audit', label: 'Audit', description: 'Access compliance reports' },
  { value: 'admin', label: 'Admin', description: 'Manage settings and keys' },
];

// ── Expiration Presets ────────────────────────────────────────────
const EXPIRY_PRESETS = [
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
  { value: 365, label: '1 year' },
  { value: 730, label: '2 years' },
];

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState<ApiKeyCreateResponse | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── Create Form State ───────────────────────────────────────────
  const [createName, setCreateName] = useState('');
  const [createScopes, setCreateScopes] = useState<string[]>(['ingest', 'read']);
  const [createExpiry, setCreateExpiry] = useState(365);
  const [creating, setCreating] = useState(false);

  const loadKeys = () => {
    setLoading(true);
    fetchApiKeys()
      .then(setKeys)
      .catch(() => setError('Failed to load API keys'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadKeys(); }, []);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  const toggleScope = (scope: string) => {
    setCreateScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  };

  const handleCreate = async () => {
    if (!createName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const result = await createApiKey({
        name: createName.trim(),
        scopes: createScopes,
        expires_in_days: createExpiry,
      });
      setNewKey(result);
      setShowCreate(false);
      setCreateName('');
      setCreateScopes(['ingest', 'read']);
      setCreateExpiry(365);
      loadKeys();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create API key';
      setError(msg);
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (keyId: string) => {
    setRevoking(keyId);
    setError(null);
    try {
      await revokeApiKey(keyId);
      setConfirmRevoke(null);
      loadKeys();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to revoke API key';
      setError(msg);
    } finally {
      setRevoking(null);
    }
  };

  const activeKeys = keys.filter((k) => k.is_active);
  const revokedKeys = keys.filter((k) => !k.is_active);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">API Keys</h1>
          <p className="mt-1 text-sm text-slate-500">
            Create and manage API authentication keys for your tenant
          </p>
        </div>
        <button
          onClick={() => { setShowCreate(true); setNewKey(null); }}
          className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
          style={{ background: 'var(--gradient-brand)' }}
        >
          <Plus className="h-4 w-4" />
          Create Key
        </button>
      </div>

      {/* Error Banner */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mb-6 flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3"
          >
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
            <p className="text-sm text-red-300">{error}</p>
            <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300">
              <X className="h-4 w-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── New Key Display (shown once after creation) ────────────── */}
      <AnimatePresence>
        {newKey && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mb-6 glass-card-static p-6 relative overflow-hidden"
            style={{ borderColor: 'rgba(16, 185, 129, 0.3)' }}
          >
            <div className="absolute inset-0 pointer-events-none"
              style={{ background: 'radial-gradient(ellipse at top left, rgba(16, 185, 129, 0.08), transparent 60%)' }} />
            <div className="relative">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <CheckCircle className="h-5 w-5 text-emerald-400" />
                  <h3 className="text-sm font-semibold text-emerald-300">API Key Created Successfully</h3>
                </div>
                <button onClick={() => setNewKey(null)} className="text-slate-500 hover:text-slate-300">
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="flex items-center gap-3 rounded-xl bg-slate-900/80 border border-emerald-500/20 px-4 py-3 mb-3">
                <code className="text-sm text-emerald-300 font-mono flex-1 select-all break-all">
                  {newKey.api_key}
                </code>
                <button
                  onClick={() => copyToClipboard(newKey.api_key, 'new-key')}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 transition-all shrink-0"
                  title="Copy API key"
                >
                  {copied === 'new-key' ? (
                    <CheckCircle className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </button>
              </div>

              <div className="flex items-center gap-2 text-xs text-amber-400">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                <span>{newKey.warning}</span>
              </div>

              <div className="mt-3 flex items-center gap-4 text-xs text-slate-500">
                <span><strong className="text-slate-400">Name:</strong> {newKey.name}</span>
                <span><strong className="text-slate-400">Scopes:</strong> {newKey.scopes.join(', ')}</span>
                <span><strong className="text-slate-400">Expires:</strong> {new Date(newKey.expires_at).toLocaleDateString()}</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Create Key Modal ──────────────────────────────────────── */}
      <AnimatePresence>
        {showCreate && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setShowCreate(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="w-full max-w-lg glass-card-static p-6 mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/15 to-violet-500/10">
                    <Key className="h-4 w-4 text-cyan-400" />
                  </div>
                  <h2 className="text-lg font-bold text-slate-100">Create API Key</h2>
                </div>
                <button onClick={() => setShowCreate(false)} className="text-slate-500 hover:text-slate-300">
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Key Name */}
              <div className="mb-5">
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Key Name</label>
                <input
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="e.g., Production Ingest Key"
                  className="w-full rounded-xl border border-slate-700 bg-slate-900/50 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
                  autoFocus
                />
              </div>

              {/* Scopes */}
              <div className="mb-5">
                <label className="block text-xs font-medium text-slate-400 mb-2">Permission Scopes</label>
                <div className="grid grid-cols-2 gap-2">
                  {AVAILABLE_SCOPES.map((scope) => (
                    <button
                      key={scope.value}
                      type="button"
                      onClick={() => toggleScope(scope.value)}
                      className={`flex flex-col items-start rounded-xl border px-3.5 py-2.5 text-left transition-all ${
                        createScopes.includes(scope.value)
                          ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300'
                          : 'border-slate-700 bg-slate-900/30 text-slate-400 hover:border-slate-600'
                      }`}
                    >
                      <span className="text-sm font-medium">{scope.label}</span>
                      <span className="text-[10px] opacity-70">{scope.description}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Expiration */}
              <div className="mb-6">
                <label className="block text-xs font-medium text-slate-400 mb-2">Expiration</label>
                <div className="flex gap-2">
                  {EXPIRY_PRESETS.map((preset) => (
                    <button
                      key={preset.value}
                      type="button"
                      onClick={() => setCreateExpiry(preset.value)}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-all ${
                        createExpiry === preset.value
                          ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300'
                          : 'border-slate-700 bg-slate-900/30 text-slate-400 hover:border-slate-600'
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => setShowCreate(false)}
                  className="rounded-xl px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-all"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating || !createName.trim() || createScopes.length === 0}
                  className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ background: 'var(--gradient-brand)' }}
                >
                  {creating ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <Key className="h-4 w-4" />
                  )}
                  {creating ? 'Creating...' : 'Create Key'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Revoke Confirmation Modal ─────────────────────────────── */}
      <AnimatePresence>
        {confirmRevoke && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setConfirmRevoke(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md glass-card-static p-6 mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-500/10">
                  <AlertTriangle className="h-5 w-5 text-red-400" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-100">Revoke API Key</h3>
                  <p className="text-xs text-slate-500">This action cannot be undone</p>
                </div>
              </div>
              <p className="text-sm text-slate-400 mb-2">
                Are you sure you want to revoke this key? Any applications using it will immediately lose access.
              </p>
              <p className="text-xs font-mono text-slate-500 mb-5 px-3 py-2 rounded-lg bg-slate-900/50 border border-slate-800">
                {keys.find((k) => k.id === confirmRevoke)?.name || confirmRevoke}
              </p>
              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => setConfirmRevoke(null)}
                  className="rounded-xl px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-all"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleRevoke(confirmRevoke)}
                  disabled={revoking === confirmRevoke}
                  className="flex items-center gap-2 rounded-xl bg-red-500/15 border border-red-500/30 px-4 py-2 text-sm font-medium text-red-300 hover:bg-red-500/25 transition-all disabled:opacity-50"
                >
                  {revoking === confirmRevoke ? (
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                  {revoking === confirmRevoke ? 'Revoking...' : 'Revoke Key'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Active Keys ───────────────────────────────────────────── */}
      <div className="glass-card-static overflow-hidden mb-6">
        <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center gap-2">
            <Key className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-200">Active Keys</h3>
          </div>
          <span className="text-xs text-slate-500">{activeKeys.length} key{activeKeys.length !== 1 ? 's' : ''}</span>
        </div>
        <div>
          {activeKeys.map((key, i) => (
            <KeyRow
              key={key.id}
              keyInfo={key}
              index={i}
              copied={copied}
              onCopy={copyToClipboard}
              onRevoke={() => setConfirmRevoke(key.id)}
            />
          ))}
          {activeKeys.length === 0 && (
            <div className="px-6 py-12 text-center">
              <div className="mx-auto h-12 w-12 rounded-xl flex items-center justify-center bg-slate-800/50 mb-3">
                <Key className="h-5 w-5 text-slate-600" />
              </div>
              <p className="text-sm text-slate-500 mb-1">No active API keys</p>
              <p className="text-xs text-slate-600">Create a key to start authenticating API requests</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Revoked Keys (collapsed section) ──────────────────────── */}
      {revokedKeys.length > 0 && (
        <RevokedKeysSection keys={revokedKeys} copied={copied} onCopy={copyToClipboard} />
      )}

      {/* ── Info Banner ───────────────────────────────────────────── */}
      <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900/30 px-5 py-4">
        <div className="flex items-start gap-3">
          <Shield className="h-4 w-4 text-violet-400 mt-0.5 shrink-0" />
          <div className="text-xs text-slate-500 space-y-1">
            <p><strong className="text-slate-400">Security notes:</strong></p>
            <ul className="list-disc list-inside space-y-0.5 ml-1">
              <li>API keys are hashed with PBKDF2-SHA256 before storage</li>
              <li>Plaintext keys are shown <strong>once</strong> at creation time only</li>
              <li>Revoked keys are immediately deactivated and cannot be restored</li>
              <li>All key operations are logged in the HIPAA audit trail</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  Sub-Components
// ══════════════════════════════════════════════════════════════════

function KeyRow({
  keyInfo,
  index,
  copied,
  onCopy,
  onRevoke,
}: {
  keyInfo: ApiKeyInfo;
  index: number;
  copied: string | null;
  onCopy: (text: string, id: string) => void;
  onRevoke?: () => void;
}) {
  const isExpired = keyInfo.expires_at && new Date(keyInfo.expires_at) < new Date();

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.05 }}
      className="flex items-center justify-between px-6 py-4 table-row-hover"
      style={{ borderBottom: '1px solid var(--border-subtle)' }}
    >
      <div className="flex items-center gap-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/15 to-violet-500/10">
          <Key className="h-4.5 w-4.5 text-cyan-400" />
        </div>
        <div>
          <p className="text-sm font-medium text-slate-200">{keyInfo.name}</p>
          <p className="text-xs text-slate-500 font-mono mt-0.5">
            {keyInfo.key_prefix}...{keyInfo.key_suffix}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        {/* Scopes */}
        <div className="text-right hidden sm:block">
          <div className="flex items-center gap-1.5 justify-end">
            <Shield className="h-3 w-3 text-slate-500" />
            <p className="text-xs text-slate-400">{keyInfo.scopes.join(', ')}</p>
          </div>
          <div className="flex items-center gap-1.5 justify-end mt-0.5">
            <Clock className="h-3 w-3 text-slate-600" />
            <p className={`text-[10px] ${isExpired ? 'text-red-400' : 'text-slate-600'}`}>
              {isExpired ? 'Expired' : `Expires ${new Date(keyInfo.expires_at).toLocaleDateString()}`}
            </p>
          </div>
          {keyInfo.last_used_at && (
            <p className="text-[10px] text-slate-600 mt-0.5">
              Last used {new Date(keyInfo.last_used_at).toLocaleDateString()}
            </p>
          )}
        </div>

        {/* Status Badge */}
        <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${
          keyInfo.is_active && !isExpired
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            : isExpired
              ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
              : 'bg-red-500/10 text-red-400 border-red-500/20'
        }`}>
          {keyInfo.is_active ? (isExpired ? 'Expired' : 'Active') : 'Revoked'}
        </span>

        {/* Copy Key ID */}
        <button
          onClick={() => onCopy(keyInfo.id, keyInfo.id)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all"
          title="Copy key ID"
        >
          {copied === keyInfo.id ? (
            <CheckCircle className="h-4 w-4 text-emerald-400" />
          ) : (
            <Copy className="h-4 w-4" />
          )}
        </button>

        {/* Revoke Button */}
        {keyInfo.is_active && onRevoke && (
          <button
            onClick={onRevoke}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
            title="Revoke key"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </motion.div>
  );
}

function RevokedKeysSection({
  keys,
  copied,
  onCopy,
}: {
  keys: ApiKeyInfo[];
  copied: string | null;
  onCopy: (text: string, id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="glass-card-static overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-800/30 transition-all"
        style={{ borderBottom: expanded ? '1px solid var(--border-subtle)' : 'none' }}
      >
        <div className="flex items-center gap-2">
          <Trash2 className="h-4 w-4 text-slate-600" />
          <h3 className="text-sm font-semibold text-slate-500">Revoked Keys</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-600">{keys.length} key{keys.length !== 1 ? 's' : ''}</span>
          <motion.span
            animate={{ rotate: expanded ? 180 : 0 }}
            className="text-slate-600"
          >
            <Eye className="h-3.5 w-3.5" />
          </motion.span>
        </div>
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {keys.map((key, i) => (
              <KeyRow key={key.id} keyInfo={key} index={i} copied={copied} onCopy={onCopy} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
