import { useState, useEffect, useCallback } from 'react';
import { Activity, ShieldCheck, AlertTriangle, Database, RefreshCw, Radio, Zap } from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar,
} from 'recharts';
import { motion } from 'framer-motion';
import { useDashboard } from '../hooks/useDashboard';
import { useWebSocket } from '../hooks/useWebSocket';
import { fetchTimeSeries, fetchQualityTrend } from '../api/client';
import { StatCard } from '../components/StatCard';
import { SystemStatus } from '../components/SystemStatus';
import type { TimeSeriesPoint, QualityTrendPoint } from '../types/api';

/* eslint-disable @typescript-eslint/no-explicit-any */
const DarkTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.95)',
      border: '1px solid rgba(148, 163, 184, 0.15)',
      borderRadius: '10px',
      padding: '10px 14px',
      backdropFilter: 'blur(12px)',
    }}>
      <p style={{ color: '#94a3b8', fontSize: '11px', marginBottom: '6px' }}>{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} style={{ color: entry.color, fontSize: '13px', fontWeight: 600 }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
};

const QualityTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.95)',
      border: '1px solid rgba(148, 163, 184, 0.15)',
      borderRadius: '10px',
      padding: '10px 14px',
      backdropFilter: 'blur(12px)',
    }}>
      <p style={{ color: '#94a3b8', fontSize: '11px', marginBottom: '6px' }}>{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} style={{ color: entry.color || '#06b6d4', fontSize: '13px', fontWeight: 600 }}>
          Quality: {entry.value}%
        </p>
      ))}
    </div>
  );
};
/* eslint-enable @typescript-eslint/no-explicit-any */

export function DashboardPage() {
  const { stats, loading, error, refresh } = useDashboard();
  const { connected, events, status: wsStatus, lastEvent } = useWebSocket();

  const [timeSeries, setTimeSeries] = useState<TimeSeriesPoint[]>([]);
  const [qualityTrend, setQualityTrend] = useState<QualityTrendPoint[]>([]);
  const [chartLoading, setChartLoading] = useState(true);

  const loadCharts = useCallback(async () => {
    try {
      setChartLoading(true);
      const [tsData, qData] = await Promise.all([
        fetchTimeSeries('24h'),
        fetchQualityTrend(7),
      ]);
      setTimeSeries(tsData.series);
      setQualityTrend(qData.series);
    } catch {
      console.warn('Failed to load chart data');
    } finally {
      setChartLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCharts();
    const interval = setInterval(loadCharts, 60000);
    return () => clearInterval(interval);
  }, [loadCharts]);

  useEffect(() => {
    if (lastEvent?.type === 'inference_received') {
      refresh();
      loadCharts();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  const handleRefresh = useCallback(() => {
    refresh();
    loadCharts();
  }, [refresh, loadCharts]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="relative mx-auto h-12 w-12">
            <div className="absolute inset-0 rounded-full animate-ping opacity-20" style={{ background: 'var(--accent-primary)' }} />
            <RefreshCw className="relative h-12 w-12 animate-spin text-cyan-400" />
          </div>
          <p className="mt-4 text-sm text-slate-400">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center glass-card p-8">
          <AlertTriangle className="mx-auto h-10 w-10 text-red-400" />
          <p className="mt-3 text-sm text-red-300">{error}</p>
          <button
            onClick={handleRefresh}
            className="mt-4 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
            style={{ background: 'var(--gradient-brand)' }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const chartData = timeSeries.map((pt) => ({
    hour: pt.label,
    inferences: pt.inferences,
    redacted: pt.pii_redacted,
  }));

  const qualityData = qualityTrend.map((pt) => ({
    name: pt.label,
    quality: pt.quality,
  }));

  const minQuality = qualityData.length > 0
    ? Math.min(...qualityData.map((d) => d.quality))
    : 99;
  const qualityDomainMin = Math.max(0, Math.floor(minQuality) - 1);

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Real-time healthcare AI inference monitoring
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* WebSocket Status */}
          <div className="glass-card-static flex items-center gap-2 px-3.5 py-2">
            <div className={`h-2 w-2 rounded-full ${
              connected
                ? 'bg-emerald-400 live-dot'
                : wsStatus === 'connecting'
                  ? 'bg-amber-400 animate-pulse'
                  : 'bg-slate-500'
            }`} />
            <span className="text-xs font-medium text-slate-400">
              {connected ? 'Live' : wsStatus === 'connecting' ? 'Connecting' : 'Offline'}
            </span>
          </div>
          <button
            onClick={handleRefresh}
            className="glass-card-static flex items-center gap-2 px-4 py-2 text-sm text-slate-400 hover:text-cyan-400 transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="mb-8 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Inferences Today"
          value={stats.inferences.today.toLocaleString()}
          subtitle={`${stats.inferences.all_time.toLocaleString()} all time`}
          icon={<Activity className="h-5 w-5" />}
          color="cyan"
          delay={0}
        />
        <StatCard
          title="PHI Redacted"
          value={stats.pii_protection.total_redacted_today.toLocaleString()}
          subtitle="Sensitive data protected"
          icon={<ShieldCheck className="h-5 w-5" />}
          color="emerald"
          delay={0.1}
        />
        <StatCard
          title="Data Quality"
          value={`${(stats.data_quality.quality_rate * 100).toFixed(1)}%`}
          subtitle={`${stats.data_quality.issues_today} issues today`}
          icon={<Database className="h-5 w-5" />}
          color={stats.data_quality.quality_rate >= 0.99 ? 'emerald' : 'amber'}
          delay={0.2}
        />
        <StatCard
          title="Active Alerts"
          value={stats.alerts.active}
          subtitle={stats.alerts.active === 0 ? 'All systems nominal' : 'Needs attention'}
          icon={<AlertTriangle className="h-5 w-5" />}
          color={stats.alerts.active === 0 ? 'violet' : 'red'}
          delay={0.3}
        />
      </div>

      {/* Charts Row */}
      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Inference Volume Chart */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="col-span-2 glass-card-static p-6 chart-container"
        >
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-sm font-semibold text-slate-200">Inference Volume</h3>
              <p className="text-xs text-slate-500 mt-0.5">Last 24 hours, hourly</p>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-cyan-400" />
                <span className="text-[10px] text-slate-500">Inferences</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-emerald-400" />
                <span className="text-[10px] text-slate-500">PHI Redacted</span>
              </div>
            </div>
          </div>
          {chartLoading ? (
            <div className="flex h-[280px] items-center justify-center">
              <RefreshCw className="h-6 w-6 animate-spin text-slate-500" />
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorInfDark" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorRedDark" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.06)" />
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: '#64748b' }} stroke="rgba(148,163,184,0.1)" />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} stroke="rgba(148,163,184,0.1)" />
                <Tooltip content={<DarkTooltip />} />
                <Area
                  type="monotone"
                  dataKey="inferences"
                  stroke="#06b6d4"
                  fill="url(#colorInfDark)"
                  strokeWidth={2}
                  name="Inferences"
                  dot={false}
                  activeDot={{ r: 4, fill: '#06b6d4', stroke: '#0B0F19', strokeWidth: 2 }}
                />
                <Area
                  type="monotone"
                  dataKey="redacted"
                  stroke="#10b981"
                  fill="url(#colorRedDark)"
                  strokeWidth={2}
                  name="PHI Redacted"
                  dot={false}
                  activeDot={{ r: 4, fill: '#10b981', stroke: '#0B0F19', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </motion.div>

        {/* System Status */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <SystemStatus />
        </motion.div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Data Quality Chart */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          className="col-span-2 glass-card-static p-6 chart-container"
        >
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-sm font-semibold text-slate-200">Data Quality Rate</h3>
              <p className="text-xs text-slate-500 mt-0.5">Last 7 days, daily</p>
            </div>
          </div>
          {chartLoading ? (
            <div className="flex h-[200px] items-center justify-center">
              <RefreshCw className="h-6 w-6 animate-spin text-slate-500" />
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={qualityData}>
                <defs>
                  <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.8} />
                    <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0.6} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.06)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} stroke="rgba(148,163,184,0.1)" />
                <YAxis domain={[qualityDomainMin, 100.1]} tick={{ fontSize: 11, fill: '#64748b' }} stroke="rgba(148,163,184,0.1)" />
                <Tooltip content={<QualityTooltip />} />
                <Bar dataKey="quality" fill="url(#barGrad)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </motion.div>

        {/* Live Event Feed */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="glass-card-static p-5"
        >
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">
              Live Feed
            </h3>
            <div className="flex items-center gap-1.5">
              <Radio className={`h-3 w-3 ${connected ? 'text-emerald-400' : 'text-slate-600'}`} />
              <span className={`text-[9px] font-bold uppercase tracking-wider ${
                connected ? 'text-emerald-400' : 'text-slate-600'
              }`}>
                {connected ? 'Streaming' : 'Offline'}
              </span>
            </div>
          </div>

          <div className="max-h-[200px] space-y-2 overflow-y-auto">
            {events.length === 0 ? (
              <div className="flex h-[160px] flex-col items-center justify-center text-center">
                <div className="h-10 w-10 rounded-xl flex items-center justify-center bg-slate-800/50">
                  <Zap className="h-5 w-5 text-slate-600" />
                </div>
                <p className="mt-3 text-xs text-slate-500">
                  {connected ? 'Waiting for events...' : 'Connect to see live events'}
                </p>
              </div>
            ) : (
              events.slice(0, 15).map((evt, i) => {
                const data = evt.data as Record<string, unknown>;
                const time = data.timestamp
                  ? new Date(data.timestamp as string).toLocaleTimeString()
                  : '';

                if (evt.type === 'inference_received') {
                  return (
                    <div
                      key={`${data.inference_id}-${i}`}
                      className="flex items-start gap-2 rounded-lg px-3 py-2 transition-colors"
                      style={{ background: 'rgba(6, 182, 212, 0.04)', border: '1px solid rgba(6, 182, 212, 0.08)' }}
                    >
                      <Activity className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-400" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-slate-300">
                          Inference: {(data.prediction as number)?.toFixed(3)}
                        </p>
                        <p className="text-[10px] text-slate-500">
                          {data.model_name as string}
                          {(data.pii_redacted as number) > 0 && (
                            <span className="ml-1 text-emerald-400">
                              {data.pii_redacted as number} PHI
                            </span>
                          )}
                          {Boolean(data.is_outlier) && (
                            <span className="ml-1 text-amber-400">outlier</span>
                          )}
                        </p>
                      </div>
                      <span className="shrink-0 text-[10px] text-slate-600">{time}</span>
                    </div>
                  );
                }

                if (evt.type === 'alert_created') {
                  return (
                    <div
                      key={`alert-${i}`}
                      className="flex items-start gap-2 rounded-lg px-3 py-2"
                      style={{ background: 'rgba(245, 158, 11, 0.04)', border: '1px solid rgba(245, 158, 11, 0.1)' }}
                    >
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-amber-200">
                          {data.message as string}
                        </p>
                        <p className="text-[10px] text-amber-500/70">
                          {data.alert_type as string}
                        </p>
                      </div>
                      <span className="shrink-0 text-[10px] text-slate-600">{time}</span>
                    </div>
                  );
                }

                if (evt.type === 'connected') {
                  return (
                    <div
                      key={`connected-${i}`}
                      className="flex items-center gap-2 rounded-lg px-3 py-2"
                      style={{ background: 'rgba(16, 185, 129, 0.04)', border: '1px solid rgba(16, 185, 129, 0.1)' }}
                    >
                      <Radio className="h-3.5 w-3.5 text-emerald-400" />
                      <p className="text-xs text-emerald-300">
                        Connected to {data.tenant as string}
                      </p>
                    </div>
                  );
                }

                return null;
              })
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
