import { useState, useEffect } from 'react';
import {
  Webhook, Plus, RefreshCw, CheckCircle, XCircle, AlertTriangle,
  Send, Trash2, Power, PowerOff, Copy, Clock, Zap,
  ChevronDown, ChevronUp, X,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  fetchWebhooks, createWebhook, updateWebhook, deleteWebhook,
  testWebhook, fetchWebhookDeliveries,
} from '../api/client';
import type { WebhookInfo, WebhookCreateResponse, WebhookTestResult, WebhookDelivery } from '../types/api';

const EVENT_TYPES = [
  { value: 'alert_created', label: 'Alert Created', desc: 'Any alert fires' },
  { value: 'outlier_detected', label: 'Outlier Detected', desc: 'Prediction anomaly' },
  { value: 'pii_detected', label: 'PII Detected', desc: 'PHI found in data' },
  { value: 'data_quality_issue', label: 'Data Quality', desc: 'Quality check fails' },
  { value: 'key_rotated', label: 'Key Rotated', desc: 'Encryption key change' },
  { value: 'compliance_report', label: 'Compliance Report', desc: 'Report generated' },
];

function EventBadge({ event }: { event: string }) {
  const colors: Record<string, string> = {
    alert_created: 'bg-red-500/10 text-red-400 border-red-500/20',
    outlier_detected: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    pii_detected: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    data_quality_issue: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    key_rotated: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    compliance_report: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  };
  const label = EVENT_TYPES.find((e) => e.value === event)?.label || event;
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${colors[event] || 'bg-slate-500/10 text-slate-400 border-slate-500/20'}`}>
      {label}
    </span>
  );
}

export function WebhooksPage() {
  const [webhooks, setWebhooks] = useState<WebhookInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createdSecret, setCreatedSecret] = useState<WebhookCreateResponse | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ id: string; result: WebhookTestResult } | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [loadingDeliveries, setLoadingDeliveries] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchWebhooks();
      setWebhooks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load webhooks');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleTest = async (id: string) => {
    setTestingId(id);
    setTestResult(null);
    try {
      const result = await testWebhook(id);
      setTestResult({ id, result });
    } catch {
      setTestResult({ id, result: { success: false, http_status: null, response_body: null, message: 'Failed to send test' } });
    } finally {
      setTestingId(null);
    }
  };

  const handleToggle = async (webhook: WebhookInfo) => {
    try {
      await updateWebhook(webhook.id, { is_active: !webhook.is_active });
      await load();
    } catch { /* swallow */ }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteWebhook(id);
      setWebhooks((prev) => prev.filter((w) => w.id !== id));
    } catch { /* swallow */ }
  };

  const handleExpand = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    setLoadingDeliveries(true);
    try {
      const data = await fetchWebhookDeliveries(id, { limit: 10 });
      setDeliveries(data.deliveries);
    } catch {
      setDeliveries([]);
    } finally {
      setLoadingDeliveries(false);
    }
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
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Webhooks</h1>
          <p className="mt-1 text-sm text-slate-500">
            Receive real-time HTTP callbacks when events occur
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={load}
            className="glass-card-static flex items-center gap-2 px-4 py-2 text-sm text-slate-400 hover:text-cyan-400 transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            onClick={() => setShowCreateForm(true)}
            className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
            style={{ background: 'var(--gradient-brand)' }}
          >
            <Plus className="h-4 w-4" />
            Add Webhook
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 flex items-center gap-3 glass-card-static p-4" style={{ borderColor: 'rgba(239, 68, 68, 0.2)' }}>
          <AlertTriangle className="h-5 w-5 text-red-400" />
          <span className="text-sm text-red-300">{error}</span>
        </div>
      )}

      {/* Secret reveal modal */}
      <AnimatePresence>
        {createdSecret && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card-static mx-4 max-w-lg w-full p-6"
              style={{ borderColor: 'rgba(6, 182, 212, 0.3)' }}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10">
                  <CheckCircle className="h-5 w-5 text-emerald-400" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-200">Webhook Created</h3>
                  <p className="text-xs text-slate-500">{createdSecret.name}</p>
                </div>
              </div>
              <div className="mb-4 rounded-xl p-4" style={{ background: 'rgba(30, 41, 59, 0.5)', border: '1px solid rgba(234, 179, 8, 0.3)' }}>
                <p className="text-xs font-semibold text-amber-400 mb-2">
                  Save your signing secret now. You will not see it again.
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs text-slate-300 font-mono break-all">{createdSecret.secret}</code>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(createdSecret.secret);
                      setCopiedSecret(true);
                      setTimeout(() => setCopiedSecret(false), 2000);
                    }}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all"
                  >
                    {copiedSecret ? <CheckCircle className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <button
                onClick={() => { setCreatedSecret(null); load(); }}
                className="w-full rounded-xl py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
                style={{ background: 'var(--gradient-brand)' }}
              >
                I&apos;ve saved my secret
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create Form */}
      <AnimatePresence>
        {showCreateForm && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mb-6"
          >
            <CreateWebhookForm
              onCreated={(resp) => { setShowCreateForm(false); setCreatedSecret(resp); }}
              onCancel={() => setShowCreateForm(false)}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Webhooks List */}
      <div className="space-y-4">
        {webhooks.length === 0 && !showCreateForm ? (
          <div className="glass-card-static p-12 text-center">
            <div className="mx-auto h-14 w-14 rounded-2xl flex items-center justify-center bg-slate-800/50 mb-4">
              <Webhook className="h-6 w-6 text-slate-600" />
            </div>
            <p className="text-sm text-slate-400 mb-1">No webhooks configured</p>
            <p className="text-xs text-slate-600 mb-5">
              Add a webhook to receive real-time event notifications
            </p>
            <button
              onClick={() => setShowCreateForm(true)}
              className="inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
              style={{ background: 'var(--gradient-brand)' }}
            >
              <Plus className="h-4 w-4" />
              Create First Webhook
            </button>
          </div>
        ) : (
          webhooks.map((wh, i) => (
            <motion.div
              key={wh.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: i * 0.05 }}
              className="glass-card-static overflow-hidden"
            >
              {/* Main row */}
              <div className="flex items-center justify-between p-5">
                <div className="flex items-center gap-4 min-w-0">
                  <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
                    wh.is_active
                      ? 'bg-gradient-to-br from-cyan-500/15 to-violet-500/10'
                      : 'bg-slate-800/50'
                  }`}>
                    <Webhook className={`h-5 w-5 ${wh.is_active ? 'text-cyan-400' : 'text-slate-600'}`} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-slate-200 truncate">{wh.name}</p>
                      <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${
                        wh.is_active
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          : 'bg-slate-500/10 text-slate-500 border-slate-500/20'
                      }`}>
                        {wh.is_active ? 'Active' : 'Disabled'}
                      </span>
                      {wh.consecutive_failures > 0 && wh.is_active && (
                        <span className="rounded-md px-2 py-0.5 text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                          {wh.consecutive_failures} failures
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-slate-500 font-mono truncate">{wh.url}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {wh.events.map((ev) => <EventBadge key={ev} event={ev} />)}
                    </div>
                  </div>
                </div>

                {/* Stats & Actions */}
                <div className="flex items-center gap-4 shrink-0">
                  {/* Delivery stats */}
                  <div className="hidden lg:flex items-center gap-4 mr-2">
                    <div className="text-center">
                      <p className="text-lg font-bold text-slate-200">{wh.total_deliveries}</p>
                      <p className="text-[10px] text-slate-500">Delivered</p>
                    </div>
                    <div className="text-center">
                      <p className={`text-lg font-bold ${wh.total_failures > 0 ? 'text-red-400' : 'text-slate-500'}`}>
                        {wh.total_failures}
                      </p>
                      <p className="text-[10px] text-slate-500">Failed</p>
                    </div>
                  </div>

                  {/* Test result indicator */}
                  {testResult?.id === wh.id && (
                    <div className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium ${
                      testResult.result.success
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-red-500/10 text-red-400'
                    }`}>
                      {testResult.result.success
                        ? <CheckCircle className="h-3.5 w-3.5" />
                        : <XCircle className="h-3.5 w-3.5" />}
                      {testResult.result.success ? 'OK' : testResult.result.http_status || 'Err'}
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleTest(wh.id)}
                      disabled={testingId === wh.id}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all disabled:opacity-30"
                      title="Send test"
                    >
                      {testingId === wh.id
                        ? <RefreshCw className="h-4 w-4 animate-spin" />
                        : <Send className="h-4 w-4" />}
                    </button>
                    <button
                      onClick={() => handleToggle(wh)}
                      className={`flex h-8 w-8 items-center justify-center rounded-lg transition-all ${
                        wh.is_active
                          ? 'text-emerald-400 hover:bg-emerald-500/10'
                          : 'text-slate-600 hover:text-slate-400 hover:bg-slate-500/10'
                      }`}
                      title={wh.is_active ? 'Disable' : 'Enable'}
                    >
                      {wh.is_active ? <Power className="h-4 w-4" /> : <PowerOff className="h-4 w-4" />}
                    </button>
                    <button
                      onClick={() => handleExpand(wh.id)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all"
                      title="Delivery history"
                    >
                      {expandedId === wh.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </button>
                    <button
                      onClick={() => handleDelete(wh.id)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Expanded delivery history */}
              <AnimatePresence>
                {expandedId === wh.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                    style={{ borderTop: '1px solid var(--border-subtle)' }}
                  >
                    <div className="p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Clock className="h-4 w-4 text-cyan-400" />
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                          Recent Deliveries
                        </h4>
                      </div>
                      {loadingDeliveries ? (
                        <div className="py-6 text-center">
                          <RefreshCw className="mx-auto h-5 w-5 animate-spin text-cyan-400" />
                        </div>
                      ) : deliveries.length === 0 ? (
                        <p className="py-4 text-center text-xs text-slate-600">No deliveries yet</p>
                      ) : (
                        <div className="space-y-2">
                          {deliveries.map((d) => (
                            <div
                              key={d.id}
                              className="flex items-center justify-between rounded-lg px-3 py-2"
                              style={{ background: 'rgba(30, 41, 59, 0.3)', border: '1px solid var(--border-subtle)' }}
                            >
                              <div className="flex items-center gap-3">
                                {d.success
                                  ? <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                                  : <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />}
                                <div>
                                  <EventBadge event={d.event_type} />
                                  {d.error && (
                                    <p className="mt-0.5 text-[10px] text-red-400 truncate max-w-[300px]">{d.error}</p>
                                  )}
                                </div>
                              </div>
                              <div className="flex items-center gap-4 text-xs text-slate-500">
                                {d.http_status && (
                                  <span className={d.success ? 'text-emerald-400' : 'text-red-400'}>
                                    {d.http_status}
                                  </span>
                                )}
                                {d.response_time_ms !== null && (
                                  <span>{d.response_time_ms}ms</span>
                                )}
                                <span>{new Date(d.delivered_at).toLocaleString()}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════ */
/*  Create Webhook Form                                           */
/* ═══════════════════════════════════════════════════════════════ */

function CreateWebhookForm({
  onCreated,
  onCancel,
}: {
  onCreated: (resp: WebhookCreateResponse) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<string[]>(['alert_created']);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const toggleEvent = (ev: string) => {
    setSelectedEvents((prev) =>
      prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev],
    );
  };

  const handleSubmit = async () => {
    setFormError(null);
    if (!name.trim()) { setFormError('Name is required'); return; }
    if (!url.trim()) { setFormError('URL is required'); return; }
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setFormError('URL must start with http:// or https://');
      return;
    }
    if (selectedEvents.length === 0) { setFormError('Select at least one event'); return; }

    setSubmitting(true);
    try {
      const resp = await createWebhook({
        name: name.trim(),
        url: url.trim(),
        events: selectedEvents,
        description: description.trim() || undefined,
      });
      onCreated(resp);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to create webhook');
    } finally {
      setSubmitting(false);
    }
  };

  const inputStyle = {
    background: 'rgba(30, 41, 59, 0.5)',
    border: '1px solid var(--border-default)',
  };

  return (
    <div className="glass-card-static p-6">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500/15 to-violet-500/10">
            <Plus className="h-4 w-4 text-cyan-400" />
          </div>
          <h3 className="font-semibold text-slate-200">New Webhook</h3>
        </div>
        <button onClick={onCancel} className="text-slate-500 hover:text-slate-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      {formError && (
        <div className="mb-4 flex items-center gap-2 rounded-lg p-3 bg-red-500/10 border border-red-500/20">
          <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
          <p className="text-xs text-red-300">{formError}</p>
        </div>
      )}

      <div className="space-y-4">
        {/* Name */}
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 block">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Slack #ops-alerts"
            className="w-full rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none transition-colors"
            style={inputStyle}
            onFocus={(e) => { e.target.style.borderColor = 'rgba(6, 182, 212, 0.4)'; }}
            onBlur={(e) => { e.target.style.borderColor = 'var(--border-default)'; }}
          />
        </div>

        {/* URL */}
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 block">Endpoint URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://hooks.slack.com/services/..."
            className="w-full rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none transition-colors font-mono"
            style={inputStyle}
            onFocus={(e) => { e.target.style.borderColor = 'rgba(6, 182, 212, 0.4)'; }}
            onBlur={(e) => { e.target.style.borderColor = 'var(--border-default)'; }}
          />
        </div>

        {/* Description */}
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5 block">
            Description <span className="text-slate-600">(optional)</span>
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Notify the ops team about critical alerts"
            className="w-full rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none transition-colors"
            style={inputStyle}
            onFocus={(e) => { e.target.style.borderColor = 'rgba(6, 182, 212, 0.4)'; }}
            onBlur={(e) => { e.target.style.borderColor = 'var(--border-default)'; }}
          />
        </div>

        {/* Event Types */}
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2 block">Event Subscriptions</label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {EVENT_TYPES.map(({ value, label, desc }) => {
              const selected = selectedEvents.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggleEvent(value)}
                  className={`rounded-xl p-3 text-left transition-all ${
                    selected
                      ? 'bg-cyan-500/10 border-cyan-500/30'
                      : 'hover:bg-slate-800/50 border-transparent'
                  }`}
                  style={{
                    border: `1px solid ${selected ? 'rgba(6, 182, 212, 0.3)' : 'var(--border-subtle)'}`,
                    background: selected ? 'rgba(6, 182, 212, 0.08)' : 'rgba(30, 41, 59, 0.3)',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <div className={`h-3.5 w-3.5 rounded-sm border ${
                      selected
                        ? 'bg-cyan-500 border-cyan-500'
                        : 'border-slate-600'
                    } flex items-center justify-center`}>
                      {selected && <CheckCircle className="h-2.5 w-2.5 text-white" />}
                    </div>
                    <p className={`text-xs font-medium ${selected ? 'text-cyan-300' : 'text-slate-400'}`}>{label}</p>
                  </div>
                  <p className="mt-1 ml-5.5 text-[10px] text-slate-600">{desc}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onCancel}
            className="rounded-xl px-5 py-2.5 text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
            style={{ background: 'var(--gradient-brand)' }}
          >
            {submitting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
            {submitting ? 'Creating...' : 'Create Webhook'}
          </button>
        </div>
      </div>
    </div>
  );
}
