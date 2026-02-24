import { useState, useEffect } from 'react';
import { Key, Copy, CheckCircle, RefreshCw } from 'lucide-react';
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
        <RefreshCw className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-800">API Keys</h1>
        <p className="mt-1 text-sm text-slate-500">Manage your API authentication keys</p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-5 py-4">
          <h3 className="font-semibold text-slate-800">Active Keys</h3>
        </div>
        <div className="divide-y divide-slate-100">
          {keys.map((key) => (
            <div key={key.id} className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-4">
                <div className="rounded-lg bg-blue-100 p-2">
                  <Key className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-800">{key.name}</p>
                  <p className="text-xs text-slate-500 font-mono">
                    {key.key_prefix}...{key.key_suffix}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-6">
                <div className="text-right">
                  <p className="text-xs text-slate-500">
                    Scopes: {key.scopes.join(', ')}
                  </p>
                  <p className="text-xs text-slate-400">
                    Expires {new Date(key.expires_at).toLocaleDateString()}
                  </p>
                </div>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    key.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                  }`}
                >
                  {key.is_active ? 'Active' : 'Inactive'}
                </span>
                <button
                  onClick={() => copyToClipboard(key.id, key.id)}
                  className="text-slate-400 hover:text-slate-600"
                  title="Copy key ID"
                >
                  {copied === key.id ? (
                    <CheckCircle className="h-4 w-4 text-emerald-500" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>
          ))}
          {keys.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-slate-400">
              No API keys found
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
