import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Shield, Key, Settings, Activity, List,
  Heart, ChevronRight, Webhook, Bell, Brain, ScrollText,
} from 'lucide-react';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', description: 'Overview & metrics' },
  { to: '/inferences', icon: List, label: 'Inference Log', description: 'Browse records' },
  { to: '/models', icon: Brain, label: 'Models', description: 'Performance & drift' },
  { to: '/alerts', icon: Bell, label: 'Alerts', description: 'Monitor & resolve' },
  { to: '/compliance', icon: Shield, label: 'Compliance', description: 'HIPAA reports' },
  { to: '/audit-logs', icon: ScrollText, label: 'Audit Trail', description: 'Event history' },
  { to: '/api-keys', icon: Key, label: 'API Keys', description: 'Authentication' },
  { to: '/webhooks', icon: Webhook, label: 'Webhooks', description: 'Event notifications' },
  { to: '/settings', icon: Settings, label: 'Settings', description: 'Configuration' },
];

export function Layout() {
  const location = useLocation();

  return (
    <div className="flex h-screen" style={{ background: 'var(--bg-primary)' }}>
      {/* Sidebar */}
      <aside className="flex w-72 flex-col" style={{
        background: 'linear-gradient(180deg, rgba(17, 24, 39, 0.95) 0%, rgba(11, 15, 25, 0.98) 100%)',
        borderRight: '1px solid var(--border-subtle)',
      }}>
        {/* Logo */}
        <div className="flex h-[72px] items-center gap-3 px-6" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl"
            style={{ background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.15), rgba(139, 92, 246, 0.15))' }}>
            <Activity className="h-5 w-5 text-cyan-400" />
            <div className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-emerald-400 live-dot" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-slate-100 tracking-tight">LumeOps</span>
              <span className="rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest text-gradient"
                style={{ background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.12), rgba(139, 92, 246, 0.12))',
                  border: '1px solid rgba(6, 182, 212, 0.2)', borderRadius: '6px',
                  WebkitBackgroundClip: 'unset', WebkitTextFillColor: '#06b6d4' }}>
                Pro
              </span>
            </div>
            <span className="text-[10px] font-medium text-slate-500 tracking-wide">Healthcare AI Platform</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3 py-5">
          <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-500">
            Navigation
          </p>
          {navItems.map(({ to, icon: Icon, label, description }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'sidebar-link group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200',
                  isActive
                    ? 'sidebar-link-active bg-[rgba(6,182,212,0.08)] text-cyan-300'
                    : 'text-slate-400 hover:bg-[rgba(148,163,184,0.06)] hover:text-slate-200'
                )
              }
            >
              {({ isActive }) => (
                <>
                  <div className={clsx(
                    'flex h-9 w-9 items-center justify-center rounded-lg transition-all duration-200',
                    isActive
                      ? 'bg-[rgba(6,182,212,0.15)] text-cyan-400'
                      : 'bg-[rgba(148,163,184,0.06)] text-slate-500 group-hover:text-slate-300'
                  )}>
                    <Icon className="h-[18px] w-[18px]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium leading-none">{label}</p>
                    <p className={clsx(
                      'mt-0.5 text-[10px] transition-colors',
                      isActive ? 'text-cyan-400/60' : 'text-slate-600'
                    )}>{description}</p>
                  </div>
                  {isActive && (
                    <ChevronRight className="h-3.5 w-3.5 text-cyan-500/50" />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 pb-5">
          <div className="rounded-xl p-4" style={{
            background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.06), rgba(139, 92, 246, 0.06))',
            border: '1px solid var(--border-subtle)',
          }}>
            <div className="flex items-center gap-2 mb-2">
              <Heart className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-[11px] font-semibold text-emerald-400">HIPAA Compliant</span>
            </div>
            <p className="text-[10px] leading-relaxed text-slate-500">
              Enterprise-grade security with end-to-end encryption and audit trail.
            </p>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto" style={{ background: 'var(--bg-primary)' }}>
        {/* Top ambient glow */}
        <div className="pointer-events-none fixed top-0 left-72 right-0 h-64 z-0"
          style={{ background: 'var(--gradient-glow)' }} />

        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="relative z-10"
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
