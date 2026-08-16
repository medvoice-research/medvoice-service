"""Synchronous pipeline: audio file -> transcript + medical document.

Reuses the same WhisperX functions the Temporal activities call, plus the
medical LLM service, but runs inline (no Temporal dependency).
"""

from typing import Any, Dict, Tuple, Type

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from whisperx import assign_word_speakers

from app.audio import process_audio_file
from app.config import Config
from app.logger import logger
from app.schemas import ASROptions, AlignmentParams, DiarizationParams, VADOptions, WhisperModelParams
from app.whisperx_services import align_whisper_output, diarize, transcribe_with_whisper


def _defaults(model_cls: Type[BaseModel]) -> Dict[str, Any]:
    """Plain default values for a request-params schema.

    The schemas declare defaults as fastapi ``Query(...)`` objects, which FastAPI
    unwraps per request. Inline callers must unwrap them themselves.
    """
    return {
        name: field.default.default if isinstance(field.default, FieldInfo) else field.default
        for name, field in model_cls.model_fields.items()
    }


async def run_stt(audio_path: str, language: str = "en", model: str = "base") -> Dict[str, Any]:
    """Transcribe + align + diarize, returning the WhisperX result with speakers."""
    audio = process_audio_file(audio_path)
    mp = WhisperModelParams(**{**_defaults(WhisperModelParams), "language": language, "model": model})
    result = transcribe_with_whisper(
        audio=audio,
        task=mp.task.value,
        asr_options=ASROptions(**_defaults(ASROptions)).model_dump(),
        vad_options=VADOptions(**_defaults(VADOptions)).model_dump(),
        language=mp.language,
        batch_size=mp.batch_size,
        chunk_size=mp.chunk_size,
        model=mp.model,
        device=mp.device,
        device_index=mp.device_index,
        compute_type=mp.compute_type,
        threads=mp.threads,
    )
    if result.get("segments"):
        ap = AlignmentParams(**_defaults(AlignmentParams))
        result = align_whisper_output(
            transcript=result["segments"],
            audio=audio,
            language_code=result.get("language", language),
            device=ap.device,
            align_model=ap.align_model,
            interpolate_method=ap.interpolate_method,
            return_char_alignments=ap.return_char_alignments,
        )

    try:
        dp = DiarizationParams(**_defaults(DiarizationParams))
        diarized = diarize(audio, device=dp.device, min_speakers=dp.min_speakers, max_speakers=dp.max_speakers)
        result = assign_word_speakers(diarized, result)
    except Exception as e:
        logger.warning(f"Diarization unavailable, falling back to a single speaker: {e}")
    for seg in result.get("segments", []):
        seg.setdefault("speaker", "SPEAKER_00")
    return result


async def run_medical(transcript: Dict[str, Any]) -> Dict[str, Any]:
    """PHI + entities + SOAP via the existing medical LLM service. Degrades per-step."""
    from app.llm.lm_studio_client import LMStudioClient, LMStudioConfig
    from app.llm.medical_llm_service import MedicalLLMService
    from app.services.transcription_transformer import TranscriptionTransformer

    result: Dict[str, Any] = {"soap": {}, "entities": [], "phi": {"detected": False, "entities": []}}

    try:
        dialogue = TranscriptionTransformer().transform({"segments": transcript.get("segments", [])})
    except Exception as e:
        logger.warning(f"Dialogue transformation failed, using flat transcript: {e}")
        dialogue = {
            "dialogue": [{"speaker": "unknown", "text": transcript.get("full_text", "")}],
            "speaker_mapping": {},
        }

    lm_config = LMStudioConfig(
        base_url=Config.LM_STUDIO_BASE_URL,
        timeout=Config.LM_STUDIO_TIMEOUT,
        temperature=Config.LM_STUDIO_TEMPERATURE,
        max_tokens=Config.LM_STUDIO_MAX_TOKENS,
        model=Config.LM_STUDIO_MODEL,
    )
    async with LMStudioClient(lm_config) as client:
        service = MedicalLLMService(client)
        try:
            phi = await service.detect_phi_in_dialogue(dialogue)
            result["phi"] = {"detected": bool(phi.get("phi_detected")), "entities": phi.get("entities", [])}
        except Exception as e:
            logger.warning(f"PHI detection failed: {e}")
        try:
            entities = await service.extract_entities_with_speaker(dialogue)
            result["entities"] = entities or []
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
        try:
            soap = await service.generate_soap_from_dialogue(dialogue)
            if isinstance(soap, dict):
                result["soap"] = {
                    "subjective": soap.get("subjective", ""),
                    "objective": soap.get("objective", ""),
                    "assessment": soap.get("assessment", ""),
                    "plan": soap.get("plan", ""),
                }
        except Exception as e:
            logger.warning(f"SOAP generation failed: {e}")
    return result


async def run_recording_pipeline(audio_path: str, language: str = "en") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    stt = await run_stt(audio_path, language=language)
    segments = stt.get("segments", [])
    transcript = {
        "full_text": " ".join(s["text"].strip() for s in segments if s.get("text")),
        "segments": segments,
    }
    medical = await run_medical(transcript)
    return transcript, medical
