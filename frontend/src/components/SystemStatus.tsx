import { useEffect, useState } from 'react';
import { CheckCircle, XCircle, Loader, Server, Database, Cpu } from 'lucide-react';
import { fetchHealth } from '../api/client';
import type { HealthStatus } from '../types/api';

export function SystemStatus() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const data = await fetchHealth();
        setHealth(data);
        setError(false);
      } catch {
        setError(true);
      }
    };
    check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, []);

  if (error) {
    return (
      <div className="glass-card-static p-5" style={{ borderColor: 'rgba(239, 68, 68, 0.2)' }}>
        <div className="flex items-center gap-2">
          <XCircle className="h-5 w-5 text-red-400" />
          <span className="font-semibold text-red-300">System Offline</span>
        </div>
        <p className="mt-1 text-sm text-red-400/70">Cannot reach LumeOps API</p>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="glass-card-static p-5">
        <div className="flex items-center gap-2">
          <Loader className="h-5 w-5 animate-spin text-slate-400" />
          <span className="text-slate-400">Checking system status...</span>
        </div>
      </div>
    );
  }

  const isHealthy = health.status === 'ready';
  const services = health.services;

  return (
    <div className="glass-card-static p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">
          Infrastructure
        </h3>
        <div className="flex items-center gap-1.5">
          <div className={`h-1.5 w-1.5 rounded-full ${isHealthy ? 'bg-emerald-400 live-dot' : 'bg-red-400'}`} />
          <span className={`text-[10px] font-semibold uppercase tracking-wider ${isHealthy ? 'text-emerald-400' : 'text-red-400'}`}>
            {isHealthy ? 'All Systems Go' : 'Issues Detected'}
          </span>
        </div>
      </div>
      <div className="space-y-3">
        <StatusRow label="API Server" icon={Server} status={isHealthy ? 'ok' : 'error'} />
        {services && (
          <>
            <StatusRow label="PostgreSQL" icon={Database} status={services.database} />
            <StatusRow label="Redis Cache" icon={Cpu} status={services.redis} />
          </>
        )}
        <div className="mt-4 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center justify-between">
            <p className="text-[10px] text-slate-500">v{health.version}</p>
            <p className="text-[10px] text-slate-600">
              {new Date(health.timestamp).toLocaleTimeString()}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusRow({ label, icon: Icon, status }: { label: string; icon: typeof Server; status: string }) {
  const isOk = status === 'ok';
  return (
    <div className="flex items-center justify-between py-1">
      <div className="flex items-center gap-2.5">
        <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${
          isOk ? 'bg-emerald-500/10' : 'bg-red-500/10'
        }`}>
          <Icon className={`h-3.5 w-3.5 ${isOk ? 'text-emerald-400' : 'text-red-400'}`} />
        </div>
        <span className="text-sm text-slate-300">{label}</span>
      </div>
      <div className="flex items-center gap-1.5">
        {isOk ? (
          <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <XCircle className="h-3.5 w-3.5 text-red-400" />
        )}
        <span className={`text-xs font-medium ${isOk ? 'text-emerald-400' : 'text-red-400'}`}>
          {isOk ? 'Healthy' : 'Error'}
        </span>
      </div>
    </div>
  );
}
