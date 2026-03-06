'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ChevronDown, ChevronUp, Download, FileText, AlertTriangle, Stethoscope, Shield, Database, ClipboardList } from 'lucide-react';
import { useState } from 'react';
import type {
    BackendWorkflowResult,
    DialogueTransformation,
    PHIDetection,
    EntityExtraction,
    SOAPGeneration,
    VectorStorage,
    WhisperXFinal,
    SpeakerMappingEntry,
} from '@/lib/medvoice/types';

// ============================================================
// Collapsible Section (replaces missing accordion component)
// ============================================================

function CollapsibleSection({
    title,
    icon: Icon,
    defaultOpen = false,
    children,
}: {
    title: string;
    icon?: React.ElementType;
    defaultOpen?: boolean;
    children: React.ReactNode;
}) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className="border rounded-lg">
            <button
                onClick={() => setOpen(!open)}
                className="w-full flex items-center justify-between p-3 text-sm font-medium hover:bg-muted/50 transition-colors rounded-lg"
            >
                <span className="flex items-center gap-2">
                    {Icon && <Icon className="w-4 h-4 text-muted-foreground" />}
                    {title}
                </span>
                {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {open && <div className="px-3 pb-3 pt-0">{children}</div>}
        </div>
    );
}

// ============================================================
// Transcription Section
// ============================================================

export function TranscriptionSection({ result }: { result: BackendWorkflowResult }) {
    const dialogue = result.dialogue_transformation;
    const whisperx = result.whisperx_final as WhisperXFinal | undefined;

    // Medical workflow: use dialogue_transformation
    if (dialogue) {
        return <DialogueDisplay dialogue={dialogue} />;
    }

    // Non-medical workflow: use whisperx_final segments
    if (whisperx?.segments?.length) {
        const fullText = whisperx.segments.map((s) => s.text.trim()).join(' ');
        return (
            <div className="space-y-3">
                <p className="text-sm text-muted-foreground">Transcription-only result (no medical processing)</p>
                <div className="bg-muted/50 rounded-lg p-4 text-sm leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">
                    {fullText}
                </div>
            </div>
        );
    }

    return <p className="text-sm text-muted-foreground">No transcription data available.</p>;
}

function DialogueDisplay({ dialogue }: { dialogue: DialogueTransformation }) {
    // Prefer full_transcript_markdown (pre-formatted speaker-attributed text)
    if (dialogue.full_transcript_markdown) {
        return (
            <div className="space-y-4">
                <div
                    className="prose prose-sm dark:prose-invert max-w-none bg-muted/30 rounded-lg p-4 max-h-96 overflow-y-auto"
                    dangerouslySetInnerHTML={{ __html: markdownToHtml(dialogue.full_transcript_markdown) }}
                />

                {/* Full text in collapsible */}
                {dialogue.full_transcript && (
                    <CollapsibleSection title="📝 Full Text" icon={FileText}>
                        <div className="bg-muted/50 rounded-lg p-3 text-sm leading-relaxed max-h-64 overflow-y-auto whitespace-pre-wrap">
                            {dialogue.full_transcript}
                        </div>
                    </CollapsibleSection>
                )}

                {/* Speaker mapping */}
                {dialogue.speaker_mapping && (
                    <CollapsibleSection title="👥 Speaker Mapping">
                        <SpeakerMapping mapping={dialogue.speaker_mapping} />
                    </CollapsibleSection>
                )}
            </div>
        );
    }

    // Fallback: dialogue array
    if (dialogue.dialogue?.length) {
        return (
            <div className="space-y-4">
                <div className="space-y-2 max-h-96 overflow-y-auto">
                    {dialogue.dialogue.map((entry, i) => (
                        <div key={i} className="text-sm">
                            <span className="font-semibold capitalize">{entry.speaker_role}:</span>{' '}
                            <span>{entry.text}</span>
                        </div>
                    ))}
                </div>
                {dialogue.speaker_mapping && (
                    <CollapsibleSection title="👥 Speaker Mapping">
                        <SpeakerMapping mapping={dialogue.speaker_mapping} />
                    </CollapsibleSection>
                )}
            </div>
        );
    }

    return <p className="text-sm text-muted-foreground">No dialogue data available.</p>;
}

function SpeakerMapping({ mapping }: { mapping: Record<string, SpeakerMappingEntry | string> }) {
    return (
        <ul className="space-y-1 text-sm">
            {Object.entries(mapping).map(([speakerId, data]) => {
                if (typeof data === 'object' && data !== null) {
                    const entry = data as SpeakerMappingEntry;
                    return (
                        <li key={speakerId}>
                            <span className="font-medium">{speakerId}</span>: {entry.role}
                            {entry.confidence != null && (
                                <span className="text-muted-foreground"> ({Math.round(entry.confidence * 100)}% confidence)</span>
                            )}
                        </li>
                    );
                }
                return (
                    <li key={speakerId}>
                        <span className="font-medium">{speakerId}</span>: {String(data)}
                    </li>
                );
            })}
        </ul>
    );
}

/** Minimal markdown-to-html for bold speaker labels. */
function markdownToHtml(md: string): string {
    return md
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br/>');
}

// ============================================================
// Medical Results Section
// ============================================================

export function MedicalResultsSection({ result }: { result: BackendWorkflowResult }) {
    const hasSomething =
        result.dialogue_transformation ||
        result.phi_detection ||
        result.entity_extraction ||
        result.soap_generation ||
        result.vector_storage;

    if (!hasSomething) {
        return <p className="text-sm text-muted-foreground">No medical processing results available.</p>;
    }

    return (
        <div className="space-y-4">
            {/* Dialogue */}
            {result.dialogue_transformation && (
                <Card>
                    <CardHeader className="py-3 px-4">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Stethoscope className="w-4 h-4" /> Dialogue
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="px-4 pb-4 pt-0">
                        <DialogueDisplay dialogue={result.dialogue_transformation} />
                    </CardContent>
                </Card>
            )}

            {/* PHI Detection */}
            {result.phi_detection && <PHISection data={result.phi_detection} />}

            {/* Entity Extraction */}
            {result.entity_extraction && <EntitySection data={result.entity_extraction} />}

            {/* SOAP Note */}
            {result.soap_generation && <SOAPSection data={result.soap_generation} />}

            {/* Vector Storage */}
            {result.vector_storage && <VectorStorageSection data={result.vector_storage} />}
        </div>
    );
}

function PHISection({ data }: { data: PHIDetection }) {
    const entities = data.entities ?? [];
    const detected = data.phi_detected && entities.length > 0;

    return (
        <Card>
            <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Shield className="w-4 h-4" /> PHI Detection
                </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
                {detected ? (
                    <div className="space-y-2">
                        <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 text-sm">
                            <AlertTriangle className="w-4 h-4" />
                            {entities.length} PHI entit{entities.length === 1 ? 'y' : 'ies'} detected
                        </div>
                        {groupByType(entities).map(([type, items]) => (
                            <CollapsibleSection key={type} title={`${formatLabel(type)} (${items.length})`}>
                                <ul className="space-y-1 text-sm">
                                    {items.map((e, i) => (
                                        <li key={i}>
                                            <span className="font-medium">{e.text}</span>
                                            <span className="text-muted-foreground text-xs ml-2">
                                                {Math.round((e.confidence ?? 0) * 100)}% confidence
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            </CollapsibleSection>
                        ))}
                    </div>
                ) : (
                    <p className="text-sm text-emerald-600 dark:text-emerald-400">✓ No PHI detected</p>
                )}
            </CardContent>
        </Card>
    );
}

function EntitySection({ data }: { data: EntityExtraction }) {
    const entities = data.entities ?? [];

    if (entities.length === 0 && !data.entities_by_speaker) {
        return (
            <Card>
                <CardHeader className="py-3 px-4">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <ClipboardList className="w-4 h-4" /> Medical Entities
                    </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4 pt-0">
                    <p className="text-sm text-muted-foreground">No medical entities extracted.</p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <ClipboardList className="w-4 h-4" /> Medical Entities
                    {data.entity_count != null && (
                        <span className="text-xs text-muted-foreground font-normal">({data.entity_count} found)</span>
                    )}
                </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0 space-y-2">
                {entities.length > 0 ? (
                    groupByType(entities).map(([type, items]) => (
                        <CollapsibleSection key={type} title={`${formatLabel(type)} (${items.length})`}>
                            <ul className="space-y-1.5 text-sm">
                                {items.map((e, i) => (
                                    <li key={i}>
                                        <span className="font-medium">{e.normalized ?? e.text}</span>
                                        <span className="text-muted-foreground text-xs ml-2">
                                            {e.text !== (e.normalized ?? e.text) && `Original: ${e.text} | `}
                                            {e.speaker_role && `Speaker: ${e.speaker_role} | `}
                                            {e.confidence != null && `${Math.round(e.confidence * 100)}%`}
                                        </span>
                                        {e.details && (
                                            <p className="text-xs text-muted-foreground mt-0.5">{e.details}</p>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </CollapsibleSection>
                    ))
                ) : (
                    // Fallback: entities_by_speaker format
                    data.entities_by_speaker &&
                    Object.entries(data.entities_by_speaker).map(([speaker, speakerEntities]) => (
                        <CollapsibleSection key={speaker} title={speaker}>
                            {Object.entries(speakerEntities).map(([entityType, items]) =>
                                items.length > 0 ? (
                                    <div key={entityType} className="mb-2">
                                        <p className="text-sm font-medium">{formatLabel(entityType)}:</p>
                                        <ul className="list-disc list-inside text-sm text-muted-foreground">
                                            {items.map((item, i) => (
                                                <li key={i}>{item}</li>
                                            ))}
                                        </ul>
                                    </div>
                                ) : null
                            )}
                        </CollapsibleSection>
                    ))
                )}
            </CardContent>
        </Card>
    );
}

function SOAPSection({ data }: { data: SOAPGeneration }) {
    const soapNote = data.soap_note ?? data;
    const sections = [
        { key: 'subjective', label: 'S — Subjective', desc: "Patient's reported symptoms and history" },
        { key: 'objective', label: 'O — Objective', desc: 'Clinical findings and observations' },
        { key: 'assessment', label: 'A — Assessment', desc: 'Diagnosis and clinical impression' },
        { key: 'plan', label: 'P — Plan', desc: 'Treatment plan and follow-up' },
    ] as const;

    const hasContent = sections.some((s) => {
        const val = (soapNote as Record<string, unknown>)[s.key];
        return typeof val === 'string' && val.trim().length > 0;
    });

    return (
        <Card>
            <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <FileText className="w-4 h-4" /> SOAP Note
                </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0 space-y-2">
                {hasContent ? (
                    sections.map((s) => {
                        const content = (soapNote as Record<string, unknown>)[s.key];
                        if (typeof content !== 'string' || !content.trim()) return null;
                        return (
                            <CollapsibleSection key={s.key} title={s.label} defaultOpen={s.key === 'subjective'}>
                                <p className="text-xs text-muted-foreground mb-1">{s.desc}</p>
                                <div className="text-sm leading-relaxed whitespace-pre-wrap">{content}</div>
                            </CollapsibleSection>
                        );
                    })
                ) : (
                    <p className="text-sm text-muted-foreground">SOAP note sections are empty.</p>
                )}
            </CardContent>
        </Card>
    );
}

function VectorStorageSection({ data }: { data: VectorStorage }) {
    return (
        <Card>
            <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Database className="w-4 h-4" /> Vector Storage
                </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
                {data.vector_id ? (
                    <div className="space-y-2">
                        <p className="text-sm text-emerald-600 dark:text-emerald-400">
                            ✓ Consultation data stored in vector database
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                            {data.consultation_id && (
                                <div>
                                    <span className="text-muted-foreground">Consultation ID: </span>
                                    <code className="text-foreground">{data.consultation_id}</code>
                                </div>
                            )}
                            {data.vector_id && (
                                <div>
                                    <span className="text-muted-foreground">Vector ID: </span>
                                    <span>{data.vector_id}</span>
                                </div>
                            )}
                            {data.stored_at && (
                                <div>
                                    <span className="text-muted-foreground">Stored: </span>
                                    <span>{data.stored_at.slice(0, 19)}</span>
                                </div>
                            )}
                        </div>
                        {data.metadata && (
                            <CollapsibleSection title="📋 Storage Metadata">
                                <ul className="text-sm space-y-0.5">
                                    {data.metadata.entity_count != null && (
                                        <li>Entities: {data.metadata.entity_count}</li>
                                    )}
                                    {data.metadata.has_soap_note != null && (
                                        <li>SOAP Note: {data.metadata.has_soap_note ? 'Yes' : 'No'}</li>
                                    )}
                                    {data.metadata.has_phi != null && (
                                        <li>PHI Detected: {data.metadata.has_phi ? 'Yes' : 'No'}</li>
                                    )}
                                </ul>
                            </CollapsibleSection>
                        )}
                    </div>
                ) : data.success ? (
                    <div className="space-y-1">
                        <p className="text-sm text-emerald-600 dark:text-emerald-400">✓ Data stored</p>
                        {data.document_id && (
                            <p className="text-xs text-muted-foreground">
                                Document ID: <code>{data.document_id}</code>
                            </p>
                        )}
                    </div>
                ) : (
                    <div className="space-y-1">
                        <p className="text-sm text-amber-600 dark:text-amber-400">Vector storage encountered an issue</p>
                        {data.error && <p className="text-xs text-muted-foreground">{data.error}</p>}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

// ============================================================
// Raw Data Section
// ============================================================

export function RawDataSection({ result, workflowId }: { result: BackendWorkflowResult; workflowId: string }) {
    const jsonStr = JSON.stringify(result, null, 2);

    const handleDownload = () => {
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${workflowId}_results.json`;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="space-y-3">
            <Button variant="outline" size="sm" onClick={handleDownload}>
                <Download className="w-3.5 h-3.5 mr-1.5" />
                Download JSON
            </Button>
            <pre className="text-xs bg-muted p-4 rounded-lg overflow-x-auto max-h-96">
                {jsonStr}
            </pre>
        </div>
    );
}

// ============================================================
// Helpers
// ============================================================

function groupByType<T extends { type: string }>(items: T[]): [string, T[]][] {
    const groups: Record<string, T[]> = {};
    for (const item of items) {
        const t = item.type ?? 'unknown';
        if (!groups[t]) groups[t] = [];
        groups[t].push(item);
    }
    return Object.entries(groups);
}

function formatLabel(s: string): string {
    return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
