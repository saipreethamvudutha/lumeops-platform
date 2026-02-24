import { useEffect, useState } from 'react';
import { CheckCircle, XCircle, Loader } from 'lucide-react';
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
      <div className="rounded-xl border border-red-200 bg-red-50 p-5">
        <div className="flex items-center gap-2">
          <XCircle className="h-5 w-5 text-red-600" />
          <span className="font-semibold text-red-700">System Offline</span>
        </div>
        <p className="mt-1 text-sm text-red-600">Cannot reach LumeOps API</p>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
        <div className="flex items-center gap-2">
          <Loader className="h-5 w-5 animate-spin text-slate-500" />
          <span className="text-slate-600">Checking system status...</span>
        </div>
      </div>
    );
  }

  const isHealthy = health.status === 'ready';
  const services = health.services;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="mb-3 text-sm font-semibold text-slate-500 uppercase tracking-wider">System Status</h3>
      <div className="space-y-2">
        <StatusRow label="API" status={isHealthy ? 'ok' : 'error'} />
        {services && (
          <>
            <StatusRow label="Database" status={services.database} />
            <StatusRow label="Redis" status={services.redis} />
          </>
        )}
        <div className="mt-3 border-t border-slate-100 pt-3">
          <p className="text-xs text-slate-400">Version {health.version}</p>
          <p className="text-xs text-slate-400">
            Last checked {new Date(health.timestamp).toLocaleTimeString()}
          </p>
        </div>
      </div>
    </div>
  );
}

function StatusRow({ label, status }: { label: string; status: string }) {
  const isOk = status === 'ok';
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-slate-600">{label}</span>
      <div className="flex items-center gap-1.5">
        {isOk ? (
          <CheckCircle className="h-4 w-4 text-emerald-500" />
        ) : (
          <XCircle className="h-4 w-4 text-red-500" />
        )}
        <span className={`text-sm font-medium ${isOk ? 'text-emerald-600' : 'text-red-600'}`}>
          {isOk ? 'Healthy' : 'Error'}
        </span>
      </div>
    </div>
  );
}
