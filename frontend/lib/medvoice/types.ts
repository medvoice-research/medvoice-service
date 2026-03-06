// MedVoice API Response Types
// Generated from FastAPI backend endpoints (streamlit_app/utils/api_client.py)

// ============================================================
// Upload & Transcription
// ============================================================

export interface UploadResponse {
    workflow_id: string;
    message?: string;
}

export interface UploadParams {
    model?: string;
    language?: string;
    compute_type?: string;
    min_speakers?: number;
    max_speakers?: number;
    initial_prompt?: string;
}

export interface UploadFormData {
    file: File;
    patient_name: string;
    enable_medical_processing: boolean;
    provider_id?: string;
    encounter_date?: string;
}

// ============================================================
// Workflow / Consultation
// ============================================================

export type WorkflowStatus = 'RUNNING' | 'COMPLETED' | 'FAILED' | 'TERMINATED' | 'CANCELED' | 'TIMED_OUT';

export interface WorkflowStatusResponse {
    workflow_id: string;
    status: WorkflowStatus;
    start_time?: string;
    close_time?: string;
    execution_time?: number;
    task_queue?: string;
}

export interface DialogueSegment {
    speaker: string;
    text: string;
    start?: number;
    end?: number;
}

export interface MedicalEntity {
    entity: string;
    type: string;
    icd10_code?: string;
    confidence?: number;
}

export interface SOAPNote {
    subjective?: string;
    objective?: string;
    assessment?: string;
    plan?: string;
}

export interface WorkflowResult {
    workflow_id: string;
    status: WorkflowStatus;
    result?: {
        dialogue?: DialogueSegment[];
        medical_entities?: MedicalEntity[];
        soap_note?: SOAPNote;
        raw?: Record<string, unknown>;
    };
    error?: string;
}

// ============================================================
// Backend Workflow Result (actual Temporal result shape)
// ============================================================

export interface DialogueEntry {
    speaker_role: string;
    text: string;
    start?: number;
    end?: number;
}

export interface SpeakerMappingEntry {
    role: string;
    confidence: number;
}

export interface DialogueTransformation {
    full_transcript_markdown?: string;
    full_transcript?: string;
    dialogue?: DialogueEntry[];
    speaker_mapping?: Record<string, SpeakerMappingEntry | string>;
}

export interface PHIEntity {
    type: string;
    text: string;
    confidence: number;
}

export interface PHIDetection {
    phi_detected: boolean;
    entities?: PHIEntity[];
}

export interface MedicalEntityItem {
    type: string;
    text: string;
    normalized?: string;
    speaker_role?: string;
    confidence?: number;
    details?: string;
}

export interface EntityExtraction {
    entities?: MedicalEntityItem[];
    entity_count?: number;
    entities_by_speaker?: Record<string, Record<string, string[]>>;
}

export interface SOAPNoteContent {
    subjective?: string;
    objective?: string;
    assessment?: string;
    plan?: string;
}

export interface SOAPGeneration {
    soap_note?: SOAPNoteContent;
    subjective?: string;
    objective?: string;
    assessment?: string;
    plan?: string;
}

export interface VectorStorageMetadata {
    entity_count?: number;
    has_soap_note?: boolean;
    has_phi?: boolean;
}

export interface VectorStorage {
    vector_id?: string;
    consultation_id?: string;
    stored_at?: string;
    metadata?: VectorStorageMetadata;
    success?: boolean;
    document_id?: string;
    error?: string;
}

export interface WhisperXSegment {
    text: string;
    start?: number;
    end?: number;
    speaker?: string;
}

export interface WhisperXFinal {
    segments?: WhisperXSegment[];
}

export interface BackendWorkflowResult {
    workflow_type?: string;
    audio_path?: string;
    started_at?: string;
    dialogue_transformation?: DialogueTransformation;
    phi_detection?: PHIDetection;
    entity_extraction?: EntityExtraction;
    soap_generation?: SOAPGeneration;
    vector_storage?: VectorStorage;
    whisperx_final?: WhisperXFinal;
    [key: string]: unknown;
}

// ============================================================
// Patient Records
// ============================================================

export interface PatientWorkflow {
    workflow_id: string;
    created_at: string;
    file_path?: string;
    status?: WorkflowStatus;
}

export interface PatientInfo {
    patient_hash: string;
    patient_name: string;
    total_workflows: number;
    workflows: PatientWorkflow[];
}

export interface PatientsListResponse {
    total_patients: number;
    patients: PatientInfo[];
}

export interface PatientWorkflowsResponse {
    workflows: PatientWorkflow[];
    total: number;
}

// ============================================================
// System Health & Stats
// ============================================================

export interface SystemHealth {
    fastapi: string;
    lm_studio?: string;
    vector_db?: string;
    temporal?: string;
}

export interface DatabaseStats {
    total_patients: number;
    total_workflows: number;
    average_workflows_per_patient?: number;
}

// ============================================================
// Medical Chat (RAG)
// ============================================================

export interface ChatSource {
    content: string;
    metadata?: Record<string, unknown>;
    similarity_score?: number;
}

export interface ChatResponse {
    answer: string;
    sources?: ChatSource[];
    session_id?: string;
}

export interface ChatRequest {
    query: string;
    patient_id_encrypted: string;
    session_id?: string;
}

// ============================================================
// API Error
// ============================================================

export interface ApiError {
    message: string;
    status: number;
    detail?: string;
}
