from __future__ import annotations

import multiprocessing as mp
import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_int(name: str, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = int(raw)
        except Exception as e:
            raise ValueError(f"Invalid integer value for {name}: {raw!r}") from e
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value} (got {value})")
    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be <= {max_value} (got {value})")
    return value


def _env_float(name: str, default: float, *, min_value: float | None = None, max_value: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        value = float(default)
    else:
        try:
            value = float(raw)
        except Exception as e:
            raise ValueError(f"Invalid float value for {name}: {raw!r}") from e
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value} (got {value})")
    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be <= {max_value} (got {value})")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {raw!r}")


def _resolve_text_extract_context(raw: str) -> str:
    value = (raw or "").strip().lower() or "auto"
    explicit = value != "auto"
    if value == "auto":
        if sys.platform.startswith("win") or sys.platform == "darwin":
            value = "spawn"
        else:
            value = "fork"
    if value not in {"fork", "spawn"}:
        raise ValueError("MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT must be 'auto', 'fork', or 'spawn'.")
    available = mp.get_all_start_methods()
    if value not in available:
        if explicit:
            raise ValueError(
                f"MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT {value!r} not supported on this platform "
                f"(available: {available})."
            )
        value = "spawn" if "spawn" in available else available[0]
    return value


@dataclass(frozen=True)
class Settings:
    db_url: str
    storage_dir: Path
    max_upload_mb: int
    max_body_mb: int
    max_unpacked_mb: int
    session_days: int
    login_code_ttl_minutes: int
    login_code_length: int
    mailgun_api_key: str
    mailgun_domain: str
    mailgun_sender: str
    mailgun_base_url: str
    turnstile_site_key: str
    turnstile_secret_key: str
    turnstile_verify_url: str

    log_level: str
    text_extract_backend: str
    text_extract_timeout_seconds: float
    text_extract_subprocess: bool
    text_extract_process_context: str
    accelerator: str

    crossref_mailto: str
    crossref_user_agent: str

    retractionwatch_csv: Path
    predatory_csv: Path

    rw_sync_enabled: bool
    rw_sync_method: str
    rw_sync_interval_hours: int
    rw_git_repo: str
    rw_git_dir: Path
    rw_http_url: str

    retraction_api_enabled: bool
    retraction_api_mode: str
    retraction_api_url: str
    retraction_api_token: str

    predatory_api_enabled: bool
    predatory_api_mode: str
    predatory_api_url: str
    predatory_api_token: str

    predatory_sync_enabled: bool
    predatory_sync_interval_hours: int
    predatory_publishers_url: str
    predatory_journals_url: str

    api_timeout_seconds: float

    openrouter_api_key: str
    llm_model: str
    enable_llm_inappropriate: bool
    llm_max_calls: int

    llm_parse_model: str
    llm_match_model: str
    llm_deep_analysis_model: str
    llm_match_max_calls: int
    llm_bib_parse_max_chars: int
    llm_bib_parse_max_refs: int
    llm_citation_parse_max_chars: int
    llm_citation_parse_max_lines: int
    llm_citation_parse_max_candidate_chars: int

    enable_local_nli: bool
    local_nli_model: str

    enable_deep_analysis: bool
    enable_deep_analysis_llm_key_selection: bool
    enable_deep_analysis_llm_suggestions: bool
    deep_analysis_min_confidence: float
    deep_analysis_max_original_refs: int
    deep_analysis_paper_excerpt_max_chars: int
    deep_analysis_max_nodes: int
    deep_analysis_max_edges: int
    deep_analysis_max_workers: int
    deep_analysis_max_references_per_work: int
    deep_analysis_max_second_hop_seeds: int
    deep_analysis_max_total_citing_refs: int
    deep_analysis_max_citing_refs_for_second_hop: int
    deep_analysis_display_max_key_refs: int
    deep_analysis_display_max_per_category: int
    deep_analysis_display_max_openalex_fetches: int

    billing_enabled: bool
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_id: str
    stripe_success_url: str
    stripe_cancel_url: str

    worker_poll_seconds: float
    worker_processes: int

    cookie_secure: bool
    trust_proxy: bool
    maintenance_mode: bool
    maintenance_message: str
    load_shed_mode: bool
    access_token_days: int
    expose_sensitive_report_fields: bool

    rate_limit_enabled: bool
    rate_limit_window_seconds: int
    rate_limit_login_request: int
    rate_limit_login_verify: int
    rate_limit_upload: int
    rate_limit_report_access: int
    rate_limit_events: int
    rate_limit_stream: int
    rate_limit_api: int

    job_stale_seconds: int
    job_stale_action: str
    job_max_attempts: int
    job_reap_interval_seconds: int

    upload_scan_enabled: bool
    upload_scan_command: str
    upload_scan_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        db_url = _env_str("MISCITE_DB_URL", "sqlite:///./data/miscite.db")
        storage_dir = Path(_env_str("MISCITE_STORAGE_DIR", "./data/uploads"))
        max_upload_mb = _env_int("MISCITE_MAX_UPLOAD_MB", 50, min_value=1, max_value=2000)
        max_body_mb = _env_int("MISCITE_MAX_BODY_MB", max_upload_mb + 5, min_value=1, max_value=4000)
        max_unpacked_mb = _env_int("MISCITE_MAX_UNPACKED_MB", max(200, max_upload_mb * 5), min_value=10, max_value=20000)
        session_days = _env_int("MISCITE_SESSION_DAYS", 14, min_value=1, max_value=3650)
        login_code_ttl_minutes = _env_int("MISCITE_LOGIN_CODE_TTL_MINUTES", 15, min_value=5, max_value=60)
        login_code_length = _env_int("MISCITE_LOGIN_CODE_LENGTH", 6, min_value=4, max_value=10)
        mailgun_api_key = _env_str("MISCITE_MAILGUN_API_KEY", "")
        mailgun_domain = _env_str("MISCITE_MAILGUN_DOMAIN", "")
        mailgun_sender = _env_str("MISCITE_MAILGUN_SENDER", "")
        mailgun_base_url = _env_str("MISCITE_MAILGUN_BASE_URL", "https://api.mailgun.net/v3")
        turnstile_site_key = _env_str("MISCITE_TURNSTILE_SITE_KEY", "")
        turnstile_secret_key = _env_str("MISCITE_TURNSTILE_SECRET_KEY", "")
        turnstile_verify_url = _env_str(
            "MISCITE_TURNSTILE_VERIFY_URL",
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        )

        log_level = _env_str("MISCITE_LOG_LEVEL", "INFO")
        text_extract_backend = _env_str("MISCITE_TEXT_EXTRACT_BACKEND", "markitdown").lower()
        if text_extract_backend not in {"markitdown", "docling"}:
            raise ValueError("MISCITE_TEXT_EXTRACT_BACKEND must be 'markitdown' or 'docling'.")
        text_extract_timeout_seconds = _env_float("MISCITE_TEXT_EXTRACT_TIMEOUT_SECONDS", 120.0, min_value=10.0, max_value=1200.0)
        text_extract_subprocess = _env_bool("MISCITE_TEXT_EXTRACT_SUBPROCESS", True)
        text_extract_process_context = _resolve_text_extract_context(
            _env_str("MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT", "auto")
        )

        accelerator = _env_str("MISCITE_ACCELERATOR", "cpu").lower()
        if accelerator not in {"cpu", "gpu"}:
            raise ValueError("MISCITE_ACCELERATOR must be 'cpu' or 'gpu'.")

        crossref_mailto = _env_str("MISCITE_CROSSREF_MAILTO", "")
        crossref_user_agent = _env_str(
            "MISCITE_CROSSREF_USER_AGENT",
            f"miscite/0.1 (mailto:{crossref_mailto})" if crossref_mailto else "miscite/0.1",
        )

        retractionwatch_csv = Path(
            _env_str(
                "MISCITE_RETRACTIONWATCH_CSV",
                "./data/datasets/retraction-watch-data/retraction_watch.csv",
            )
        )
        predatory_csv = Path(_env_str("MISCITE_PREDATORY_CSV", "./data/datasets/predatory.csv"))

        rw_sync_enabled = _env_bool("MISCITE_RW_SYNC_ENABLED", False)
        rw_sync_method = _env_str("MISCITE_RW_SYNC_METHOD", "git").lower()
        if rw_sync_method not in {"git", "http"}:
            raise ValueError("MISCITE_RW_SYNC_METHOD must be 'git' or 'http'.")
        rw_sync_interval_hours = _env_int("MISCITE_RW_SYNC_INTERVAL_HOURS", 24, min_value=1, max_value=720)
        rw_git_repo = _env_str("MISCITE_RW_GIT_REPO", "https://gitlab.com/crossref/retraction-watch-data")
        rw_git_dir = Path(_env_str("MISCITE_RW_GIT_DIR", "./data/datasets/retraction-watch-data"))
        rw_http_url = _env_str(
            "MISCITE_RW_HTTP_URL",
            "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv?ref_type=heads&inline=false",
        )

        retraction_api_enabled = _env_bool("MISCITE_RETRACTION_API_ENABLED", False)
        retraction_api_mode = _env_str("MISCITE_RETRACTION_API_MODE", "lookup").lower()
        if retraction_api_mode not in {"lookup", "list"}:
            raise ValueError("MISCITE_RETRACTION_API_MODE must be 'lookup' or 'list'.")
        retraction_api_url = _env_str("MISCITE_RETRACTION_API_URL", "")
        retraction_api_token = _env_str("MISCITE_RETRACTION_API_TOKEN", "")

        predatory_api_enabled = _env_bool("MISCITE_PREDATORY_API_ENABLED", False)
        predatory_api_mode = _env_str("MISCITE_PREDATORY_API_MODE", "lookup").lower()
        if predatory_api_mode not in {"lookup", "list"}:
            raise ValueError("MISCITE_PREDATORY_API_MODE must be 'lookup' or 'list'.")
        predatory_api_url = _env_str("MISCITE_PREDATORY_API_URL", "")
        predatory_api_token = _env_str("MISCITE_PREDATORY_API_TOKEN", "")

        predatory_sync_enabled = _env_bool("MISCITE_PREDATORY_SYNC_ENABLED", False)
        predatory_sync_interval_hours = _env_int("MISCITE_PREDATORY_SYNC_INTERVAL_HOURS", 24, min_value=1, max_value=720)
        predatory_publishers_url = _env_str(
            "MISCITE_PREDATORY_PUBLISHERS_URL",
            "https://docs.google.com/spreadsheets/d/1BHM4aJljhbOAzSpkX1kXDUEvy6vxREZu5WJaDH6M1Vk/edit?usp=sharing",
        )
        predatory_journals_url = _env_str(
            "MISCITE_PREDATORY_JOURNALS_URL",
            "https://docs.google.com/spreadsheets/d/1Qa1lAlSbl7iiKddYINNsDB4wxI7uUA4IVseeLnCc5U4/edit?gid=0#gid=0",
        )

        api_timeout_seconds = _env_float("MISCITE_API_TIMEOUT_SECONDS", 20.0, min_value=2.0, max_value=120.0)

        openrouter_api_key = _env_str("OPENROUTER_API_KEY", "")
        llm_model = _env_str("MISCITE_LLM_MODEL", "google/gemini-3-flash-preview")
        enable_llm_inappropriate = _env_bool("MISCITE_ENABLE_LLM_INAPPROPRIATE", True)
        llm_max_calls = _env_int("MISCITE_LLM_MAX_CALLS", 25, min_value=1, max_value=200)

        llm_parse_model = _env_str("MISCITE_LLM_PARSE_MODEL", llm_model)
        llm_match_model = _env_str("MISCITE_LLM_MATCH_MODEL", llm_model)
        llm_deep_analysis_model = _env_str("MISCITE_LLM_DEEP_ANALYSIS_MODEL", llm_model)
        llm_match_max_calls = _env_int("MISCITE_LLM_MATCH_MAX_CALLS", 50, min_value=0, max_value=200)
        llm_bib_parse_max_chars = _env_int("MISCITE_LLM_BIB_PARSE_MAX_CHARS", 120_000, min_value=1000, max_value=500_000)
        llm_bib_parse_max_refs = _env_int("MISCITE_LLM_BIB_PARSE_MAX_REFS", 400, min_value=1, max_value=2000)
        llm_citation_parse_max_chars = _env_int(
            "MISCITE_LLM_CITATION_PARSE_MAX_CHARS", 120_000, min_value=1000, max_value=500_000
        )
        llm_citation_parse_max_lines = _env_int("MISCITE_LLM_CITATION_PARSE_MAX_LINES", 2000, min_value=1, max_value=10_000)
        llm_citation_parse_max_candidate_chars = _env_int(
            "MISCITE_LLM_CITATION_PARSE_MAX_CANDIDATE_CHARS", 60_000, min_value=1000, max_value=200_000
        )

        enable_local_nli = _env_bool("MISCITE_ENABLE_LOCAL_NLI", False)
        local_nli_model = _env_str("MISCITE_LOCAL_NLI_MODEL", "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")

        enable_deep_analysis = _env_bool("MISCITE_ENABLE_DEEP_ANALYSIS", False)
        enable_deep_analysis_llm_key_selection = _env_bool("MISCITE_ENABLE_DEEP_ANALYSIS_LLM_KEY_SELECTION", True)
        enable_deep_analysis_llm_suggestions = _env_bool("MISCITE_ENABLE_DEEP_ANALYSIS_LLM_SUGGESTIONS", True)
        deep_analysis_min_confidence = _env_float("MISCITE_DEEP_ANALYSIS_MIN_CONFIDENCE", 0.55, min_value=0.0, max_value=1.0)
        deep_analysis_max_original_refs = _env_int("MISCITE_DEEP_ANALYSIS_MAX_ORIGINAL_REFS", 400, min_value=10, max_value=5000)
        deep_analysis_paper_excerpt_max_chars = _env_int("MISCITE_DEEP_ANALYSIS_PAPER_EXCERPT_MAX_CHARS", 6000, min_value=500, max_value=50_000)
        deep_analysis_max_nodes = _env_int("MISCITE_DEEP_ANALYSIS_MAX_NODES", 2500, min_value=100, max_value=200_000)
        deep_analysis_max_edges = _env_int("MISCITE_DEEP_ANALYSIS_MAX_EDGES", 50_000, min_value=100, max_value=1_000_000)
        deep_analysis_max_workers = _env_int("MISCITE_DEEP_ANALYSIS_MAX_WORKERS", 8, min_value=1, max_value=64)
        deep_analysis_max_references_per_work = _env_int("MISCITE_DEEP_ANALYSIS_MAX_REFERENCES_PER_WORK", 80, min_value=5, max_value=500)
        deep_analysis_max_second_hop_seeds = _env_int("MISCITE_DEEP_ANALYSIS_MAX_SECOND_HOP_SEEDS", 500, min_value=0, max_value=50_000)
        deep_analysis_max_total_citing_refs = _env_int("MISCITE_DEEP_ANALYSIS_MAX_TOTAL_CITING_REFS", 1000, min_value=0, max_value=50_000)
        deep_analysis_max_citing_refs_for_second_hop = _env_int(
            "MISCITE_DEEP_ANALYSIS_MAX_CITING_REFS_FOR_SECOND_HOP", 800, min_value=0, max_value=50_000
        )
        deep_analysis_display_max_key_refs = _env_int("MISCITE_DEEP_ANALYSIS_DISPLAY_MAX_KEY_REFS", 25, min_value=1, max_value=200)
        deep_analysis_display_max_per_category = _env_int("MISCITE_DEEP_ANALYSIS_DISPLAY_MAX_PER_CATEGORY", 20, min_value=1, max_value=200)
        deep_analysis_display_max_openalex_fetches = _env_int(
            "MISCITE_DEEP_ANALYSIS_DISPLAY_MAX_OPENALEX_FETCHES", 140, min_value=0, max_value=2000
        )

        billing_enabled = _env_bool("MISCITE_BILLING_ENABLED", False)
        stripe_secret_key = _env_str("STRIPE_SECRET_KEY", "")
        stripe_webhook_secret = _env_str("STRIPE_WEBHOOK_SECRET", "")
        stripe_price_id = _env_str("STRIPE_PRICE_ID", "")
        stripe_success_url = _env_str("STRIPE_SUCCESS_URL", "http://localhost:8000/billing/success")
        stripe_cancel_url = _env_str("STRIPE_CANCEL_URL", "http://localhost:8000/billing/cancel")

        worker_poll_seconds = _env_float("MISCITE_WORKER_POLL_SECONDS", 1.5, min_value=0.1, max_value=10.0)
        cpu_count = os.cpu_count() or 1
        worker_processes = _env_int("MISCITE_WORKER_PROCESSES", 1, min_value=1, max_value=max(1, cpu_count * 8))

        cookie_secure = _env_bool("MISCITE_COOKIE_SECURE", False)
        trust_proxy = _env_bool("MISCITE_TRUST_PROXY", False)
        maintenance_mode = _env_bool("MISCITE_MAINTENANCE_MODE", False)
        maintenance_message = _env_str(
            "MISCITE_MAINTENANCE_MESSAGE",
            "Maintenance in progress. Uploads are temporarily disabled.",
        )
        load_shed_mode = _env_bool("MISCITE_LOAD_SHED_MODE", False)
        access_token_days = _env_int("MISCITE_ACCESS_TOKEN_DAYS", 7, min_value=1, max_value=3650)
        expose_sensitive_report_fields = _env_bool("MISCITE_EXPOSE_SENSITIVE_REPORT_FIELDS", False)

        rate_limit_enabled = _env_bool("MISCITE_RATE_LIMIT_ENABLED", True)
        rate_limit_window_seconds = _env_int("MISCITE_RATE_LIMIT_WINDOW_SECONDS", 60, min_value=1, max_value=3600)
        rate_limit_login_request = _env_int("MISCITE_RATE_LIMIT_LOGIN_REQUEST", 12, min_value=1, max_value=1000)
        rate_limit_login_verify = _env_int("MISCITE_RATE_LIMIT_LOGIN_VERIFY", 12, min_value=1, max_value=1000)
        rate_limit_upload = _env_int("MISCITE_RATE_LIMIT_UPLOAD", 6, min_value=1, max_value=1000)
        rate_limit_report_access = _env_int("MISCITE_RATE_LIMIT_REPORT_ACCESS", 20, min_value=1, max_value=1000)
        rate_limit_events = _env_int("MISCITE_RATE_LIMIT_EVENTS", 120, min_value=1, max_value=5000)
        rate_limit_stream = _env_int("MISCITE_RATE_LIMIT_STREAM", 6, min_value=1, max_value=1000)
        rate_limit_api = _env_int("MISCITE_RATE_LIMIT_API", 120, min_value=1, max_value=5000)

        job_stale_seconds = _env_int("MISCITE_JOB_STALE_SECONDS", 3600, min_value=60, max_value=86_400)
        job_stale_action = _env_str("MISCITE_JOB_STALE_ACTION", "fail").lower()
        if job_stale_action not in {"fail", "requeue"}:
            raise ValueError("MISCITE_JOB_STALE_ACTION must be 'fail' or 'requeue'.")
        job_max_attempts = _env_int("MISCITE_JOB_MAX_ATTEMPTS", 2, min_value=1, max_value=10)
        job_reap_interval_seconds = _env_int("MISCITE_JOB_REAP_INTERVAL_SECONDS", 60, min_value=5, max_value=3600)

        upload_scan_enabled = _env_bool("MISCITE_UPLOAD_SCAN_ENABLED", False)
        upload_scan_command = _env_str("MISCITE_UPLOAD_SCAN_COMMAND", "")
        upload_scan_timeout_seconds = _env_float("MISCITE_UPLOAD_SCAN_TIMEOUT_SECONDS", 45.0, min_value=5.0, max_value=600.0)

        if load_shed_mode:
            enable_deep_analysis = False
            enable_deep_analysis_llm_key_selection = False
            enable_deep_analysis_llm_suggestions = False
            llm_max_calls = min(llm_max_calls, 5)
            llm_match_max_calls = min(llm_match_max_calls, 10)

        return cls(
            db_url=db_url,
            storage_dir=storage_dir,
            max_upload_mb=max_upload_mb,
            max_body_mb=max_body_mb,
            max_unpacked_mb=max_unpacked_mb,
            session_days=session_days,
            login_code_ttl_minutes=login_code_ttl_minutes,
            login_code_length=login_code_length,
            mailgun_api_key=mailgun_api_key,
            mailgun_domain=mailgun_domain,
            mailgun_sender=mailgun_sender,
            mailgun_base_url=mailgun_base_url,
            turnstile_site_key=turnstile_site_key,
            turnstile_secret_key=turnstile_secret_key,
            turnstile_verify_url=turnstile_verify_url,
            log_level=log_level,
            text_extract_backend=text_extract_backend,
            text_extract_timeout_seconds=text_extract_timeout_seconds,
            text_extract_subprocess=text_extract_subprocess,
            text_extract_process_context=text_extract_process_context,
            accelerator=accelerator,
            crossref_mailto=crossref_mailto,
            crossref_user_agent=crossref_user_agent,
            retractionwatch_csv=retractionwatch_csv,
            predatory_csv=predatory_csv,
            rw_sync_enabled=rw_sync_enabled,
            rw_sync_method=rw_sync_method,
            rw_sync_interval_hours=rw_sync_interval_hours,
            rw_git_repo=rw_git_repo,
            rw_git_dir=rw_git_dir,
            rw_http_url=rw_http_url,
            retraction_api_enabled=retraction_api_enabled,
            retraction_api_mode=retraction_api_mode,
            retraction_api_url=retraction_api_url,
            retraction_api_token=retraction_api_token,
            predatory_api_enabled=predatory_api_enabled,
            predatory_api_mode=predatory_api_mode,
            predatory_api_url=predatory_api_url,
            predatory_api_token=predatory_api_token,
            predatory_sync_enabled=predatory_sync_enabled,
            predatory_sync_interval_hours=predatory_sync_interval_hours,
            predatory_publishers_url=predatory_publishers_url,
            predatory_journals_url=predatory_journals_url,
            api_timeout_seconds=api_timeout_seconds,
            openrouter_api_key=openrouter_api_key,
            llm_model=llm_model,
            enable_llm_inappropriate=enable_llm_inappropriate,
            llm_max_calls=llm_max_calls,
            llm_parse_model=llm_parse_model,
            llm_match_model=llm_match_model,
            llm_deep_analysis_model=llm_deep_analysis_model,
            llm_match_max_calls=llm_match_max_calls,
            llm_bib_parse_max_chars=llm_bib_parse_max_chars,
            llm_bib_parse_max_refs=llm_bib_parse_max_refs,
            llm_citation_parse_max_chars=llm_citation_parse_max_chars,
            llm_citation_parse_max_lines=llm_citation_parse_max_lines,
            llm_citation_parse_max_candidate_chars=llm_citation_parse_max_candidate_chars,
            enable_local_nli=enable_local_nli,
            local_nli_model=local_nli_model,
            enable_deep_analysis=enable_deep_analysis,
            enable_deep_analysis_llm_key_selection=enable_deep_analysis_llm_key_selection,
            enable_deep_analysis_llm_suggestions=enable_deep_analysis_llm_suggestions,
            deep_analysis_min_confidence=deep_analysis_min_confidence,
            deep_analysis_max_original_refs=deep_analysis_max_original_refs,
            deep_analysis_paper_excerpt_max_chars=deep_analysis_paper_excerpt_max_chars,
            deep_analysis_max_nodes=deep_analysis_max_nodes,
            deep_analysis_max_edges=deep_analysis_max_edges,
            deep_analysis_max_workers=deep_analysis_max_workers,
            deep_analysis_max_references_per_work=deep_analysis_max_references_per_work,
            deep_analysis_max_second_hop_seeds=deep_analysis_max_second_hop_seeds,
            deep_analysis_max_total_citing_refs=deep_analysis_max_total_citing_refs,
            deep_analysis_max_citing_refs_for_second_hop=deep_analysis_max_citing_refs_for_second_hop,
            deep_analysis_display_max_key_refs=deep_analysis_display_max_key_refs,
            deep_analysis_display_max_per_category=deep_analysis_display_max_per_category,
            deep_analysis_display_max_openalex_fetches=deep_analysis_display_max_openalex_fetches,
            billing_enabled=billing_enabled,
            stripe_secret_key=stripe_secret_key,
            stripe_webhook_secret=stripe_webhook_secret,
            stripe_price_id=stripe_price_id,
            stripe_success_url=stripe_success_url,
            stripe_cancel_url=stripe_cancel_url,
            worker_poll_seconds=worker_poll_seconds,
            worker_processes=worker_processes,
            cookie_secure=cookie_secure,
            trust_proxy=trust_proxy,
            maintenance_mode=maintenance_mode,
            maintenance_message=maintenance_message,
            load_shed_mode=load_shed_mode,
            access_token_days=access_token_days,
            expose_sensitive_report_fields=expose_sensitive_report_fields,
            rate_limit_enabled=rate_limit_enabled,
            rate_limit_window_seconds=rate_limit_window_seconds,
            rate_limit_login_request=rate_limit_login_request,
            rate_limit_login_verify=rate_limit_login_verify,
            rate_limit_upload=rate_limit_upload,
            rate_limit_report_access=rate_limit_report_access,
            rate_limit_events=rate_limit_events,
            rate_limit_stream=rate_limit_stream,
            rate_limit_api=rate_limit_api,
            job_stale_seconds=job_stale_seconds,
            job_stale_action=job_stale_action,
            job_max_attempts=job_max_attempts,
            job_reap_interval_seconds=job_reap_interval_seconds,
            upload_scan_enabled=upload_scan_enabled,
            upload_scan_command=upload_scan_command,
            upload_scan_timeout_seconds=upload_scan_timeout_seconds,
        )
