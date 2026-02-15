'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
    Users,
    Search,
    RefreshCw,
    Loader2,
    ChevronRight,
    Activity,
} from 'lucide-react';

interface Patient {
    patient_hash: string;
    patient_name: string;
    total_workflows: number;
    workflows: { workflow_id: string; created_at: string }[];
}

export default function PatientsPage() {
    const [patients, setPatients] = useState<Patient[]>([]);
    const [filtered, setFiltered] = useState<Patient[]>([]);
    const [search, setSearch] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selected, setSelected] = useState<Patient | null>(null);

    const fetchPatients = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/api/medvoice/patients');
            if (!res.ok) throw new Error(`Failed to load (${res.status})`);
            const data = await res.json();
            setPatients(data.patients || []);
            setFiltered(data.patients || []);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPatients();
    }, []);

    useEffect(() => {
        const q = search.toLowerCase();
        setFiltered(
            patients.filter(
                (p) =>
                    p.patient_name.toLowerCase().includes(q) ||
                    p.patient_hash.toLowerCase().includes(q)
            )
        );
    }, [search, patients]);

    return (
        <div className="p-4 sm:p-6 lg:p-8 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
                        Patient Records
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        {patients.length} patient{patients.length !== 1 ? 's' : ''} on record
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchPatients} disabled={loading}>
                    <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </Button>
            </div>

            {/* Search */}
            <div className="relative max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search by name or patient hash..."
                    className="pl-10"
                />
            </div>

            {error && (
                <div className="p-4 rounded-lg bg-red-50 text-red-800 text-sm">{error}</div>
            )}

            {/* Patient List + Detail Split View */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                {/* List */}
                <div className="lg:col-span-2 space-y-2">
                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                        </div>
                    ) : filtered.length === 0 ? (
                        <div className="text-center py-12 text-muted-foreground">
                            <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
                            <p className="text-sm font-medium">No patients found</p>
                        </div>
                    ) : (
                        filtered.map((patient) => (
                            <button
                                key={patient.patient_hash}
                                onClick={() => setSelected(patient)}
                                className={`w-full text-left p-4 rounded-lg border transition-colors ${selected?.patient_hash === patient.patient_hash
                                        ? 'border-primary bg-accent'
                                        : 'border-border hover:bg-accent/50'
                                    }`}
                            >
                                <div className="flex items-center justify-between">
                                    <div className="min-w-0">
                                        <p className="font-medium text-sm truncate">
                                            {patient.patient_name}
                                        </p>
                                        <p className="text-xs text-muted-foreground font-mono mt-0.5">
                                            {patient.patient_hash}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                        <span className="text-xs text-muted-foreground">
                                            {patient.total_workflows} workflow{patient.total_workflows !== 1 ? 's' : ''}
                                        </span>
                                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                                    </div>
                                </div>
                            </button>
                        ))
                    )}
                </div>

                {/* Detail Panel */}
                <div className="lg:col-span-3">
                    {selected ? (
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold text-sm">
                                        {selected.patient_name
                                            .split(' ')
                                            .map((n) => n[0])
                                            .join('')
                                            .slice(0, 2)
                                            .toUpperCase()}
                                    </div>
                                    <div>
                                        <p className="text-lg">{selected.patient_name}</p>
                                        <p className="text-xs font-mono text-muted-foreground font-normal">
                                            Hash: {selected.patient_hash}
                                        </p>
                                    </div>
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
                                    <Activity className="w-4 h-4" />
                                    Consultation History ({selected.total_workflows})
                                </h3>
                                <div className="space-y-2 max-h-96 overflow-y-auto">
                                    {selected.workflows.length === 0 ? (
                                        <p className="text-sm text-muted-foreground py-4 text-center">
                                            No consultations yet
                                        </p>
                                    ) : (
                                        selected.workflows.map((wf) => (
                                            <a
                                                key={wf.workflow_id}
                                                href={`/dashboard/consultations?wf=${wf.workflow_id}`}
                                                className="block p-3 rounded-md border border-border hover:bg-accent/50 transition-colors"
                                            >
                                                <code className="text-xs font-mono break-all">
                                                    {wf.workflow_id}
                                                </code>
                                                <p className="text-xs text-muted-foreground mt-1">
                                                    {new Date(wf.created_at).toLocaleString()}
                                                </p>
                                            </a>
                                        ))
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    ) : (
                        <div className="flex items-center justify-center h-64 text-muted-foreground">
                            <div className="text-center">
                                <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
                                <p className="text-sm">Select a patient to view details</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
