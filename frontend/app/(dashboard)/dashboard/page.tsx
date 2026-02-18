'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity, Users, Upload, Clock, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface DashboardStats {
  totalPatients: number;
  totalWorkflows: number;
  systemStatus: 'healthy' | 'degraded' | 'offline';
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthRes, statsRes] = await Promise.allSettled([
        fetch('/api/medvoice/health'),
        fetch('/api/medvoice/stats'),
      ]);

      let systemStatus: 'healthy' | 'degraded' | 'offline' = 'offline';
      if (healthRes.status === 'fulfilled' && healthRes.value.ok) {
        systemStatus = 'healthy';
      } else if (healthRes.status === 'fulfilled') {
        systemStatus = 'degraded';
      }

      let totalPatients = 0;
      let totalWorkflows = 0;
      if (statsRes.status === 'fulfilled' && statsRes.value.ok) {
        const data = await statsRes.value.json();
        totalPatients = data.total_patients || 0;
        totalWorkflows = data.total_workflows || 0;
      }

      setStats({ totalPatients, totalWorkflows, systemStatus });
    } catch (err) {
      setError('Unable to connect to MedVoice backend');
      setStats({ totalPatients: 0, totalWorkflows: 0, systemStatus: 'offline' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  const statusConfig = {
    healthy: { label: 'All Systems Operational', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-950/50', icon: CheckCircle2 },
    degraded: { label: 'Partial Outage', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-950/50', icon: AlertCircle },
    offline: { label: 'Backend Offline', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-950/50', icon: AlertCircle },
  };

  const status = stats ? statusConfig[stats.systemStatus] : statusConfig.offline;
  const StatusIcon = status.icon;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Welcome to MedVoice Clinical Portal
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchStats}
          disabled={loading}
          className="w-fit"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* System Status Banner */}
      <div className={`flex items-center gap-3 px-4 py-3 rounded-lg ${status.bg}`}>
        <StatusIcon className={`w-5 h-5 ${status.color}`} />
        <span className={`text-sm font-medium ${status.color}`}>
          {status.label}
        </span>
        {error && (
          <span className="text-xs text-muted-foreground ml-auto">{error}</span>
        )}
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Patients
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? '—' : stats?.totalPatients ?? 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Consultations
            </CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? '—' : stats?.totalWorkflows ?? 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              System Health
            </CardTitle>
            <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-lg font-semibold ${status.color}`}>
              {loading ? '—' : stats?.systemStatus === 'healthy' ? 'Healthy' : stats?.systemStatus === 'degraded' ? 'Warning' : 'Offline'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Auto-Refresh
            </CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-lg font-semibold text-muted-foreground">
              30s
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Quick Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <a
              href="/dashboard/upload"
              className="flex items-center gap-3 p-4 rounded-lg border border-border hover:bg-accent transition-colors cursor-pointer"
            >
              <Upload className="w-8 h-8 text-primary" />
              <div>
                <p className="font-medium text-sm">Upload Consultation</p>
                <p className="text-xs text-muted-foreground">New audio recording</p>
              </div>
            </a>
            <a
              href="/dashboard/consultations"
              className="flex items-center gap-3 p-4 rounded-lg border border-border hover:bg-accent transition-colors cursor-pointer"
            >
              <Activity className="w-8 h-8 text-primary" />
              <div>
                <p className="font-medium text-sm">My Consultations</p>
                <p className="text-xs text-muted-foreground">Monitor workflows</p>
              </div>
            </a>
            <a
              href="/dashboard/patients"
              className="flex items-center gap-3 p-4 rounded-lg border border-border hover:bg-accent transition-colors cursor-pointer"
            >
              <Users className="w-8 h-8 text-primary" />
              <div>
                <p className="font-medium text-sm">Patient Records</p>
                <p className="text-xs text-muted-foreground">Browse all patients</p>
              </div>
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
