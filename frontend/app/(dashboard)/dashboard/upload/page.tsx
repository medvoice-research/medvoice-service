'use client';

import { useState, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Upload, FileAudio, CheckCircle2, AlertCircle, Loader2, Mic, Square } from 'lucide-react';
import { useAudioRecorder } from '@/hooks/use-audio-recorder';

function formatDuration(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export default function UploadPage() {
    const [activeTab, setActiveTab] = useState('upload');
    const [file, setFile] = useState<File | null>(null);
    const [patientName, setPatientName] = useState('');
    const [enableMedical, setEnableMedical] = useState(false);
    const [providerId, setProviderId] = useState('');
    const [model, setModel] = useState('base');
    const [language, setLanguage] = useState('en');
    const [minSpeakers, setMinSpeakers] = useState('');
    const [maxSpeakers, setMaxSpeakers] = useState('');
    const [uploading, setUploading] = useState(false);
    const [result, setResult] = useState<{ workflow_id: string } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const recorder = useAudioRecorder();

    const handleFileDrop = (e: React.DragEvent) => {
        e.preventDefault();
        const droppedFile = e.dataTransfer.files[0];
        if (droppedFile) setFile(droppedFile);
    };

    const hasAudioSource = activeTab === 'upload' ? !!file : !!recorder.audioBlob;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!patientName.trim() || !hasAudioSource) return;

        setUploading(true);
        setError(null);
        setResult(null);

        try {
            const formData = new FormData();

            if (activeTab === 'upload' && file) {
                formData.append('file', file);
            } else if (activeTab === 'record' && recorder.audioBlob) {
                const now = new Date();
                const timestamp = now.toISOString().replace(/[-:T]/g, '').slice(0, 15);
                const filename = `recorded_${timestamp}.webm`;
                formData.append('file', recorder.audioBlob, filename);
            } else {
                return;
            }

            formData.append('patient_name', patientName);
            formData.append('enable_medical_processing', String(enableMedical));
            if (enableMedical && providerId) formData.append('provider_id', providerId);

            const params = new URLSearchParams({ model, language });
            if (minSpeakers) params.set('min_speakers', minSpeakers);
            if (maxSpeakers) params.set('max_speakers', maxSpeakers);

            const res = await fetch(`/api/medvoice/speech-to-text?${params}`, {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const errText = await res.text();
                throw new Error(errText || `Upload failed (${res.status})`);
            }

            const data = await res.json();
            setResult({
                ...data,
                workflow_id: data.identifier || data.workflow_id
            });
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-3xl">
            <div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
                    Upload Consultation
                </h1>
                <p className="text-muted-foreground mt-1">
                    Upload an audio recording or record from your microphone for AI-powered transcription
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                {/* Audio Input Tabs */}
                <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList>
                        <TabsTrigger value="upload" className="gap-1.5">
                            <Upload className="size-3.5" />
                            Upload File
                        </TabsTrigger>
                        <TabsTrigger value="record" className="gap-1.5">
                            <Mic className="size-3.5" />
                            Record Audio
                        </TabsTrigger>
                    </TabsList>

                    {/* Upload File Tab */}
                    <TabsContent value="upload" className="mt-4">
                        <Card>
                            <CardContent className="pt-6">
                                <div
                                    onDragOver={(e) => e.preventDefault()}
                                    onDrop={handleFileDrop}
                                    onClick={() => fileInputRef.current?.click()}
                                    className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 hover:bg-accent/30 transition-colors"
                                >
                                    {file ? (
                                        <div className="flex items-center justify-center gap-3">
                                            <FileAudio className="w-8 h-8 text-primary" />
                                            <div className="text-left">
                                                <p className="font-medium text-sm">{file.name}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {(file.size / (1024 * 1024)).toFixed(1)} MB
                                                </p>
                                            </div>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setFile(null);
                                                }}
                                            >
                                                Remove
                                            </Button>
                                        </div>
                                    ) : (
                                        <>
                                            <Upload className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                                            <p className="text-sm font-medium">
                                                Drop audio file here or click to browse
                                            </p>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                Supports MP3, WAV, M4A, FLAC, OGG
                                            </p>
                                        </>
                                    )}
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept="audio/*"
                                        className="hidden"
                                        aria-label="Select audio file"
                                        onChange={(e) => setFile(e.target.files?.[0] || null)}
                                    />
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* Record Audio Tab */}
                    <TabsContent value="record" className="mt-4">
                        <Card>
                            <CardContent className="pt-6">
                                <div className="space-y-4">
                                    {/* Recording controls */}
                                    <div className="flex flex-col items-center gap-4 py-4">
                                        {recorder.isRecording ? (
                                            <>
                                                <div className="flex items-center gap-2">
                                                    <span className="relative flex size-3">
                                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                                                        <span className="relative inline-flex rounded-full size-3 bg-red-500" />
                                                    </span>
                                                    <span className="text-sm font-medium text-red-500">
                                                        Recording
                                                    </span>
                                                    <span className="text-sm font-mono text-muted-foreground">
                                                        {formatDuration(recorder.duration)}
                                                    </span>
                                                </div>
                                                <Button
                                                    type="button"
                                                    variant="destructive"
                                                    size="lg"
                                                    onClick={recorder.stopRecording}
                                                    className="gap-2"
                                                >
                                                    <Square className="size-4" />
                                                    Stop Recording
                                                </Button>
                                            </>
                                        ) : recorder.audioBlob ? (
                                            <div className="w-full space-y-3">
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-2">
                                                        <FileAudio className="w-5 h-5 text-primary" />
                                                        <div>
                                                            <p className="text-sm font-medium">Recording captured</p>
                                                            <p className="text-xs text-muted-foreground">
                                                                {(recorder.audioBlob.size / 1024).toFixed(1)} KB · {formatDuration(recorder.duration)}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <Button
                                                        type="button"
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={recorder.resetRecording}
                                                    >
                                                        Remove
                                                    </Button>
                                                </div>
                                                {recorder.audioUrl && (
                                                    <audio
                                                        controls
                                                        src={recorder.audioUrl}
                                                        className="w-full h-10"
                                                    />
                                                )}
                                            </div>
                                        ) : (
                                            <>
                                                <Mic className="w-10 h-10 text-muted-foreground" />
                                                <p className="text-sm text-muted-foreground">
                                                    Click below to start recording from your microphone
                                                </p>
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    size="lg"
                                                    onClick={recorder.startRecording}
                                                    className="gap-2"
                                                >
                                                    <Mic className="size-4" />
                                                    Start Recording
                                                </Button>
                                            </>
                                        )}
                                    </div>

                                    {/* Recorder error */}
                                    {recorder.error && (
                                        <div className="flex items-center gap-3 p-3 rounded-lg bg-red-50 dark:bg-red-950/50 text-red-800 dark:text-red-300">
                                            <AlertCircle className="w-4 h-4 shrink-0" />
                                            <p className="text-sm">{recorder.error}</p>
                                        </div>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>

                {/* Patient Information */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Patient Information</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="patientName">Patient Full Name *</Label>
                            <Input
                                id="patientName"
                                value={patientName}
                                onChange={(e) => setPatientName(e.target.value)}
                                placeholder="e.g. John Michael Smith"
                                required
                            />
                        </div>

                        <div className="flex items-center gap-3">
                            <input
                                type="checkbox"
                                id="enableMedical"
                                checked={enableMedical}
                                onChange={(e) => setEnableMedical(e.target.checked)}
                                className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                            />
                            <Label htmlFor="enableMedical" className="cursor-pointer">
                                Enable medical processing (NER, SOAP notes)
                            </Label>
                        </div>

                        {enableMedical && (
                            <div className="space-y-2">
                                <Label htmlFor="providerId">Provider ID</Label>
                                <Input
                                    id="providerId"
                                    value={providerId}
                                    onChange={(e) => setProviderId(e.target.value)}
                                    placeholder="Healthcare provider ID"
                                />
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Transcription Settings */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Transcription Settings</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="model">Whisper Model</Label>
                                <select
                                    id="model"
                                    value={model}
                                    onChange={(e) => setModel(e.target.value)}
                                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
                                >
                                    <option value="tiny">tiny</option>
                                    <option value="base">base</option>
                                    <option value="small">small</option>
                                    <option value="medium">medium</option>
                                    <option value="large-v3">large-v3</option>
                                </select>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="language">Language</Label>
                                <select
                                    id="language"
                                    value={language}
                                    onChange={(e) => setLanguage(e.target.value)}
                                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
                                >
                                    <option value="en">English</option>
                                    <option value="vi">Vietnamese</option>
                                    <option value="zh">Chinese</option>
                                    <option value="yue">Cantonese</option>
                                </select>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="minSpeakers">Min Speakers</Label>
                                <Input
                                    id="minSpeakers"
                                    type="number"
                                    min="1"
                                    max="10"
                                    value={minSpeakers}
                                    onChange={(e) => setMinSpeakers(e.target.value)}
                                    placeholder="Auto"
                                />
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="maxSpeakers">Max Speakers</Label>
                                <Input
                                    id="maxSpeakers"
                                    type="number"
                                    min="1"
                                    max="10"
                                    value={maxSpeakers}
                                    onChange={(e) => setMaxSpeakers(e.target.value)}
                                    placeholder="Auto"
                                />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Result / Error */}
                {result && (
                    <div className="flex items-center gap-3 p-4 rounded-lg bg-emerald-50 dark:bg-emerald-950/50 text-emerald-800 dark:text-emerald-300">
                        <CheckCircle2 className="w-5 h-5 shrink-0" />
                        <div>
                            <p className="font-medium text-sm">Upload successful!</p>
                            <p className="text-xs mt-0.5">
                                Workflow ID:{' '}
                                <a
                                    href={`/dashboard/consultations?wf=${result.workflow_id}`}
                                    className="underline font-mono"
                                >
                                    {result.workflow_id}
                                </a>
                            </p>
                        </div>
                    </div>
                )}

                {error && (
                    <div className="flex items-center gap-3 p-4 rounded-lg bg-red-50 dark:bg-red-950/50 text-red-800 dark:text-red-300">
                        <AlertCircle className="w-5 h-5 shrink-0" />
                        <p className="text-sm">{error}</p>
                    </div>
                )}

                {/* Submit */}
                <Button
                    type="submit"
                    size="lg"
                    disabled={!hasAudioSource || !patientName.trim() || uploading}
                    className="w-full sm:w-auto"
                >
                    {uploading ? (
                        <>
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            Uploading...
                        </>
                    ) : (
                        <>
                            <Upload className="w-4 h-4 mr-2" />
                            Upload & Transcribe
                        </>
                    )}
                </Button>
            </form>
        </div>
    );
}
