import type { ReactNode } from 'react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  color?: 'cyan' | 'emerald' | 'amber' | 'red' | 'violet' | 'slate';
  delay?: number;
}

const glowMap = {
  cyan: 'stat-glow-cyan',
  emerald: 'stat-glow-emerald',
  amber: 'stat-glow-amber',
  red: 'stat-glow-red',
  violet: 'stat-glow-violet',
  slate: '',
};

const iconBgMap = {
  cyan: 'from-cyan-500/20 to-cyan-400/5 text-cyan-400',
  emerald: 'from-emerald-500/20 to-emerald-400/5 text-emerald-400',
  amber: 'from-amber-500/20 to-amber-400/5 text-amber-400',
  red: 'from-red-500/20 to-red-400/5 text-red-400',
  violet: 'from-violet-500/20 to-violet-400/5 text-violet-400',
  slate: 'from-slate-500/20 to-slate-400/5 text-slate-400',
};

const valueColorMap = {
  cyan: 'text-cyan-50',
  emerald: 'text-emerald-50',
  amber: 'text-amber-50',
  red: 'text-red-50',
  violet: 'text-violet-50',
  slate: 'text-slate-50',
};

export function StatCard({
  title, value, subtitle, icon, trend, trendValue, color = 'cyan', delay = 0,
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: 'easeOut' }}
      className={clsx('glass-card p-5 relative overflow-hidden', glowMap[color])}
    >
      {/* Subtle gradient overlay */}
      <div className="absolute inset-0 opacity-30 pointer-events-none"
        style={{ background: `radial-gradient(ellipse at top right, ${
          color === 'cyan' ? 'rgba(6,182,212,0.08)' :
          color === 'emerald' ? 'rgba(16,185,129,0.08)' :
          color === 'amber' ? 'rgba(245,158,11,0.08)' :
          color === 'red' ? 'rgba(239,68,68,0.08)' :
          color === 'violet' ? 'rgba(139,92,246,0.08)' :
          'rgba(148,163,184,0.04)'
        }, transparent 70%)` }} />

      <div className="relative flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{title}</p>
          <p className={clsx('mt-2 text-3xl font-bold tracking-tight', valueColorMap[color])}>
            {value}
          </p>
          <div className="mt-2 flex items-center gap-2">
            {trend && trend !== 'neutral' && (
              <span className={clsx(
                'inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold',
                trend === 'up' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
              )}>
                {trend === 'up' ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                {trendValue}
              </span>
            )}
            {subtitle && (
              <p className="text-[11px] text-slate-500 truncate">{subtitle}</p>
            )}
          </div>
        </div>
        <div className={clsx(
          'flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br',
          iconBgMap[color]
        )}>
          {icon}
        </div>
      </div>
    </motion.div>
  );
}
