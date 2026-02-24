import { useState, useEffect, useCallback } from 'react';
import { Activity, ShieldCheck, AlertTriangle, Database, RefreshCw, Radio, Zap } from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar,
} from 'recharts';
import { useDashboard } from '../hooks/useDashboard';
import { useWebSocket } from '../hooks/useWebSocket';
import { fetchTimeSeries, fetchQualityTrend } from '../api/client';
import { StatCard } from '../components/StatCard';
import { SystemStatus } from '../components/SystemStatus';
import type { TimeSeriesPoint, QualityTrendPoint } from '../types/api';

export function DashboardPage() {
  const { stats, loading, error, refresh } = useDashboard();
  const { connected, events, status: wsStatus, lastEvent } = useWebSocket();

  // Chart data from real API (no more mock data)
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
      // Charts fail gracefully — stat cards still show
      console.warn('Failed to load chart data');
    } finally {
      setChartLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCharts();
    // Refresh charts every 60 seconds
    const interval = setInterval(loadCharts, 60000);
    return () => clearInterval(interval);
  }, [loadCharts]);

  // Auto-refresh stats when a new inference arrives via WebSocket
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
          <RefreshCw className="mx-auto h-8 w-8 animate-spin text-blue-500" />
          <p className="mt-3 text-sm text-slate-500">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="mx-auto h-8 w-8 text-red-500" />
          <p className="mt-3 text-sm text-red-600">{error}</p>
          <button
            onClick={handleRefresh}
            className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  // Transform API data for Recharts
  const chartData = timeSeries.map((pt) => ({
    hour: pt.label,
    inferences: pt.inferences,
    redacted: pt.pii_redacted,
  }));

  const qualityData = qualityTrend.map((pt) => ({
    name: pt.label,
    quality: pt.quality,
  }));

  // Dynamic Y-axis domain for quality chart
  const minQuality = qualityData.length > 0
    ? Math.min(...qualityData.map((d) => d.quality))
    : 99;
  const qualityDomainMin = Math.max(0, Math.floor(minQuality) - 1);

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Real-time overview of your healthcare AI inference monitoring
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* WebSocket connection status */}
          <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2">
            <div
              className={`h-2 w-2 rounded-full ${
                connected
                  ? 'bg-green-500 animate-pulse'
                  : wsStatus === 'connecting'
                    ? 'bg-yellow-400 animate-pulse'
                    : 'bg-slate-300'
              }`}
            />
            <span className="text-xs font-medium text-slate-500">
              {connected ? 'Live' : wsStatus === 'connecting' ? 'Connecting' : 'Offline'}
            </span>
          </div>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
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
          color="blue"
        />
        <StatCard
          title="PHI Redacted"
          value={stats.pii_protection.total_redacted_today.toLocaleString()}
          subtitle="Sensitive data protected"
          icon={<ShieldCheck className="h-5 w-5" />}
          color="green"
        />
        <StatCard
          title="Data Quality"
          value={`${(stats.data_quality.quality_rate * 100).toFixed(1)}%`}
          subtitle={`${stats.data_quality.issues_today} issues today`}
          icon={<Database className="h-5 w-5" />}
          color={stats.data_quality.quality_rate >= 0.99 ? 'green' : 'yellow'}
        />
        <StatCard
          title="Active Alerts"
          value={stats.alerts.active}
          subtitle={stats.alerts.active === 0 ? 'All clear' : 'Needs attention'}
          icon={<AlertTriangle className="h-5 w-5" />}
          color={stats.alerts.active === 0 ? 'slate' : 'red'}
        />
      </div>

      {/* Charts Row */}
      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Inference Volume Chart */}
        <div className="col-span-2 rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-500 uppercase tracking-wider">
            Inference Volume (24h)
          </h3>
          {chartLoading ? (
            <div className="flex h-[280px] items-center justify-center">
              <RefreshCw className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorInf" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorRed" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="hour" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#fff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '13px',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="inferences"
                  stroke="#3b82f6"
                  fill="url(#colorInf)"
                  strokeWidth={2}
                  name="Inferences"
                />
                <Area
                  type="monotone"
                  dataKey="redacted"
                  stroke="#22c55e"
                  fill="url(#colorRed)"
                  strokeWidth={2}
                  name="PHI Redacted"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* System Status */}
        <div>
          <SystemStatus />
        </div>
      </div>

      {/* Bottom Row: Data Quality + Live Feed */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Data Quality Chart */}
        <div className="col-span-2 rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-500 uppercase tracking-wider">
            Data Quality Rate (7-day)
          </h3>
          {chartLoading ? (
            <div className="flex h-[200px] items-center justify-center">
              <RefreshCw className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={qualityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis domain={[qualityDomainMin, 100.1]} tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#fff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '13px',
                  }}
                  formatter={(value) => [`${value}%`, 'Quality Rate']}
                />
                <Bar dataKey="quality" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Live Event Feed */}
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
              Live Feed
            </h3>
            <div className="flex items-center gap-1.5">
              <Radio className={`h-3.5 w-3.5 ${connected ? 'text-green-500' : 'text-slate-300'}`} />
              <span className="text-[10px] font-medium text-slate-400">
                {connected ? 'STREAMING' : 'DISCONNECTED'}
              </span>
            </div>
          </div>

          <div className="max-h-[200px] space-y-2 overflow-y-auto">
            {events.length === 0 ? (
              <div className="flex h-[160px] flex-col items-center justify-center text-center">
                <Zap className="h-6 w-6 text-slate-300" />
                <p className="mt-2 text-xs text-slate-400">
                  {connected
                    ? 'Waiting for events...'
                    : 'Connect to see live events'}
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
                      className="flex items-start gap-2 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
                    >
                      <Activity className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-500" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-slate-700">
                          Inference: {(data.prediction as number)?.toFixed(3)}
                        </p>
                        <p className="text-[10px] text-slate-400">
                          {data.model_name as string}
                          {(data.pii_redacted as number) > 0 && (
                            <span className="ml-1 text-green-600">
                              {data.pii_redacted as number} PHI redacted
                            </span>
                          )}
                          {Boolean(data.is_outlier) && (
                            <span className="ml-1 text-amber-600">outlier</span>
                          )}
                        </p>
                      </div>
                      <span className="shrink-0 text-[10px] text-slate-400">{time}</span>
                    </div>
                  );
                }

                if (evt.type === 'alert_created') {
                  return (
                    <div
                      key={`alert-${i}`}
                      className="flex items-start gap-2 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2"
                    >
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-amber-800">
                          {data.message as string}
                        </p>
                        <p className="text-[10px] text-amber-600">
                          {data.alert_type as string}
                        </p>
                      </div>
                      <span className="shrink-0 text-[10px] text-slate-400">{time}</span>
                    </div>
                  );
                }

                if (evt.type === 'connected') {
                  return (
                    <div
                      key={`connected-${i}`}
                      className="flex items-center gap-2 rounded-lg border border-green-100 bg-green-50 px-3 py-2"
                    >
                      <Radio className="h-3.5 w-3.5 text-green-500" />
                      <p className="text-xs text-green-700">
                        Connected to {data.tenant as string}
                      </p>
                    </div>
                  );
                }

                return null;
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
