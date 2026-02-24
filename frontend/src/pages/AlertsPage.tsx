import { useState, useEffect, useCallback } from 'react';
import {
  Bell, RefreshCw, CheckCircle, XCircle, AlertTriangle, Clock,
  Filter, ChevronDown, ChevronUp, Eye, CheckCheck, ShieldCheck,
  Zap,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  fetchAlerts, fetchAlertStats, acknowledgeAlert, resolveAlert,
  bulkAcknowledgeAlerts, bulkResolveAlerts,
} from '../api/client';
import type { AlertDetail, AlertStats } from '../types/api';

type AlertStatus = 'open' | 'acknowledged' | 'resolved' | '';

const SEVERITY_CONFIG: Record<string, { color: string; bg: string; border: string; icon: typeof AlertTriangle }> = {
  critical: { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20', icon: XCircle },
  warning: { color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20', icon: AlertTriangle },
  info: { color: 'text-cyan-400', bg: 'bg-cyan-500/10', border: 'border-cyan-500/20', icon: Bell },
};

const TYPE_LABELS: Record<string, string> = {
  outlier: 'Outlier',
  data_quality: 'Data Quality',
  system_error: 'System Error',
};

function SeverityBadge({ severity }: { severity: string }) {
  const cfg = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.info;
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${cfg.bg} ${cfg.color} ${cfg.border}`}>
      {severity}
    </span>
  );
}

function StatusBadge({ alert }: { alert: AlertDetail }) {
  if (alert.resolved_at) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
        <CheckCircle className="h-3 w-3" /> Resolved
      </span>
    );
  }
  if (alert.acknowledged_at) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-violet-500/10 text-violet-400 border-violet-500/20">
        <Eye className="h-3 w-3" /> Acknowledged
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-red-500/10 text-red-400 border-red-500/20">
      <Zap className="h-3 w-3" /> Open
    </span>
  );
}

function StatCard({ label, value, subValue, icon: Icon, color }: {
  label: string; value: string | number; subValue?: string;
  icon: typeof Bell; color: string;
}) {
  return (
    <div className="glass-card-static p-4">
      <div className="flex items-center justify-between mb-2">
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${color}`}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
      <p className="text-xs text-slate-500 mt-0.5">{label}</p>
      {subValue && <p className="text-[10px] text-slate-600 mt-0.5">{subValue}</p>}
    </div>
  );
}

export function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertDetail[]>([]);
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState<AlertStatus>('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [days, setDays] = useState(7);

  // Pagination
  const [offset, setOffset] = useState(0);
  const limit = 20;

  // Selection for bulk actions
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Action states
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [alertData, statsData] = await Promise.all([
        fetchAlerts({
          status: statusFilter || undefined,
          severity: severityFilter || undefined,
          alert_type: typeFilter || undefined,
          days,
          limit,
          offset,
        }),
        fetchAlertStats(days),
      ]);
      setAlerts(alertData.alerts);
      setTotal(alertData.total);
      setHasMore(alertData.has_more);
      setStats(statsData);
    } catch {
      // swallow
    } finally {
      setLoading(false);
    }
  }, [statusFilter, severityFilter, typeFilter, days, offset]);

  useEffect(() => { load(); }, [load]);

  // Reset offset when filters change
  useEffect(() => { setOffset(0); setSelected(new Set()); }, [statusFilter, severityFilter, typeFilter, days]);

  const handleAck = async (id: string) => {
    setActionLoading(id);
    try {
      await acknowledgeAlert(id, 'Dashboard User');
      await load();
    } catch { /* swallow */ }
    finally { setActionLoading(null); }
  };

  const handleResolve = async (id: string) => {
    setActionLoading(id);
    try {
      await resolveAlert(id);
      await load();
    } catch { /* swallow */ }
    finally { setActionLoading(null); }
  };

  const handleBulkAck = async () => {
    if (selected.size === 0) return;
    setActionLoading('bulk');
    try {
      await bulkAcknowledgeAlerts([...selected], 'Dashboard User');
      setSelected(new Set());
      await load();
    } catch { /* swallow */ }
    finally { setActionLoading(null); }
  };

  const handleBulkResolve = async () => {
    if (selected.size === 0) return;
    setActionLoading('bulk');
    try {
      await bulkResolveAlerts([...selected]);
      setSelected(new Set());
      await load();
    } catch { /* swallow */ }
    finally { setActionLoading(null); }
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (selected.size === alerts.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(alerts.map((a) => a.id)));
    }
  };

  const selectStyle = {
    background: 'rgba(30, 41, 59, 0.5)',
    border: '1px solid var(--border-default)',
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Alerts</h1>
          <p className="mt-1 text-sm text-slate-500">
            Monitor, acknowledge, and resolve alerts from your inference pipeline
          </p>
        </div>
        <button
          onClick={load}
          className="glass-card-static flex items-center gap-2 px-4 py-2 text-sm text-slate-400 hover:text-cyan-400 transition-colors"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats Row */}
      {stats && (
        <div className="mb-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Open Alerts"
            value={stats.total_active}
            icon={Zap}
            color="bg-red-500/10 text-red-400"
          />
          <StatCard
            label="Acknowledged"
            value={stats.total_acknowledged}
            icon={Eye}
            color="bg-violet-500/10 text-violet-400"
          />
          <StatCard
            label="Resolved"
            value={stats.total_resolved}
            icon={CheckCircle}
            color="bg-emerald-500/10 text-emerald-400"
          />
          <StatCard
            label="MTTA"
            value={stats.mean_time_to_acknowledge_minutes != null ? `${stats.mean_time_to_acknowledge_minutes}m` : '--'}
            subValue="Mean time to acknowledge"
            icon={Clock}
            color="bg-cyan-500/10 text-cyan-400"
          />
        </div>
      )}

      {/* Filters */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Filter className="h-3.5 w-3.5" />
          <span>Filters:</span>
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as AlertStatus)}
          className="rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none"
          style={selectStyle}
        >
          <option value="">All Status</option>
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </select>

        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none"
          style={selectStyle}
        >
          <option value="">All Severity</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>

        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none"
          style={selectStyle}
        >
          <option value="">All Types</option>
          <option value="outlier">Outlier</option>
          <option value="data_quality">Data Quality</option>
          <option value="system_error">System Error</option>
        </select>

        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none"
          style={selectStyle}
        >
          <option value={1}>Last 24h</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>

        {/* Bulk actions */}
        {selected.size > 0 && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-cyan-400">{selected.size} selected</span>
            <button
              onClick={handleBulkAck}
              disabled={actionLoading === 'bulk'}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-violet-400 bg-violet-500/10 border border-violet-500/20 hover:bg-violet-500/20 transition-colors disabled:opacity-50"
            >
              <CheckCheck className="h-3.5 w-3.5" /> Ack All
            </button>
            <button
              onClick={handleBulkResolve}
              disabled={actionLoading === 'bulk'}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
            >
              <ShieldCheck className="h-3.5 w-3.5" /> Resolve All
            </button>
          </div>
        )}
      </div>

      {/* Alert List */}
      {loading && alerts.length === 0 ? (
        <div className="flex h-64 items-center justify-center">
          <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="glass-card-static p-12 text-center">
          <div className="mx-auto h-14 w-14 rounded-2xl flex items-center justify-center bg-slate-800/50 mb-4">
            <ShieldCheck className="h-6 w-6 text-emerald-400" />
          </div>
          <p className="text-sm text-slate-400 mb-1">No alerts found</p>
          <p className="text-xs text-slate-600">
            {statusFilter || severityFilter || typeFilter
              ? 'Try adjusting your filters'
              : 'Your inference pipeline is running smoothly'}
          </p>
        </div>
      ) : (
        <>
          {/* Table Header */}
          <div className="mb-2 flex items-center gap-3 px-4 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <div className="w-8">
              <button onClick={selectAll} className="h-4 w-4 rounded border border-slate-600 flex items-center justify-center hover:border-cyan-500 transition-colors">
                {selected.size === alerts.length && alerts.length > 0 && <CheckCircle className="h-3 w-3 text-cyan-400" />}
              </button>
            </div>
            <div className="w-20">Severity</div>
            <div className="w-24">Status</div>
            <div className="w-24">Type</div>
            <div className="flex-1">Message</div>
            <div className="w-40 text-right">Triggered</div>
            <div className="w-28 text-right">Actions</div>
          </div>

          {/* Alert Rows */}
          <div className="space-y-2">
            {alerts.map((alert, i) => {
              const isExpanded = expandedId === alert.id;
              const isSelected = selected.has(alert.id);

              return (
                <motion.div
                  key={alert.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.15, delay: i * 0.02 }}
                  className={`glass-card-static overflow-hidden transition-all ${isSelected ? 'ring-1 ring-cyan-500/30' : ''}`}
                >
                  <div className="flex items-center gap-3 px-4 py-3">
                    {/* Checkbox */}
                    <div className="w-8">
                      <button
                        onClick={() => toggleSelect(alert.id)}
                        className={`h-4 w-4 rounded border flex items-center justify-center transition-colors ${
                          isSelected ? 'bg-cyan-500 border-cyan-500' : 'border-slate-600 hover:border-cyan-500'
                        }`}
                      >
                        {isSelected && <CheckCircle className="h-3 w-3 text-white" />}
                      </button>
                    </div>

                    {/* Severity */}
                    <div className="w-20">
                      <SeverityBadge severity={alert.severity} />
                    </div>

                    {/* Status */}
                    <div className="w-24">
                      <StatusBadge alert={alert} />
                    </div>

                    {/* Type */}
                    <div className="w-24">
                      <span className="text-xs text-slate-400">{TYPE_LABELS[alert.alert_type] || alert.alert_type}</span>
                    </div>

                    {/* Message */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-300 truncate">{alert.message}</p>
                    </div>

                    {/* Triggered time */}
                    <div className="w-40 text-right">
                      <p className="text-xs text-slate-500">{new Date(alert.triggered_at).toLocaleString()}</p>
                    </div>

                    {/* Actions */}
                    <div className="w-28 flex items-center justify-end gap-1">
                      <button
                        onClick={() => setExpandedId(isExpanded ? null : alert.id)}
                        className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all"
                        title="Details"
                      >
                        {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                      </button>

                      {!alert.acknowledged_at && !alert.resolved_at && (
                        <button
                          onClick={() => handleAck(alert.id)}
                          disabled={actionLoading === alert.id}
                          className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 hover:text-violet-400 hover:bg-violet-500/10 transition-all disabled:opacity-30"
                          title="Acknowledge"
                        >
                          {actionLoading === alert.id
                            ? <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                            : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      )}

                      {!alert.resolved_at && (
                        <button
                          onClick={() => handleResolve(alert.id)}
                          disabled={actionLoading === alert.id}
                          className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 hover:text-emerald-400 hover:bg-emerald-500/10 transition-all disabled:opacity-30"
                          title="Resolve"
                        >
                          {actionLoading === alert.id
                            ? <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                            : <CheckCircle className="h-3.5 w-3.5" />}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Expanded Details */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                        style={{ borderTop: '1px solid var(--border-subtle)' }}
                      >
                        <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                          <DetailField label="Alert ID" value={alert.id} mono />
                          <DetailField label="Model ID" value={alert.model_id} mono />
                          <DetailField label="Inference ID" value={alert.inference_id || '--'} mono />
                          <DetailField
                            label="Triggered"
                            value={new Date(alert.triggered_at).toLocaleString()}
                          />
                          <DetailField
                            label="Acknowledged"
                            value={alert.acknowledged_at ? new Date(alert.acknowledged_at).toLocaleString() : '--'}
                          />
                          <DetailField label="Acknowledged By" value={alert.acknowledged_by || '--'} />
                          <DetailField
                            label="Resolved"
                            value={alert.resolved_at ? new Date(alert.resolved_at).toLocaleString() : '--'}
                          />
                          <DetailField
                            label="Notifications"
                            value={[
                              alert.notified_email && 'Email',
                              alert.notified_slack && 'Slack',
                            ].filter(Boolean).join(', ') || 'None'}
                          />
                          {alert.details && (
                            <div className="col-span-full">
                              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Details</p>
                              <pre className="rounded-lg p-3 text-xs text-slate-400 font-mono overflow-x-auto" style={{ background: 'rgba(30, 41, 59, 0.5)', border: '1px solid var(--border-subtle)' }}>
                                {JSON.stringify(alert.details, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </div>

          {/* Pagination */}
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-slate-500">
              Showing {offset + 1}–{Math.min(offset + limit, total)} of {total} alerts
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                className="rounded-lg px-3 py-1.5 text-xs text-slate-400 glass-card-static hover:text-cyan-400 transition-colors disabled:opacity-30"
              >
                Previous
              </button>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={!hasMore}
                className="rounded-lg px-3 py-1.5 text-xs text-slate-400 glass-card-static hover:text-cyan-400 transition-colors disabled:opacity-30"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function DetailField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-0.5">{label}</p>
      <p className={`text-xs text-slate-300 truncate ${mono ? 'font-mono' : ''}`}>{value}</p>
    </div>
  );
}
