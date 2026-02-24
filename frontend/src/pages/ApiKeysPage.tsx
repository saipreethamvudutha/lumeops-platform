import { useState, useEffect } from 'react';
import { Key, Copy, CheckCircle, RefreshCw, Shield, Clock } from 'lucide-react';
import { motion } from 'framer-motion';
import { fetchApiKeys } from '../api/client';
import type { ApiKeyInfo } from '../types/api';

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    fetchApiKeys()
      .then(setKeys)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-100 tracking-tight">API Keys</h1>
        <p className="mt-1 text-sm text-slate-500">Manage your API authentication keys</p>
      </div>

      <div className="glass-card-static overflow-hidden">
        <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center gap-2">
            <Key className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-200">Active Keys</h3>
          </div>
          <span className="text-xs text-slate-500">{keys.length} keys</span>
        </div>
        <div>
          {keys.map((key, i) => (
            <motion.div
              key={key.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: i * 0.05 }}
              className="flex items-center justify-between px-6 py-4 table-row-hover"
              style={{ borderBottom: '1px solid var(--border-subtle)' }}
            >
              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/15 to-violet-500/10">
                  <Key className="h-4.5 w-4.5 text-cyan-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">{key.name}</p>
                  <p className="text-xs text-slate-500 font-mono mt-0.5">
                    {key.key_prefix}...{key.key_suffix}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-5">
                <div className="text-right">
                  <div className="flex items-center gap-1.5 justify-end">
                    <Shield className="h-3 w-3 text-slate-500" />
                    <p className="text-xs text-slate-400">
                      {key.scopes.join(', ')}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 justify-end mt-0.5">
                    <Clock className="h-3 w-3 text-slate-600" />
                    <p className="text-[10px] text-slate-600">
                      Expires {new Date(key.expires_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${
                  key.is_active
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-red-500/10 text-red-400 border-red-500/20'
                }`}>
                  {key.is_active ? 'Active' : 'Revoked'}
                </span>
                <button
                  onClick={() => copyToClipboard(key.id, key.id)}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all"
                  title="Copy key ID"
                >
                  {copied === key.id ? (
                    <CheckCircle className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </button>
              </div>
            </motion.div>
          ))}
          {keys.length === 0 && (
            <div className="px-6 py-12 text-center">
              <div className="mx-auto h-12 w-12 rounded-xl flex items-center justify-center bg-slate-800/50 mb-3">
                <Key className="h-5 w-5 text-slate-600" />
              </div>
              <p className="text-sm text-slate-500">No API keys found</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
