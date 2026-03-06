'use client';

import { useState, useCallback, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
    Search,
    RefreshCw,
    Clock,
    CheckCircle2,
    XCircle,
    Loader2,
    ChevronDown,
    ChevronUp,
    FileText,
} from 'lucide-react';
import { TranscriptionSection, MedicalResultsSection, RawDataSection } from './result-sections';
import type { BackendWorkflowResult } from '@/lib/medvoice/types';

interface Workflow {
    workflow_id: string;
    status: string;
    start_time?: string;
    close_time?: string;
    result?: Record<string, unknown>;
}

const statusStyles: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
    RUNNING: { icon: Loader2, color: 'text-blue-600', bg: 'bg-blue-50' },
    COMPLETED: { icon: CheckCircle2, color: 'text-emerald-600', bg: 'bg-emerald-50' },
    FAILED: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50' },
    TERMINATED: { icon: XCircle, color: 'text-gray-600', bg: 'bg-gray-50' },
    TIMED_OUT: { icon: Clock, color: 'text-amber-600', bg: 'bg-amber-50' },
};

function ConsultationsClient() {
    const searchParams = useSearchParams();
    const initialWf = searchParams.get('wf') ?? '';

    const [searchId, setSearchId] = useState(initialWf);
    const [workflows, setWorkflows] = useState<Workflow[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [workflowResults, setWorkflowResults] = useState<Record<string, unknown>>({});

    const searchWorkflow = useCallback(async (id?: string) => {
        const query = (id ?? searchId).trim();
        if (!query) return;
        setLoading(true);
        setError(null);

        try {
            const res = await fetch(`/api/medvoice/workflows/${query}/status`);
            if (!res.ok) {
                if (res.status === 404) {
                    setError('Workflow not found');
                    setWorkflows([]);
                    return;
                }
                throw new Error(`Search failed (${res.status})`);
            }
            const data = await res.json();
            setWorkflows([data]);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setLoading(false);
        }
    }, [searchId]);

    // Auto-search when navigated with ?wf= query parameter
    useEffect(() => {
        if (initialWf) {
            searchWorkflow(initialWf);
        }
        // Only run on initial mount
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const fetchResult = async (workflowId: string) => {
        if (workflowResults[workflowId]) {
            setExpandedId(expandedId === workflowId ? null : workflowId);
            return;
        }

        try {
            const res = await fetch(`/api/medvoice/workflows/${workflowId}/result`);
            if (res.ok) {
                const data = await res.json();
                setWorkflowResults((prev) => ({ ...prev, [workflowId]: data }));
            }
        } catch {
            // Result not available
        }
        setExpandedId(expandedId === workflowId ? null : workflowId);
    };

    const formatDate = (dateStr?: string) => {
        if (!dateStr) return '—';
        return new Date(dateStr).toLocaleString();
    };

    return (
        <div className="p-4 sm:p-6 lg:p-8 space-y-6">
            <div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
                    My Consultations
                </h1>
                <p className="text-muted-foreground mt-1">
                    Search and monitor consultation workflows
                </p>
            </div>

            {/* Search Bar */}
            <Card>
                <CardContent className="pt-6">
                    <div className="flex gap-2">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                value={searchId}
                                onChange={(e) => setSearchId(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && searchWorkflow()}
                                placeholder="Search by Workflow ID or Patient Hash..."
                                className="pl-10"
                            />
                        </div>
                        <Button onClick={() => searchWorkflow()} disabled={loading} aria-label="Search workflow">
                            {loading ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                                <Search className="w-4 h-4" />
                            )}
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Error */}
            {error && (
                <div className="flex items-center gap-3 p-4 rounded-lg bg-red-50 dark:bg-red-950/50 text-red-800 dark:text-red-300">
                    <XCircle className="w-5 h-5" />
                    <p className="text-sm">{error}</p>
                </div>
            )}

            {/* Workflow Results */}
            <div className="space-y-3">
                {workflows.map((wf) => {
                    const style = statusStyles[wf.status] || statusStyles.TERMINATED;
                    const StatusIcon = style.icon;
                    const isExpanded = expandedId === wf.workflow_id;
                    const result = workflowResults[wf.workflow_id] as Record<string, unknown> | undefined;

                    return (
                        <Card key={wf.workflow_id}>
                            <CardContent className="pt-6">
                                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                                    {/* Status badge */}
                                    <div
                                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${style.color} ${style.bg} w-fit`}
                                    >
                                        <StatusIcon
                                            className={`w-3.5 h-3.5 ${wf.status === 'RUNNING' ? 'animate-spin' : ''}`}
                                        />
                                        {wf.status}
                                    </div>

                                    {/* Workflow ID */}
                                    <code className="text-sm font-mono text-foreground break-all flex-1">
                                        {wf.workflow_id}
                                    </code>

                                    {/* Actions */}
                                    <div className="flex gap-2">
                                        {wf.status === 'RUNNING' && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => searchWorkflow()}
                                            >
                                                <RefreshCw className="w-3.5 h-3.5 mr-1" />
                                                Poll
                                            </Button>
                                        )}
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => fetchResult(wf.workflow_id)}
                                        >
                                            <FileText className="w-3.5 h-3.5 mr-1" />
                                            {isExpanded ? 'Hide' : 'Details'}
                                            {isExpanded ? (
                                                <ChevronUp className="w-3.5 h-3.5 ml-1" />
                                            ) : (
                                                <ChevronDown className="w-3.5 h-3.5 ml-1" />
                                            )}
                                        </Button>
                                    </div>
                                </div>

                                {/* Timestamps */}
                                <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                                    <span>Started: {formatDate(wf.start_time)}</span>
                                    {wf.close_time && <span>Completed: {formatDate(wf.close_time)}</span>}
                                </div>

                                {/* Expanded Result */}
                                {isExpanded && result && (() => {
                                    const r = result as BackendWorkflowResult;
                                    const hasMedical =
                                        (r.workflow_type && r.workflow_type.toLowerCase().includes('medical')) ||
                                        !!r.dialogue_transformation;
                                    return (
                                        <div className="mt-4 border-t pt-4">
                                            <Tabs defaultValue="transcription">
                                                <TabsList>
                                                    <TabsTrigger value="transcription">📄 Transcription</TabsTrigger>
                                                    {hasMedical && (
                                                        <TabsTrigger value="medical">🏥 Medical Results</TabsTrigger>
                                                    )}
                                                    <TabsTrigger value="raw">📊 Raw Data</TabsTrigger>
                                                </TabsList>
                                                <TabsContent value="transcription" className="mt-3">
                                                    <TranscriptionSection result={r} />
                                                </TabsContent>
                                                {hasMedical && (
                                                    <TabsContent value="medical" className="mt-3">
                                                        <MedicalResultsSection result={r} />
                                                    </TabsContent>
                                                )}
                                                <TabsContent value="raw" className="mt-3">
                                                    <RawDataSection result={r} workflowId={wf.workflow_id} />
                                                </TabsContent>
                                            </Tabs>
                                        </div>
                                    );
                                })()}
                            </CardContent>
                        </Card>
                    );
                })}

                {workflows.length === 0 && !loading && !error && (
                    <div className="text-center py-12 text-muted-foreground">
                        <Search className="w-12 h-12 mx-auto mb-3 opacity-30" />
                        <p className="text-sm font-medium">No consultations found</p>
                        <p className="text-xs mt-1">
                            Enter a Workflow ID above to search
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}

export default function ConsultationsPage() {
    return (
        <Suspense fallback={
            <div className="p-4 sm:p-6 lg:p-8 flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
        }>
            <ConsultationsClient />
        </Suspense>
    );
}
