/**
 * MedVoice API Client
 * Typed fetch wrapper for communicating with MedVoice FastAPI backend
 * through Next.js API route proxies.
 */

import type {
    UploadResponse,
    UploadParams,
    UploadFormData,
    WorkflowStatusResponse,
    WorkflowResult,
    PatientWorkflowsResponse,
    WorkflowResult as LatestWorkflowResponse,
    SystemHealth,
    DatabaseStats,
    ChatResponse,
    PatientsListResponse,
    PatientInfo,
    ApiError,
} from './types';

class MedVoiceApiError extends Error {
    status: number;
    detail?: string;

    constructor(message: string, status: number, detail?: string) {
        super(message);
        this.name = 'MedVoiceApiError';
        this.status = status;
        this.detail = detail;
    }
}

async function apiFetch<T>(
    url: string,
    options: RequestInit = {}
): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000); // 30s timeout

    try {
        const res = await fetch(url, {
            ...options,
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });

        if (!res.ok) {
            const errorBody = await res.text().catch(() => '');
            let detail: string | undefined;
            try {
                const parsed = JSON.parse(errorBody);
                detail = parsed.detail || parsed.message;
            } catch {
                detail = errorBody || undefined;
            }
            throw new MedVoiceApiError(
                `API error: ${res.status} ${res.statusText}`,
                res.status,
                detail
            );
        }

        return res.json() as Promise<T>;
    } catch (err) {
        if (err instanceof MedVoiceApiError) throw err;
        if ((err as Error).name === 'AbortError') {
            throw new MedVoiceApiError('Request timed out', 408);
        }
        throw new MedVoiceApiError(
            `Network error: ${(err as Error).message}`,
            0
        );
    } finally {
        clearTimeout(timeout);
    }
}

// ============================================================
// API Client Functions (call Next.js proxy routes)
// ============================================================

/** Upload audio file for transcription */
export async function uploadAudio(
    formData: UploadFormData,
    params: UploadParams = {}
): Promise<UploadResponse> {
    const body = new FormData();
    body.append('file', formData.file);
    body.append('patient_name', formData.patient_name);
    body.append('enable_medical_processing', String(formData.enable_medical_processing));
    if (formData.provider_id) body.append('provider_id', formData.provider_id);
    if (formData.encounter_date) body.append('encounter_date', formData.encounter_date);

    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
            queryParams.set(key, String(value));
        }
    });
    const qs = queryParams.toString();

    const res = await fetch(`/api/medvoice/speech-to-text${qs ? `?${qs}` : ''}`, {
        method: 'POST',
        body,
    });

    if (!res.ok) {
        const errorBody = await res.text().catch(() => '');
        throw new MedVoiceApiError(`Upload failed: ${res.status}`, res.status, errorBody);
    }

    return res.json();
}

/** Get workflow status */
export async function getWorkflowStatus(workflowId: string): Promise<WorkflowStatusResponse> {
    return apiFetch<WorkflowStatusResponse>(`/api/medvoice/workflows/${workflowId}/status`);
}

/** Get workflow result */
export async function getWorkflowResult(workflowId: string): Promise<WorkflowResult> {
    return apiFetch<WorkflowResult>(`/api/medvoice/workflows/${workflowId}/result`);
}

/** Get patient workflows */
export async function getPatientWorkflows(
    patientHash: string,
    options: { status?: string; limit?: number; offset?: number } = {}
): Promise<PatientWorkflowsResponse> {
    const params = new URLSearchParams();
    if (options.status) params.set('status', options.status);
    if (options.limit) params.set('limit', String(options.limit));
    if (options.offset) params.set('offset', String(options.offset));
    const qs = params.toString();

    return apiFetch<PatientWorkflowsResponse>(
        `/api/medvoice/patients/${patientHash}/workflows${qs ? `?${qs}` : ''}`
    );
}

/** Get latest workflow for a patient */
export async function getLatestWorkflow(patientHash: string): Promise<LatestWorkflowResponse> {
    return apiFetch<LatestWorkflowResponse>(`/api/medvoice/patients/${patientHash}/latest`);
}

/** Get system health */
export async function getSystemHealth(): Promise<SystemHealth> {
    return apiFetch<SystemHealth>('/api/medvoice/health');
}

/** Get database stats */
export async function getDatabaseStats(): Promise<DatabaseStats> {
    return apiFetch<DatabaseStats>('/api/medvoice/stats');
}

/** Send medical chat message */
export async function sendChatMessage(
    query: string,
    patientHash: string,
    sessionId?: string
): Promise<ChatResponse> {
    return apiFetch<ChatResponse>('/api/medvoice/chat', {
        method: 'POST',
        body: JSON.stringify({
            query,
            patient_id_encrypted: patientHash,
            session_id: sessionId,
        }),
    });
}

/** Get all patients */
export async function getAllPatients(): Promise<PatientsListResponse> {
    return apiFetch<PatientsListResponse>('/api/medvoice/patients');
}

/** Get patient info by hash */
export async function getPatientByHash(patientHash: string): Promise<PatientInfo> {
    return apiFetch<PatientInfo>(`/api/medvoice/patients/${patientHash}`);
}

export { MedVoiceApiError };
export type { ApiError };
