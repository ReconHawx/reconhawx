--
-- PostgreSQL database dump
--

-- Dumped from database version 15.15 (Debian 15.15-1.pgdg13+1)
-- Dumped by pg_dump version 17.8

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: update_aws_credentials_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_aws_credentials_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_broken_links_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_broken_links_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_internal_service_tokens_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_internal_service_tokens_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_social_media_credentials_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_social_media_credentials_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: action_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.action_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id character varying(255) NOT NULL,
    action_type character varying(100) NOT NULL,
    user_id uuid NOT NULL,
    old_value jsonb,
    new_value jsonb,
    metadata jsonb,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE action_logs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.action_logs IS 'Generic table for logging user actions on various entities';


--
-- Name: COLUMN action_logs.entity_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.action_logs.entity_type IS 'Type of entity being acted upon (e.g., typosquat_finding)';


--
-- Name: COLUMN action_logs.entity_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.action_logs.entity_id IS 'Unique identifier of the entity';


--
-- Name: COLUMN action_logs.action_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.action_logs.action_type IS 'Type of action performed (e.g., status_change)';


--
-- Name: COLUMN action_logs.old_value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.action_logs.old_value IS 'Previous state of the entity (JSON)';


--
-- Name: COLUMN action_logs.new_value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.action_logs.new_value IS 'New state of the entity (JSON)';


--
-- Name: COLUMN action_logs.metadata; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.action_logs.metadata IS 'Additional action metadata (comments, action_taken, etc.)';


--
-- Name: ips; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ips (
    id uuid NOT NULL,
    ip_address inet NOT NULL,
    ptr_record character varying(255),
    service_provider character varying(255),
    program_id uuid NOT NULL,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: programs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.programs (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    domain_regex text[],
    cidr_list text[],
    safe_registrar text[],
    safe_ssl_issuer text[],
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    phishlabs_api_key character varying,
    notification_settings jsonb DEFAULT '{}'::jsonb,
    threatstream_api_key character varying(255),
    threatstream_api_user character varying(255),
    recordedfuture_api_key character varying(255),
    out_of_scope_regex text[] DEFAULT '{}'::text[],
    protected_domains text[] DEFAULT '{}'::text[],
    typosquat_auto_resolve_settings jsonb DEFAULT '{}'::jsonb,
    ai_analysis_settings jsonb DEFAULT '{}'::jsonb,
    protected_subdomain_prefixes text[] DEFAULT '{}'::text[],
    typosquat_filtering_settings jsonb DEFAULT '{}'::jsonb,
    event_handler_addon_mode boolean DEFAULT false NOT NULL,
    ct_monitoring_enabled boolean DEFAULT false NOT NULL,
    ct_monitor_program_settings jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: COLUMN programs.threatstream_api_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.threatstream_api_key IS 'API key for Threatstream integration';


--
-- Name: COLUMN programs.threatstream_api_user; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.threatstream_api_user IS 'API user for Threatstream integration';


--
-- Name: COLUMN programs.recordedfuture_api_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.recordedfuture_api_key IS 'API key for RecordedFuture integration';


--
-- Name: COLUMN programs.out_of_scope_regex; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.out_of_scope_regex IS 'Array of regex patterns for domains that should be excluded from scope, even if they match in-scope patterns. Out-of-scope patterns take precedence over in-scope patterns.';


--
-- Name: COLUMN programs.protected_domains; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.protected_domains IS 'List of apex domains to monitor for typosquatting and CT alerts';


--
-- Name: COLUMN programs.typosquat_auto_resolve_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.typosquat_auto_resolve_settings IS 'Schema: {"min_parked_confidence_percent": 80, "min_similarity_percent": 85.0}';


--
-- Name: COLUMN programs.ai_analysis_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.ai_analysis_settings IS 'Schema: {"enabled": false, "model": "llama3:latest", "auto_action_enabled": false, "auto_action_min_confidence": 80, "auto_dismiss_benign": false, "auto_monitor_medium": false, "reanalyze_after_days": 30}';


--
-- Name: COLUMN programs.protected_subdomain_prefixes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.protected_subdomain_prefixes IS 'List of subdomain prefixes that automatically qualify a typosquat domain for insertion (e.g. service.login, acces.mobile)';


--
-- Name: COLUMN programs.typosquat_filtering_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.typosquat_filtering_settings IS 'Settings for pre-insertion typosquat filtering: {"min_similarity_percent": 60.0, "enabled": true}';


--
-- Name: COLUMN programs.ct_monitor_program_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.programs.ct_monitor_program_settings IS 'CT monitor tuning per program: {"tld_filter": "com,net,org", "similarity_threshold": 0.75}';


--
-- Name: services; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.services (
    id uuid NOT NULL,
    ip_id uuid NOT NULL,
    port integer NOT NULL,
    protocol character varying(10),
    service_name character varying(50),
    banner text,
    program_id uuid NOT NULL,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    nerva_metadata jsonb
);


--
-- Name: COLUMN services.nerva_metadata; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.services.nerva_metadata IS 'Nerva service fingerprinting metadata (cpes, confidence, algo, auth_methods, etc.)';


--
-- Name: active_services; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.active_services AS
 SELECT i.ip_address,
    srv.port,
    srv.protocol,
    srv.service_name,
    srv.banner,
    p.name AS program_name,
    srv.created_at,
    srv.updated_at
   FROM ((public.services srv
     JOIN public.ips i ON ((srv.ip_id = i.id)))
     JOIN public.programs p ON ((srv.program_id = p.id)))
  ORDER BY i.ip_address, srv.port;


--
-- Name: apex_domains; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.apex_domains (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    program_id uuid NOT NULL,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    whois_status character varying(64),
    whois_registrar text,
    whois_creation_date timestamp without time zone,
    whois_expiration_date timestamp without time zone,
    whois_updated_date timestamp without time zone,
    whois_name_servers text[],
    whois_registrant_name text,
    whois_registrant_org text,
    whois_registrant_country character varying(128),
    whois_admin_email character varying(320),
    whois_tech_email character varying(320),
    whois_dnssec character varying(64),
    whois_registry_server character varying(255),
    whois_response_source character varying(64),
    whois_raw_response text,
    whois_error text,
    whois_checked_at timestamp without time zone
);


--
-- Name: api_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_tokens (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(255) NOT NULL,
    name character varying(100) NOT NULL,
    description character varying(500),
    permissions character varying(100)[],
    is_active boolean,
    expires_at timestamp without time zone,
    last_used_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: certificates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.certificates (
    id uuid NOT NULL,
    subject_dn text NOT NULL,
    subject_cn character varying(255) NOT NULL,
    subject_alternative_names character varying(255)[],
    valid_from timestamp without time zone NOT NULL,
    valid_until timestamp without time zone NOT NULL,
    issuer_dn text NOT NULL,
    issuer_cn character varying(255) NOT NULL,
    issuer_organization character varying(255)[],
    serial_number character varying(255) NOT NULL,
    fingerprint_hash character varying(255) NOT NULL,
    program_id uuid,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    tls_version character varying(255),
    cipher character varying(255)
);


--
-- Name: COLUMN certificates.tls_version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.certificates.tls_version IS 'TLS version';


--
-- Name: COLUMN certificates.cipher; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.certificates.cipher IS 'Cipher';


--
-- Name: subdomains; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subdomains (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    apex_domain_id uuid NOT NULL,
    program_id uuid NOT NULL,
    cname_record character varying(255),
    is_wildcard boolean,
    wildcard_types character varying(10)[],
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: urls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.urls (
    id uuid NOT NULL,
    url text NOT NULL,
    hostname character varying(255) NOT NULL,
    port integer,
    path text,
    scheme character varying(10),
    http_status_code smallint,
    http_method character varying(10),
    response_time_ms integer,
    content_type character varying(255),
    content_length bigint,
    line_count integer,
    word_count integer,
    title text,
    final_url text,
    response_body_hash character varying(255),
    body_preview text,
    favicon_hash character varying(255),
    favicon_url text,
    redirect_chain jsonb,
    chain_status_codes smallint[],
    certificate_id uuid,
    program_id uuid,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    subdomain_id uuid
);


--
-- Name: COLUMN urls.subdomain_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.urls.subdomain_id IS 'Subdomain (hostname) this URL belongs to';


--
-- Name: asset_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.asset_summary AS
 SELECT p.name AS program_name,
    p.id AS program_id,
    count(DISTINCT ad.id) AS apex_domains_count,
    count(DISTINCT s.id) AS subdomains_count,
    count(DISTINCT i.id) AS ips_count,
    count(DISTINCT srv.id) AS services_count,
    count(DISTINCT u.id) AS urls_count,
    count(DISTINCT c.id) AS certificates_count
   FROM ((((((public.programs p
     LEFT JOIN public.apex_domains ad ON ((p.id = ad.program_id)))
     LEFT JOIN public.subdomains s ON ((p.id = s.program_id)))
     LEFT JOIN public.ips i ON ((p.id = i.program_id)))
     LEFT JOIN public.services srv ON ((p.id = srv.program_id)))
     LEFT JOIN public.urls u ON ((p.id = u.program_id)))
     LEFT JOIN public.certificates c ON ((p.id = c.program_id)))
  GROUP BY p.id, p.name
  ORDER BY p.name;


--
-- Name: aws_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aws_credentials (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    access_key character varying(255) NOT NULL,
    secret_access_key character varying(255) NOT NULL,
    default_region character varying(50) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE aws_credentials; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.aws_credentials IS 'Stores AWS credentials for system-wide use';


--
-- Name: COLUMN aws_credentials.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.aws_credentials.name IS 'Human-readable name for the credential set';


--
-- Name: COLUMN aws_credentials.access_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.aws_credentials.access_key IS 'AWS access key ID';


--
-- Name: COLUMN aws_credentials.secret_access_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.aws_credentials.secret_access_key IS 'AWS secret access key (should be encrypted in production)';


--
-- Name: COLUMN aws_credentials.default_region; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.aws_credentials.default_region IS 'Default AWS region for this credential set';


--
-- Name: COLUMN aws_credentials.is_active; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.aws_credentials.is_active IS 'Whether the credential set is currently active';


--
-- Name: broken_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.broken_links (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    program_id uuid NOT NULL,
    link_type character varying(20) DEFAULT 'social_media'::character varying NOT NULL,
    media_type character varying(50),
    domain character varying(255),
    reason character varying(100),
    status character varying(20) NOT NULL,
    url text,
    error_code character varying(50),
    response_data jsonb,
    checked_at timestamp with time zone DEFAULT now() NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE broken_links; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.broken_links IS 'Stores broken link findings (social media and general links)';


--
-- Name: COLUMN broken_links.program_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.program_id IS 'Foreign key to programs table';


--
-- Name: COLUMN broken_links.link_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.link_type IS 'Type of link: social_media or general';


--
-- Name: COLUMN broken_links.media_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.media_type IS 'Social media platform: facebook, instagram, twitter, x, linkedin - nullable for general links';


--
-- Name: COLUMN broken_links.domain; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.domain IS 'Domain name for general broken links (extracted from URL)';


--
-- Name: COLUMN broken_links.reason; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.reason IS 'Reason for broken link (e.g., domain_not_registered)';


--
-- Name: COLUMN broken_links.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.status IS 'Status: valid, broken, error, throttled';


--
-- Name: COLUMN broken_links.url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.url IS 'Full URL that was checked';


--
-- Name: COLUMN broken_links.error_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.error_code IS 'HTTP status code or error type';


--
-- Name: COLUMN broken_links.response_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.response_data IS 'Raw response data for debugging';


--
-- Name: COLUMN broken_links.checked_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.broken_links.checked_at IS 'Timestamp when the check was performed';


--
-- Name: subdomain_ips; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subdomain_ips (
    id uuid NOT NULL,
    subdomain_id uuid NOT NULL,
    ip_id uuid NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: domain_resolution; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.domain_resolution AS
 SELECT s.name AS subdomain,
    s.id AS subdomain_id,
    ad.name AS apex_domain,
    i.ip_address,
    i.ptr_record,
    s.cname_record,
    s.is_wildcard,
    p.name AS program_name,
    s.created_at,
    s.updated_at
   FROM ((((public.subdomains s
     JOIN public.programs p ON ((s.program_id = p.id)))
     LEFT JOIN public.apex_domains ad ON ((s.apex_domain_id = ad.id)))
     LEFT JOIN public.subdomain_ips si ON ((s.id = si.subdomain_id)))
     LEFT JOIN public.ips i ON ((si.ip_id = i.id)))
  ORDER BY s.name, i.ip_address;


--
-- Name: droopescan_findings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.droopescan_findings (
    id uuid NOT NULL,
    url text NOT NULL,
    program_id uuid NOT NULL,
    cms_name character varying(50),
    host text,
    plugins_data jsonb,
    hostname character varying(255),
    port integer,
    scheme character varying(10),
    notes text,
    status character varying(50),
    assigned_to character varying(255),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: event_handler_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_handler_configs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    program_id uuid,
    handler_id character varying(100) NOT NULL,
    event_type character varying(100) NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: TABLE event_handler_configs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.event_handler_configs IS 'Event handler configuration: one row per handler, program_id NULL = global';


--
-- Name: extracted_link_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extracted_link_sources (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    extracted_link_id uuid NOT NULL,
    source_url_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: extracted_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extracted_links (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    link_url text NOT NULL,
    program_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: internal_service_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.internal_service_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    token_hash character varying(64) NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_used_at timestamp with time zone,
    expires_at timestamp with time zone
);


--
-- Name: TABLE internal_service_tokens; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.internal_service_tokens IS 'Stores internal service authentication tokens for service-to-service communication';


--
-- Name: COLUMN internal_service_tokens.token_hash; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.internal_service_tokens.token_hash IS 'SHA-256 hash of the internal service token';


--
-- Name: COLUMN internal_service_tokens.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.internal_service_tokens.name IS 'Human-readable name for the token';


--
-- Name: COLUMN internal_service_tokens.description; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.internal_service_tokens.description IS 'Optional description of the token purpose';


--
-- Name: COLUMN internal_service_tokens.is_active; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.internal_service_tokens.is_active IS 'Whether the token is currently active';


--
-- Name: COLUMN internal_service_tokens.last_used_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.internal_service_tokens.last_used_at IS 'Timestamp of last token usage';


--
-- Name: COLUMN internal_service_tokens.expires_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.internal_service_tokens.expires_at IS 'Optional token expiration timestamp';


--
-- Name: job_execution_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_execution_history (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    execution_id character varying(255) NOT NULL,
    schedule_id character varying(255) NOT NULL,
    job_id character varying(255) NOT NULL,
    status character varying(20) NOT NULL,
    started_at timestamp without time zone NOT NULL,
    completed_at timestamp without time zone,
    duration_seconds integer,
    error_message text,
    results jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE job_execution_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.job_execution_history IS 'Stores execution history for scheduled jobs';


--
-- Name: job_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_status (
    id uuid NOT NULL,
    job_id character varying(255) NOT NULL,
    job_type character varying(100) NOT NULL,
    user_id uuid,
    status character varying(20) NOT NULL,
    progress smallint,
    message text,
    results jsonb,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: nuclei_findings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nuclei_findings (
    id uuid NOT NULL,
    url text,
    template_id character varying(255) NOT NULL,
    template_url text,
    name character varying(500) NOT NULL,
    severity character varying(20) NOT NULL,
    finding_type character varying(50) NOT NULL,
    tags character varying(100)[],
    description text,
    matched_at text,
    matcher_name character varying(255),
    ip_id uuid,
    hostname character varying(255),
    port integer,
    scheme character varying(10),
    protocol character varying(10),
    matched_line text,
    extracted_results text[],
    info_data jsonb,
    program_id uuid NOT NULL,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    template_path text
);


--
-- Name: nuclei_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nuclei_templates (
    id uuid NOT NULL,
    template_id character varying(255) NOT NULL,
    name character varying(500) NOT NULL,
    author character varying(255),
    severity character varying(20),
    description text,
    tags character varying(100)[],
    yaml_content text NOT NULL,
    is_active boolean,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: recon_task_parameters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recon_task_parameters (
    id uuid NOT NULL,
    recon_task character varying(100) NOT NULL,
    parameters jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refresh_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    is_revoked boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    last_used_at timestamp with time zone DEFAULT now(),
    device_info text,
    ip_address inet
);


--
-- Name: TABLE refresh_tokens; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.refresh_tokens IS 'Stores refresh tokens for JWT authentication with device tracking and revocation support';


--
-- Name: COLUMN refresh_tokens.token_hash; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.refresh_tokens.token_hash IS 'Hashed refresh token value for security';


--
-- Name: COLUMN refresh_tokens.device_info; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.refresh_tokens.device_info IS 'User agent or device information for session tracking';


--
-- Name: COLUMN refresh_tokens.ip_address; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.refresh_tokens.ip_address IS 'IP address where token was created for security monitoring';


--
-- Name: scheduled_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduled_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    schedule_id character varying(255) NOT NULL,
    job_type character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    schedule_data jsonb NOT NULL,
    job_data jsonb NOT NULL,
    user_id uuid NOT NULL,
    status character varying(20) DEFAULT 'scheduled'::character varying NOT NULL,
    tags text[] DEFAULT '{}'::text[],
    next_run timestamp without time zone,
    last_run timestamp without time zone,
    total_executions integer DEFAULT 0,
    successful_executions integer DEFAULT 0,
    failed_executions integer DEFAULT 0,
    enabled boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    workflow_variables jsonb DEFAULT '{}'::jsonb,
    program_id uuid NOT NULL
);


--
-- Name: TABLE scheduled_jobs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.scheduled_jobs IS 'Stores scheduled job configurations for automated tasks';


--
-- Name: COLUMN scheduled_jobs.workflow_variables; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduled_jobs.workflow_variables IS 'Stores workflow variable values for scheduled workflow jobs';


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version character varying(50) NOT NULL,
    applied_at timestamp without time zone NOT NULL,
    checksum character varying(64) NOT NULL,
    execution_time_ms integer NOT NULL,
    success boolean NOT NULL,
    error_message text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: screenshot_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.screenshot_files (
    id uuid NOT NULL,
    file_content bytea NOT NULL,
    content_type character varying(100) NOT NULL,
    filename character varying(255) NOT NULL,
    file_size bigint NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: screenshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.screenshots (
    id uuid NOT NULL,
    url_id uuid NOT NULL,
    file_id uuid NOT NULL,
    image_hash character varying(255) NOT NULL,
    workflow_id character varying(255),
    capture_count integer,
    last_captured_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL,
    step_name character varying(255),
    program_name character varying(255),
    extracted_text text
);


--
-- Name: typosquat_domains; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.typosquat_domains (
    id uuid NOT NULL,
    typo_domain character varying(255) NOT NULL,
    fuzzer_types character varying(50)[],
    risk_score integer,
    program_id uuid NOT NULL,
    detected_at timestamp without time zone NOT NULL,
    fixed_at timestamp without time zone,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    domain_registered boolean,
    dns_a_records text[],
    dns_mx_records text[],
    is_wildcard boolean,
    wildcard_types text[],
    geoip_country text,
    geoip_city text,
    geoip_organization text,
    risk_analysis_total_score integer,
    risk_analysis_risk_level text,
    risk_analysis_version text,
    risk_analysis_timestamp timestamp without time zone,
    risk_analysis_category_scores jsonb,
    risk_analysis_risk_factors jsonb,
    status character varying(20) DEFAULT 'new'::character varying,
    assigned_to character varying(255),
    threatstream_data jsonb,
    phishlabs_data jsonb,
    recordedfuture_data jsonb,
    source character varying(255),
    action_taken character varying(255)[],
    is_parked boolean,
    parked_detection_timestamp timestamp without time zone,
    parked_detection_reasons jsonb,
    dns_ns_records text[],
    parked_confidence integer,
    protected_domain_similarities jsonb DEFAULT '[]'::jsonb,
    auto_resolve boolean DEFAULT false,
    ai_analysis jsonb,
    ai_analyzed_at timestamp without time zone,
    apex_typosquat_domain_id uuid NOT NULL
);


--
-- Name: COLUMN typosquat_domains.threatstream_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.threatstream_data IS 'Full Threatstream API response object stored as JSONB for complete data preservation';


--
-- Name: COLUMN typosquat_domains.phishlabs_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.phishlabs_data IS 'Consolidated PhishLabs data in JSONB format containing incident_id, url, category_code, category_name, status, comment, product, create_date, assignee, last_comment, group_category_name, action_description, status_description, mitigation_start, date_resolved, severity_name, mx_record, ticket_status, resolution_status, incident_status, last_updated';


--
-- Name: COLUMN typosquat_domains.recordedfuture_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.recordedfuture_data IS 'RecordedFuture data in JSONB format';


--
-- Name: COLUMN typosquat_domains.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.source IS 'Source of the data';


--
-- Name: COLUMN typosquat_domains.action_taken; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.action_taken IS 'Action taken';


--
-- Name: COLUMN typosquat_domains.is_parked; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.is_parked IS 'Indicates if the domain is detected as parked';


--
-- Name: COLUMN typosquat_domains.parked_detection_timestamp; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.parked_detection_timestamp IS 'Timestamp when parked domain was detected';


--
-- Name: COLUMN typosquat_domains.parked_detection_reasons; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.parked_detection_reasons IS 'JSON object containing detection indicators (nameservers matched, keywords found, etc.)';


--
-- Name: COLUMN typosquat_domains.dns_ns_records; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.dns_ns_records IS 'DNS NS records';


--
-- Name: COLUMN typosquat_domains.parked_confidence; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.parked_confidence IS 'Confidence score (0-100) that the domain is parked, based on DNS/HTTP indicators and similarity to protected domains';


--
-- Name: COLUMN typosquat_domains.protected_domain_similarities; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.protected_domain_similarities IS 'Array of similarity scores with protected domains. Schema: [{"protected_domain": "example.com", "similarity_percent": 95.0, "calculated_at": "2025-01-27T10:30:00Z"}]';


--
-- Name: COLUMN typosquat_domains.auto_resolve; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.auto_resolve IS 'True when finding meets program thresholds for auto-resolve (parked confidence + similarity with protected domain)';


--
-- Name: COLUMN typosquat_domains.ai_analysis; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.ai_analysis IS 'Structured AI analysis output: {model, threat_level, confidence, summary, recommended_action, reasoning, indicators, context_used}';


--
-- Name: COLUMN typosquat_domains.ai_analyzed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.typosquat_domains.ai_analyzed_at IS 'Timestamp of last AI analysis run';


--
-- Name: security_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.security_summary AS
 SELECT p.name AS program_name,
    p.id AS program_id,
    count(DISTINCT nf.id) AS nuclei_findings_count,
    count(DISTINCT
        CASE
            WHEN ((nf.severity)::text = 'critical'::text) THEN nf.id
            ELSE NULL::uuid
        END) AS critical_findings,
    count(DISTINCT
        CASE
            WHEN ((nf.severity)::text = 'high'::text) THEN nf.id
            ELSE NULL::uuid
        END) AS high_findings,
    count(DISTINCT
        CASE
            WHEN ((nf.severity)::text = 'medium'::text) THEN nf.id
            ELSE NULL::uuid
        END) AS medium_findings,
    count(DISTINCT
        CASE
            WHEN ((nf.severity)::text = 'low'::text) THEN nf.id
            ELSE NULL::uuid
        END) AS low_findings,
    count(DISTINCT td.id) AS typosquat_domains_count,
    count(DISTINCT
        CASE
            WHEN (td.fixed_at IS NULL) THEN td.id
            ELSE NULL::uuid
        END) AS active_typosquats
   FROM ((public.programs p
     LEFT JOIN public.nuclei_findings nf ON ((p.id = nf.program_id)))
     LEFT JOIN public.typosquat_domains td ON ((p.id = td.program_id)))
  GROUP BY p.id, p.name
  ORDER BY p.name;


--
-- Name: social_media_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.social_media_credentials (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    platform character varying(50) NOT NULL,
    username character varying(255),
    email character varying(255),
    password character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE social_media_credentials; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.social_media_credentials IS 'Stores social media credentials for system-wide use';


--
-- Name: COLUMN social_media_credentials.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.social_media_credentials.name IS 'Human-readable name for the credential set';


--
-- Name: COLUMN social_media_credentials.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.social_media_credentials.platform IS 'Platform: facebook, instagram, twitter, linkedin';


--
-- Name: COLUMN social_media_credentials.username; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.social_media_credentials.username IS 'Username for the platform';


--
-- Name: COLUMN social_media_credentials.email; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.social_media_credentials.email IS 'Email address (for Instagram/Twitter)';


--
-- Name: COLUMN social_media_credentials.password; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.social_media_credentials.password IS 'Password (should be encrypted in production)';


--
-- Name: COLUMN social_media_credentials.is_active; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.social_media_credentials.is_active IS 'Whether the credential set is currently active';


--
-- Name: system_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_settings (
    key character varying(100) NOT NULL,
    value jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: TABLE system_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.system_settings IS 'Key-value store for system-wide configuration (e.g. ai_settings)';


--
-- Name: COLUMN system_settings.key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.system_settings.key IS 'Setting key (e.g. ai_settings)';


--
-- Name: COLUMN system_settings.value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.system_settings.value IS 'JSONB value for the setting';


--
-- Name: technologies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.technologies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(100) NOT NULL,
    program_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: typosquat_apex_domains; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.typosquat_apex_domains (
    id uuid NOT NULL,
    program_id uuid NOT NULL,
    apex_domain character varying(255) NOT NULL,
    whois_registrar text,
    whois_creation_date timestamp without time zone,
    whois_expiration_date timestamp without time zone,
    whois_registrant_name text,
    whois_registrant_country text,
    whois_admin_email text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: typosquat_certificates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.typosquat_certificates (
    id uuid NOT NULL,
    subject_dn text NOT NULL,
    subject_cn character varying(255) NOT NULL,
    subject_alternative_names character varying(255)[],
    valid_from timestamp without time zone NOT NULL,
    valid_until timestamp without time zone NOT NULL,
    issuer_dn text NOT NULL,
    issuer_cn character varying(255) NOT NULL,
    issuer_organization character varying(255)[],
    serial_number character varying(255) NOT NULL,
    fingerprint_hash character varying(255) NOT NULL,
    program_id uuid,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: typosquat_screenshot_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.typosquat_screenshot_files (
    id uuid NOT NULL,
    file_content bytea NOT NULL,
    content_type character varying(100) NOT NULL,
    filename character varying(255) NOT NULL,
    file_size bigint NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: typosquat_screenshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.typosquat_screenshots (
    id uuid NOT NULL,
    url_id uuid NOT NULL,
    file_id uuid NOT NULL,
    image_hash character varying(255) NOT NULL,
    workflow_id character varying(255),
    capture_count integer,
    last_captured_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL,
    step_name character varying(255),
    program_name character varying(255),
    extracted_text text,
    source_created_at timestamp without time zone,
    source character varying(255)
);


--
-- Name: typosquat_urls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.typosquat_urls (
    id uuid NOT NULL,
    url text NOT NULL,
    hostname character varying(255) NOT NULL,
    port integer,
    path text,
    scheme character varying(10),
    http_status_code smallint,
    http_method character varying(10),
    response_time_ms integer,
    content_type character varying(255),
    content_length bigint,
    line_count integer,
    word_count integer,
    title text,
    final_url text,
    response_body_hash character varying(255),
    body_preview text,
    favicon_hash character varying(255),
    favicon_url text,
    redirect_chain jsonb,
    chain_status_codes smallint[],
    extracted_links text[],
    typosquat_certificate_id uuid,
    program_id uuid,
    typosquat_domain_id uuid,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    technologies character varying(100)[]
);


--
-- Name: url_services; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.url_services (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    url_id uuid NOT NULL,
    service_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: url_technologies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.url_technologies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    technology_id uuid NOT NULL,
    url_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: user_program_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_program_permissions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    program_id uuid NOT NULL,
    permission_level character varying(20) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    username character varying(150) NOT NULL,
    email character varying(254),
    password_hash character varying(255) NOT NULL,
    first_name character varying(150),
    last_name character varying(150),
    is_active boolean,
    is_superuser boolean,
    roles character varying(50)[],
    created_at timestamp without time zone NOT NULL,
    last_login timestamp without time zone,
    updated_at timestamp without time zone NOT NULL,
    rf_uhash character varying(255),
    hackerone_api_token character varying(255),
    hackerone_api_user character varying(255),
    intigriti_api_token character varying(255),
    must_change_password boolean DEFAULT false NOT NULL
);


--
-- Name: COLUMN users.rf_uhash; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.users.rf_uhash IS 'RecordedFuture user hash';


--
-- Name: COLUMN users.hackerone_api_token; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.users.hackerone_api_token IS 'API token for hackerone integration';


--
-- Name: COLUMN users.hackerone_api_user; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.users.hackerone_api_user IS 'API user for hackerone integration';


--
-- Name: COLUMN users.intigriti_api_token; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.users.intigriti_api_token IS 'API token for intigriti integration';


--
-- Name: wordlist_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wordlist_files (
    id uuid NOT NULL,
    file_content bytea NOT NULL,
    content_type character varying(100) NOT NULL,
    filename character varying(255) NOT NULL,
    file_size bigint NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: wordlists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wordlists (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    word_count integer NOT NULL,
    tags character varying(100)[],
    file_id uuid,
    program_id uuid,
    created_by character varying(255),
    is_active boolean,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    is_dynamic boolean DEFAULT false NOT NULL,
    dynamic_type character varying(50),
    dynamic_config jsonb,
    CONSTRAINT chk_dynamic_type_required CHECK (((is_dynamic = false) OR ((is_dynamic = true) AND (dynamic_type IS NOT NULL)))),
    CONSTRAINT chk_file_id_required_for_static CHECK (((is_dynamic = true) OR ((is_dynamic = false) AND (file_id IS NOT NULL))))
);


--
-- Name: COLUMN wordlists.is_dynamic; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wordlists.is_dynamic IS 'Whether this wordlist generates content dynamically from program assets';


--
-- Name: COLUMN wordlists.dynamic_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wordlists.dynamic_type IS 'Type of dynamic generation: subdomain_prefixes, apex_domains, url_paths, etc.';


--
-- Name: COLUMN wordlists.dynamic_config; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wordlists.dynamic_config IS 'JSON configuration for dynamic generation, e.g., {"program_id": "..."}';


--
-- Name: workflow_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_logs (
    id uuid NOT NULL,
    workflow_name character varying(255) NOT NULL,
    program_id uuid NOT NULL,
    execution_id character varying(255) NOT NULL,
    status character varying(20) NOT NULL,
    result_data jsonb,
    workflow_steps jsonb,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    workflow_definition jsonb,
    runner_pod_output text,
    task_execution_logs jsonb DEFAULT '[]'::jsonb,
    workflow_id uuid
);


--
-- Name: COLUMN workflow_logs.started_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.workflow_logs.started_at IS 'Timestamp when the workflow execution started (defaults to creation time)';


--
-- Name: COLUMN workflow_logs.completed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.workflow_logs.completed_at IS 'Timestamp when the workflow execution completed (NULL if still running or failed)';


--
-- Name: workflows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflows (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    program_id uuid,
    description text,
    variables jsonb,
    inputs jsonb,
    steps jsonb,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: wpscan_findings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wpscan_findings (
    id uuid NOT NULL,
    url text NOT NULL,
    program_id uuid NOT NULL,
    item_name character varying(255) NOT NULL,
    item_type character varying(50) NOT NULL,
    vulnerability_type character varying(100),
    severity character varying(20),
    title text,
    description text,
    fixed_in character varying(100),
    "references" text[],
    cve_ids text[],
    enumeration_data jsonb,
    hostname character varying(255),
    port integer,
    scheme character varying(10),
    notes text,
    status character varying(50),
    assigned_to character varying(255),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: action_logs action_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_pkey PRIMARY KEY (id);


--
-- Name: apex_domains apex_domains_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apex_domains
    ADD CONSTRAINT apex_domains_pkey PRIMARY KEY (id);


--
-- Name: api_tokens api_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_tokens
    ADD CONSTRAINT api_tokens_pkey PRIMARY KEY (id);


--
-- Name: api_tokens api_tokens_token_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_tokens
    ADD CONSTRAINT api_tokens_token_hash UNIQUE (token_hash);


--
-- Name: aws_credentials aws_credentials_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aws_credentials
    ADD CONSTRAINT aws_credentials_name_key UNIQUE (name);


--
-- Name: aws_credentials aws_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aws_credentials
    ADD CONSTRAINT aws_credentials_pkey PRIMARY KEY (id);


--
-- Name: broken_links broken_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broken_links
    ADD CONSTRAINT broken_links_pkey PRIMARY KEY (id);


--
-- Name: certificates certificates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_pkey PRIMARY KEY (id);


--
-- Name: droopescan_findings droopescan_findings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.droopescan_findings
    ADD CONSTRAINT droopescan_findings_pkey PRIMARY KEY (id);


--
-- Name: droopescan_findings droopescan_findings_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.droopescan_findings
    ADD CONSTRAINT droopescan_findings_unique UNIQUE (url, program_id);


--
-- Name: event_handler_configs event_handler_configs_new_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_handler_configs
    ADD CONSTRAINT event_handler_configs_new_pkey PRIMARY KEY (id);


--
-- Name: extracted_link_sources extracted_link_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_link_sources
    ADD CONSTRAINT extracted_link_sources_pkey PRIMARY KEY (id);


--
-- Name: extracted_links extracted_links_new_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_links
    ADD CONSTRAINT extracted_links_new_pkey PRIMARY KEY (id);


--
-- Name: internal_service_tokens internal_service_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.internal_service_tokens
    ADD CONSTRAINT internal_service_tokens_pkey PRIMARY KEY (id);


--
-- Name: internal_service_tokens internal_service_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.internal_service_tokens
    ADD CONSTRAINT internal_service_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: ips ips_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ips
    ADD CONSTRAINT ips_pkey PRIMARY KEY (id);


--
-- Name: job_execution_history job_execution_history_execution_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_execution_history
    ADD CONSTRAINT job_execution_history_execution_id_key UNIQUE (execution_id);


--
-- Name: job_execution_history job_execution_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_execution_history
    ADD CONSTRAINT job_execution_history_pkey PRIMARY KEY (id);


--
-- Name: job_status job_status_job_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_status
    ADD CONSTRAINT job_status_job_id UNIQUE (job_id);


--
-- Name: job_status job_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_status
    ADD CONSTRAINT job_status_pkey PRIMARY KEY (id);


--
-- Name: nuclei_findings nuclei_findings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclei_findings
    ADD CONSTRAINT nuclei_findings_pkey PRIMARY KEY (id);


--
-- Name: nuclei_findings nuclei_findings_url_template_id_matcher_name_program_id_mat_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclei_findings
    ADD CONSTRAINT nuclei_findings_url_template_id_matcher_name_program_id_mat_key UNIQUE (url, template_id, matcher_name, program_id, matched_at);


--
-- Name: nuclei_templates nuclei_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclei_templates
    ADD CONSTRAINT nuclei_templates_pkey PRIMARY KEY (id);


--
-- Name: nuclei_templates nuclei_templates_template_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclei_templates
    ADD CONSTRAINT nuclei_templates_template_id UNIQUE (template_id);


--
-- Name: programs programs_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.programs
    ADD CONSTRAINT programs_name UNIQUE (name);


--
-- Name: programs programs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.programs
    ADD CONSTRAINT programs_pkey PRIMARY KEY (id);


--
-- Name: recon_task_parameters recon_task_parameters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recon_task_parameters
    ADD CONSTRAINT recon_task_parameters_pkey PRIMARY KEY (id);


--
-- Name: recon_task_parameters recon_task_parameters_recon_task; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recon_task_parameters
    ADD CONSTRAINT recon_task_parameters_recon_task UNIQUE (recon_task);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: scheduled_jobs scheduled_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_pkey PRIMARY KEY (id);


--
-- Name: scheduled_jobs scheduled_jobs_schedule_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_schedule_id_key UNIQUE (schedule_id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: screenshot_files screenshot_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screenshot_files
    ADD CONSTRAINT screenshot_files_pkey PRIMARY KEY (id);


--
-- Name: screenshots screenshots_file_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screenshots
    ADD CONSTRAINT screenshots_file_id_key UNIQUE (file_id);


--
-- Name: screenshots screenshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screenshots
    ADD CONSTRAINT screenshots_pkey PRIMARY KEY (id);


--
-- Name: services services_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_pkey PRIMARY KEY (id);


--
-- Name: social_media_credentials social_media_credentials_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.social_media_credentials
    ADD CONSTRAINT social_media_credentials_name_key UNIQUE (name);


--
-- Name: social_media_credentials social_media_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.social_media_credentials
    ADD CONSTRAINT social_media_credentials_pkey PRIMARY KEY (id);


--
-- Name: subdomain_ips subdomain_ips_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subdomain_ips
    ADD CONSTRAINT subdomain_ips_pkey PRIMARY KEY (id);


--
-- Name: subdomain_ips subdomain_ips_subdomain_id_ip_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subdomain_ips
    ADD CONSTRAINT subdomain_ips_subdomain_id_ip_id_key UNIQUE (subdomain_id, ip_id);


--
-- Name: subdomains subdomains_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subdomains
    ADD CONSTRAINT subdomains_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (key);


--
-- Name: technologies technologies_name_program_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.technologies
    ADD CONSTRAINT technologies_name_program_id_key UNIQUE (name, program_id);


--
-- Name: technologies technologies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.technologies
    ADD CONSTRAINT technologies_pkey PRIMARY KEY (id);


--
-- Name: typosquat_apex_domains typosquat_apex_domains_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_apex_domains
    ADD CONSTRAINT typosquat_apex_domains_pkey PRIMARY KEY (id);


--
-- Name: typosquat_certificates typosquat_certificates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_certificates
    ADD CONSTRAINT typosquat_certificates_pkey PRIMARY KEY (id);


--
-- Name: typosquat_certificates typosquat_certificates_serial_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_certificates
    ADD CONSTRAINT typosquat_certificates_serial_number UNIQUE (serial_number);


--
-- Name: typosquat_domains typosquat_domains_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_domains
    ADD CONSTRAINT typosquat_domains_pkey PRIMARY KEY (id);


--
-- Name: typosquat_domains typosquat_domains_typo_domain; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_domains
    ADD CONSTRAINT typosquat_domains_typo_domain UNIQUE (typo_domain);


--
-- Name: typosquat_screenshot_files typosquat_screenshot_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_screenshot_files
    ADD CONSTRAINT typosquat_screenshot_files_pkey PRIMARY KEY (id);


--
-- Name: typosquat_screenshots typosquat_screenshots_file_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_screenshots
    ADD CONSTRAINT typosquat_screenshots_file_id_key UNIQUE (file_id);


--
-- Name: typosquat_screenshots typosquat_screenshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_screenshots
    ADD CONSTRAINT typosquat_screenshots_pkey PRIMARY KEY (id);


--
-- Name: typosquat_urls typosquat_urls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_urls
    ADD CONSTRAINT typosquat_urls_pkey PRIMARY KEY (id);


--
-- Name: typosquat_urls typosquat_urls_url; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_urls
    ADD CONSTRAINT typosquat_urls_url UNIQUE (url);


--
-- Name: typosquat_apex_domains uq_typosquat_apex_program_domain; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_apex_domains
    ADD CONSTRAINT uq_typosquat_apex_program_domain UNIQUE (program_id, apex_domain);


--
-- Name: url_services url_services_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.url_services
    ADD CONSTRAINT url_services_pkey PRIMARY KEY (id);


--
-- Name: url_services url_services_url_id_service_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.url_services
    ADD CONSTRAINT url_services_url_id_service_id_key UNIQUE (url_id, service_id);


--
-- Name: url_technologies url_technologies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.url_technologies
    ADD CONSTRAINT url_technologies_pkey PRIMARY KEY (id);


--
-- Name: urls urls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.urls
    ADD CONSTRAINT urls_pkey PRIMARY KEY (id);


--
-- Name: user_program_permissions user_program_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_program_permissions
    ADD CONSTRAINT user_program_permissions_pkey PRIMARY KEY (id);


--
-- Name: user_program_permissions user_program_permissions_user_id_program_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_program_permissions
    ADD CONSTRAINT user_program_permissions_user_id_program_id_key UNIQUE (user_id, program_id);


--
-- Name: users users_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username UNIQUE (username);


--
-- Name: wordlist_files wordlist_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wordlist_files
    ADD CONSTRAINT wordlist_files_pkey PRIMARY KEY (id);


--
-- Name: wordlists wordlists_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wordlists
    ADD CONSTRAINT wordlists_name UNIQUE (name);


--
-- Name: wordlists wordlists_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wordlists
    ADD CONSTRAINT wordlists_pkey PRIMARY KEY (id);


--
-- Name: workflow_logs workflow_logs_execution_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_logs
    ADD CONSTRAINT workflow_logs_execution_id UNIQUE (execution_id);


--
-- Name: workflow_logs workflow_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_logs
    ADD CONSTRAINT workflow_logs_pkey PRIMARY KEY (id);


--
-- Name: workflows workflows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_pkey PRIMARY KEY (id);


--
-- Name: wpscan_findings wpscan_findings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wpscan_findings
    ADD CONSTRAINT wpscan_findings_pkey PRIMARY KEY (id);


--
-- Name: wpscan_findings wpscan_findings_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wpscan_findings
    ADD CONSTRAINT wpscan_findings_unique UNIQUE (url, item_name, program_id);


--
-- Name: apex_domains_name_program_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX apex_domains_name_program_id_unique ON public.apex_domains USING btree (name, program_id);


--
-- Name: certificates_serial_number_program_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX certificates_serial_number_program_id_unique ON public.certificates USING btree (serial_number, program_id);


--
-- Name: extracted_links_link_url_program_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX extracted_links_link_url_program_id_unique ON public.extracted_links USING btree (link_url, program_id);


--
-- Name: idx_action_logs_action_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_logs_action_type ON public.action_logs USING btree (action_type);


--
-- Name: idx_action_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_logs_created_at ON public.action_logs USING btree (created_at);


--
-- Name: idx_action_logs_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_logs_entity ON public.action_logs USING btree (entity_type, entity_id);


--
-- Name: idx_action_logs_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_logs_user ON public.action_logs USING btree (user_id);


--
-- Name: idx_aws_credentials_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_aws_credentials_active ON public.aws_credentials USING btree (is_active);


--
-- Name: idx_aws_credentials_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_aws_credentials_name ON public.aws_credentials USING btree (name);


--
-- Name: idx_broken_links_checked_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_broken_links_checked_at ON public.broken_links USING btree (checked_at);


--
-- Name: idx_broken_links_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_broken_links_domain ON public.broken_links USING btree (domain);


--
-- Name: idx_broken_links_link_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_broken_links_link_type ON public.broken_links USING btree (link_type);


--
-- Name: idx_broken_links_media_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_broken_links_media_type ON public.broken_links USING btree (media_type);


--
-- Name: idx_broken_links_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_broken_links_program_id ON public.broken_links USING btree (program_id);


--
-- Name: idx_broken_links_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_broken_links_status ON public.broken_links USING btree (status);


--
-- Name: idx_broken_links_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_broken_links_unique ON public.broken_links USING btree (program_id, url);


--
-- Name: idx_certificates_cipher; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_certificates_cipher ON public.certificates USING btree (cipher);


--
-- Name: idx_certificates_tls_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_certificates_tls_version ON public.certificates USING btree (tls_version);


--
-- Name: idx_ehc_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ehc_event_type ON public.event_handler_configs USING btree (event_type);


--
-- Name: idx_ehc_handler_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ehc_handler_id ON public.event_handler_configs USING btree (handler_id);


--
-- Name: idx_ehc_unique_global; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_ehc_unique_global ON public.event_handler_configs USING btree (handler_id) WHERE (program_id IS NULL);


--
-- Name: idx_ehc_unique_program; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_ehc_unique_program ON public.event_handler_configs USING btree (program_id, handler_id) WHERE (program_id IS NOT NULL);


--
-- Name: idx_event_handler_configs_program; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_event_handler_configs_program ON public.event_handler_configs USING btree (program_id);


--
-- Name: idx_extracted_link_sources_extracted_link_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_link_sources_extracted_link_id ON public.extracted_link_sources USING btree (extracted_link_id);


--
-- Name: idx_extracted_link_sources_source_url_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_link_sources_source_url_id ON public.extracted_link_sources USING btree (source_url_id);


--
-- Name: idx_extracted_link_sources_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_extracted_link_sources_unique ON public.extracted_link_sources USING btree (extracted_link_id, source_url_id);


--
-- Name: idx_extracted_links_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_links_created_at ON public.extracted_links USING btree (created_at);


--
-- Name: idx_extracted_links_link_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_links_link_url ON public.extracted_links USING btree (link_url);


--
-- Name: idx_extracted_links_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_links_program_id ON public.extracted_links USING btree (program_id);


--
-- Name: idx_internal_service_tokens_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_internal_service_tokens_active ON public.internal_service_tokens USING btree (is_active);


--
-- Name: idx_internal_service_tokens_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_internal_service_tokens_token_hash ON public.internal_service_tokens USING btree (token_hash);


--
-- Name: idx_programs_out_of_scope_regex; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_programs_out_of_scope_regex ON public.programs USING gin (out_of_scope_regex);


--
-- Name: idx_refresh_tokens_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_expires ON public.refresh_tokens USING btree (expires_at);


--
-- Name: idx_refresh_tokens_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_hash ON public.refresh_tokens USING btree (token_hash);


--
-- Name: idx_refresh_tokens_revoked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_revoked ON public.refresh_tokens USING btree (is_revoked);


--
-- Name: idx_refresh_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_user_id ON public.refresh_tokens USING btree (user_id);


--
-- Name: idx_social_media_credentials_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_social_media_credentials_active ON public.social_media_credentials USING btree (is_active);


--
-- Name: idx_social_media_credentials_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_social_media_credentials_name ON public.social_media_credentials USING btree (name);


--
-- Name: idx_social_media_credentials_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_social_media_credentials_platform ON public.social_media_credentials USING btree (platform);


--
-- Name: idx_social_media_credentials_platform_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_social_media_credentials_platform_active ON public.social_media_credentials USING btree (platform, is_active);


--
-- Name: idx_technologies_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_technologies_created_at ON public.technologies USING btree (created_at);


--
-- Name: idx_technologies_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_technologies_name ON public.technologies USING btree (name);


--
-- Name: idx_technologies_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_technologies_program_id ON public.technologies USING btree (program_id);


--
-- Name: idx_typosquat_apex_domains_apex_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_apex_domains_apex_domain ON public.typosquat_apex_domains USING btree (apex_domain);


--
-- Name: idx_typosquat_apex_domains_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_apex_domains_program_id ON public.typosquat_apex_domains USING btree (program_id);


--
-- Name: idx_typosquat_domains_action_taken; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_domains_action_taken ON public.typosquat_domains USING btree (action_taken);


--
-- Name: idx_typosquat_domains_apex_typosquat_domain_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_domains_apex_typosquat_domain_id ON public.typosquat_domains USING btree (apex_typosquat_domain_id);


--
-- Name: idx_typosquat_domains_is_parked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_domains_is_parked ON public.typosquat_domains USING btree (is_parked);


--
-- Name: idx_typosquat_domains_parked_confidence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_domains_parked_confidence ON public.typosquat_domains USING btree (parked_confidence);


--
-- Name: idx_typosquat_domains_phishlabs_data; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_domains_phishlabs_data ON public.typosquat_domains USING gin (phishlabs_data);


--
-- Name: idx_typosquat_domains_protected_similarities; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_domains_protected_similarities ON public.typosquat_domains USING gin (protected_domain_similarities);


--
-- Name: idx_typosquat_domains_threatstream_data; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_typosquat_domains_threatstream_data ON public.typosquat_domains USING gin (threatstream_data);


--
-- Name: idx_url_services_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_url_services_unique ON public.url_services USING btree (url_id, service_id);


--
-- Name: idx_url_technologies_technology_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_url_technologies_technology_id ON public.url_technologies USING btree (technology_id);


--
-- Name: idx_url_technologies_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_url_technologies_unique ON public.url_technologies USING btree (technology_id, url_id);


--
-- Name: idx_url_technologies_url_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_url_technologies_url_id ON public.url_technologies USING btree (url_id);


--
-- Name: idx_users_rf_uhash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_rf_uhash ON public.users USING btree (rf_uhash);


--
-- Name: idx_wordlists_dynamic_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wordlists_dynamic_type ON public.wordlists USING btree (dynamic_type) WHERE (dynamic_type IS NOT NULL);


--
-- Name: idx_wordlists_is_dynamic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wordlists_is_dynamic ON public.wordlists USING btree (is_dynamic);


--
-- Name: ips_ip_address_program_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ips_ip_address_program_id_unique ON public.ips USING btree (ip_address, program_id);


--
-- Name: ix_apex_domains_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_apex_domains_program_id ON public.apex_domains USING btree (program_id);


--
-- Name: ix_api_tokens_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_tokens_expires_at ON public.api_tokens USING btree (expires_at);


--
-- Name: ix_api_tokens_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_tokens_is_active ON public.api_tokens USING btree (is_active);


--
-- Name: ix_api_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_tokens_user_id ON public.api_tokens USING btree (user_id);


--
-- Name: ix_certificates_fingerprint_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_certificates_fingerprint_hash ON public.certificates USING btree (fingerprint_hash);


--
-- Name: ix_certificates_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_certificates_program_id ON public.certificates USING btree (program_id);


--
-- Name: ix_certificates_subject_cn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_certificates_subject_cn ON public.certificates USING btree (subject_cn);


--
-- Name: ix_certificates_valid_until; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_certificates_valid_until ON public.certificates USING btree (valid_until);


--
-- Name: ix_droopescan_findings_cms_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_droopescan_findings_cms_name ON public.droopescan_findings USING btree (cms_name);


--
-- Name: ix_droopescan_findings_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_droopescan_findings_created_at ON public.droopescan_findings USING btree (created_at);


--
-- Name: ix_droopescan_findings_hostname; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_droopescan_findings_hostname ON public.droopescan_findings USING btree (hostname);


--
-- Name: ix_droopescan_findings_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_droopescan_findings_program_id ON public.droopescan_findings USING btree (program_id);


--
-- Name: ix_droopescan_findings_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_droopescan_findings_status ON public.droopescan_findings USING btree (status);


--
-- Name: ix_droopescan_findings_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_droopescan_findings_url ON public.droopescan_findings USING btree (url);


--
-- Name: ix_ips_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ips_program_id ON public.ips USING btree (program_id);


--
-- Name: ix_ips_ptr_record; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ips_ptr_record ON public.ips USING btree (ptr_record);


--
-- Name: ix_job_execution_history_execution_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_execution_history_execution_id ON public.job_execution_history USING btree (execution_id);


--
-- Name: ix_job_execution_history_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_execution_history_job_id ON public.job_execution_history USING btree (job_id);


--
-- Name: ix_job_execution_history_schedule_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_execution_history_schedule_id ON public.job_execution_history USING btree (schedule_id);


--
-- Name: ix_job_execution_history_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_execution_history_started_at ON public.job_execution_history USING btree (started_at);


--
-- Name: ix_job_execution_history_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_execution_history_status ON public.job_execution_history USING btree (status);


--
-- Name: ix_job_status_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_status_created_at ON public.job_status USING btree (created_at);


--
-- Name: ix_job_status_job_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_status_job_type ON public.job_status USING btree (job_type);


--
-- Name: ix_job_status_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_status_status ON public.job_status USING btree (status);


--
-- Name: ix_job_status_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_status_updated_at ON public.job_status USING btree (updated_at);


--
-- Name: ix_job_status_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_status_user_id ON public.job_status USING btree (user_id);


--
-- Name: ix_nuclei_findings_hostname; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_findings_hostname ON public.nuclei_findings USING btree (hostname);


--
-- Name: ix_nuclei_findings_ip_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_findings_ip_id ON public.nuclei_findings USING btree (ip_id);


--
-- Name: ix_nuclei_findings_matched_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_findings_matched_at ON public.nuclei_findings USING btree (matched_at);


--
-- Name: ix_nuclei_findings_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_findings_program_id ON public.nuclei_findings USING btree (program_id);


--
-- Name: ix_nuclei_findings_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_findings_severity ON public.nuclei_findings USING btree (severity);


--
-- Name: ix_nuclei_findings_template_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_findings_template_id ON public.nuclei_findings USING btree (template_id);


--
-- Name: ix_nuclei_findings_template_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_findings_template_path ON public.nuclei_findings USING btree (template_path);


--
-- Name: ix_nuclei_findings_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_findings_url ON public.nuclei_findings USING btree (url);


--
-- Name: ix_nuclei_templates_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_templates_is_active ON public.nuclei_templates USING btree (is_active);


--
-- Name: ix_nuclei_templates_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_templates_severity ON public.nuclei_templates USING btree (severity);


--
-- Name: ix_nuclei_templates_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nuclei_templates_tags ON public.nuclei_templates USING btree (tags);


--
-- Name: ix_programs_protected_domains; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_programs_protected_domains ON public.programs USING gin (protected_domains);


--
-- Name: ix_programs_protected_subdomain_prefixes; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_programs_protected_subdomain_prefixes ON public.programs USING gin (protected_subdomain_prefixes);


--
-- Name: ix_programs_threatstream_api_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_programs_threatstream_api_user ON public.programs USING btree (threatstream_api_user);


--
-- Name: ix_scheduled_jobs_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_enabled ON public.scheduled_jobs USING btree (enabled);


--
-- Name: ix_scheduled_jobs_job_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_job_type ON public.scheduled_jobs USING btree (job_type);


--
-- Name: ix_scheduled_jobs_next_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_next_run ON public.scheduled_jobs USING btree (next_run);


--
-- Name: ix_scheduled_jobs_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_program_id ON public.scheduled_jobs USING btree (program_id);


--
-- Name: ix_scheduled_jobs_program_id_fkey; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_program_id_fkey ON public.scheduled_jobs USING btree (program_id);


--
-- Name: ix_scheduled_jobs_schedule_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_schedule_id ON public.scheduled_jobs USING btree (schedule_id);


--
-- Name: ix_scheduled_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_status ON public.scheduled_jobs USING btree (status);


--
-- Name: ix_scheduled_jobs_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_tags ON public.scheduled_jobs USING gin (tags);


--
-- Name: ix_scheduled_jobs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_jobs_user_id ON public.scheduled_jobs USING btree (user_id);


--
-- Name: ix_screenshot_files_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_screenshot_files_created_at ON public.screenshot_files USING btree (created_at);


--
-- Name: ix_screenshots_capture_count; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_screenshots_capture_count ON public.screenshots USING btree (capture_count);


--
-- Name: ix_screenshots_image_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_screenshots_image_hash ON public.screenshots USING btree (image_hash);


--
-- Name: ix_screenshots_last_captured_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_screenshots_last_captured_at ON public.screenshots USING btree (last_captured_at);


--
-- Name: ix_screenshots_program_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_screenshots_program_name ON public.screenshots USING btree (program_name);


--
-- Name: ix_screenshots_step_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_screenshots_step_name ON public.screenshots USING btree (step_name);


--
-- Name: ix_screenshots_url_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_screenshots_url_id ON public.screenshots USING btree (url_id);


--
-- Name: ix_screenshots_workflow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_screenshots_workflow_id ON public.screenshots USING btree (workflow_id);


--
-- Name: ix_services_ip_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_services_ip_id ON public.services USING btree (ip_id);


--
-- Name: ix_services_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_services_program_id ON public.services USING btree (program_id);


--
-- Name: ix_subdomains_apex_domain_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_subdomains_apex_domain_id ON public.subdomains USING btree (apex_domain_id);


--
-- Name: ix_subdomains_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_subdomains_program_id ON public.subdomains USING btree (program_id);


--
-- Name: ix_typosquat_apex_domains_apex_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_apex_domains_apex_domain ON public.typosquat_apex_domains USING btree (apex_domain);


--
-- Name: ix_typosquat_apex_domains_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_apex_domains_program_id ON public.typosquat_apex_domains USING btree (program_id);


--
-- Name: ix_typosquat_certificates_fingerprint_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_certificates_fingerprint_hash ON public.typosquat_certificates USING btree (fingerprint_hash);


--
-- Name: ix_typosquat_certificates_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_certificates_program_id ON public.typosquat_certificates USING btree (program_id);


--
-- Name: ix_typosquat_certificates_subject_cn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_certificates_subject_cn ON public.typosquat_certificates USING btree (subject_cn);


--
-- Name: ix_typosquat_certificates_valid_until; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_certificates_valid_until ON public.typosquat_certificates USING btree (valid_until);


--
-- Name: ix_typosquat_domains_detected_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_domains_detected_at ON public.typosquat_domains USING btree (detected_at);


--
-- Name: ix_typosquat_domains_domain_registered; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_domains_domain_registered ON public.typosquat_domains USING btree (domain_registered);


--
-- Name: ix_typosquat_domains_fixed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_domains_fixed_at ON public.typosquat_domains USING btree (fixed_at);


--
-- Name: ix_typosquat_domains_geoip_country; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_domains_geoip_country ON public.typosquat_domains USING btree (geoip_country);


--
-- Name: ix_typosquat_domains_is_wildcard; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_domains_is_wildcard ON public.typosquat_domains USING btree (is_wildcard);


--
-- Name: ix_typosquat_domains_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_domains_program_id ON public.typosquat_domains USING btree (program_id);


--
-- Name: ix_typosquat_domains_risk_analysis_risk_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_domains_risk_analysis_risk_level ON public.typosquat_domains USING btree (risk_analysis_risk_level);


--
-- Name: ix_typosquat_domains_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_domains_status ON public.typosquat_domains USING btree (status);


--
-- Name: ix_typosquat_screenshot_files_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshot_files_created_at ON public.typosquat_screenshot_files USING btree (created_at);


--
-- Name: ix_typosquat_screenshots_capture_count; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_capture_count ON public.typosquat_screenshots USING btree (capture_count);


--
-- Name: ix_typosquat_screenshots_image_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_image_hash ON public.typosquat_screenshots USING btree (image_hash);


--
-- Name: ix_typosquat_screenshots_last_captured_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_last_captured_at ON public.typosquat_screenshots USING btree (last_captured_at);


--
-- Name: ix_typosquat_screenshots_program_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_program_name ON public.typosquat_screenshots USING btree (program_name);


--
-- Name: ix_typosquat_screenshots_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_source ON public.typosquat_screenshots USING btree (source);


--
-- Name: ix_typosquat_screenshots_source_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_source_created_at ON public.typosquat_screenshots USING btree (source_created_at);


--
-- Name: ix_typosquat_screenshots_step_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_step_name ON public.typosquat_screenshots USING btree (step_name);


--
-- Name: ix_typosquat_screenshots_url_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_url_id ON public.typosquat_screenshots USING btree (url_id);


--
-- Name: ix_typosquat_screenshots_workflow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_screenshots_workflow_id ON public.typosquat_screenshots USING btree (workflow_id);


--
-- Name: ix_typosquat_urls_hostname; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_urls_hostname ON public.typosquat_urls USING btree (hostname);


--
-- Name: ix_typosquat_urls_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_urls_program_id ON public.typosquat_urls USING btree (program_id);


--
-- Name: ix_typosquat_urls_response_body_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_urls_response_body_hash ON public.typosquat_urls USING btree (response_body_hash);


--
-- Name: ix_typosquat_urls_typosquat_certificate_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_urls_typosquat_certificate_id ON public.typosquat_urls USING btree (typosquat_certificate_id);


--
-- Name: ix_typosquat_urls_typosquat_domain_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_typosquat_urls_typosquat_domain_id ON public.typosquat_urls USING btree (typosquat_domain_id);


--
-- Name: ix_url_services_service_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_url_services_service_id ON public.url_services USING btree (service_id);


--
-- Name: ix_url_services_url_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_url_services_url_id ON public.url_services USING btree (url_id);


--
-- Name: ix_urls_certificate_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_urls_certificate_id ON public.urls USING btree (certificate_id);


--
-- Name: ix_urls_hostname; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_urls_hostname ON public.urls USING btree (hostname);


--
-- Name: ix_urls_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_urls_program_id ON public.urls USING btree (program_id);


--
-- Name: ix_urls_response_body_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_urls_response_body_hash ON public.urls USING btree (response_body_hash);


--
-- Name: ix_urls_subdomain_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_urls_subdomain_id ON public.urls USING btree (subdomain_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_is_active ON public.users USING btree (is_active);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: ix_wordlists_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wordlists_is_active ON public.wordlists USING btree (is_active);


--
-- Name: ix_wordlists_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wordlists_program_id ON public.wordlists USING btree (program_id);


--
-- Name: ix_workflow_logs_completed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_logs_completed_at ON public.workflow_logs USING btree (completed_at);


--
-- Name: ix_workflow_logs_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_logs_program_id ON public.workflow_logs USING btree (program_id);


--
-- Name: ix_workflow_logs_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_logs_started_at ON public.workflow_logs USING btree (started_at);


--
-- Name: ix_workflow_logs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_logs_status ON public.workflow_logs USING btree (status);


--
-- Name: ix_workflows_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflows_program_id ON public.workflows USING btree (program_id);


--
-- Name: ix_wpscan_findings_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wpscan_findings_created_at ON public.wpscan_findings USING btree (created_at);


--
-- Name: ix_wpscan_findings_hostname; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wpscan_findings_hostname ON public.wpscan_findings USING btree (hostname);


--
-- Name: ix_wpscan_findings_item_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wpscan_findings_item_name ON public.wpscan_findings USING btree (item_name);


--
-- Name: ix_wpscan_findings_item_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wpscan_findings_item_type ON public.wpscan_findings USING btree (item_type);


--
-- Name: ix_wpscan_findings_program_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wpscan_findings_program_id ON public.wpscan_findings USING btree (program_id);


--
-- Name: ix_wpscan_findings_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wpscan_findings_severity ON public.wpscan_findings USING btree (severity);


--
-- Name: ix_wpscan_findings_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wpscan_findings_status ON public.wpscan_findings USING btree (status);


--
-- Name: ix_wpscan_findings_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wpscan_findings_url ON public.wpscan_findings USING btree (url);


--
-- Name: services_ip_id_port_program_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX services_ip_id_port_program_id_unique ON public.services USING btree (ip_id, port, program_id);


--
-- Name: subdomains_name_program_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX subdomains_name_program_id_unique ON public.subdomains USING btree (name, program_id);


--
-- Name: urls_url_program_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX urls_url_program_id_unique ON public.urls USING btree (url, program_id);


--
-- Name: workflows_name_program_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX workflows_name_program_id_unique ON public.workflows USING btree (name, COALESCE(program_id, '00000000-0000-0000-0000-000000000000'::uuid));


--
-- Name: aws_credentials update_aws_credentials_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_aws_credentials_updated_at BEFORE UPDATE ON public.aws_credentials FOR EACH ROW EXECUTE FUNCTION public.update_aws_credentials_updated_at();


--
-- Name: broken_links update_broken_links_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_broken_links_updated_at BEFORE UPDATE ON public.broken_links FOR EACH ROW EXECUTE FUNCTION public.update_broken_links_updated_at();


--
-- Name: internal_service_tokens update_internal_service_tokens_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_internal_service_tokens_updated_at BEFORE UPDATE ON public.internal_service_tokens FOR EACH ROW EXECUTE FUNCTION public.update_internal_service_tokens_updated_at();


--
-- Name: scheduled_jobs update_scheduled_jobs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_scheduled_jobs_updated_at BEFORE UPDATE ON public.scheduled_jobs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: social_media_credentials update_social_media_credentials_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_social_media_credentials_updated_at BEFORE UPDATE ON public.social_media_credentials FOR EACH ROW EXECUTE FUNCTION public.update_social_media_credentials_updated_at();


--
-- Name: action_logs action_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: apex_domains apex_domains_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apex_domains
    ADD CONSTRAINT apex_domains_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: api_tokens api_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_tokens
    ADD CONSTRAINT api_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: broken_links broken_links_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broken_links
    ADD CONSTRAINT broken_links_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id) ON DELETE CASCADE;


--
-- Name: certificates certificates_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: droopescan_findings droopescan_findings_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.droopescan_findings
    ADD CONSTRAINT droopescan_findings_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: event_handler_configs event_handler_configs_new_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_handler_configs
    ADD CONSTRAINT event_handler_configs_new_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id) ON DELETE CASCADE;


--
-- Name: extracted_link_sources extracted_link_sources_extracted_link_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_link_sources
    ADD CONSTRAINT extracted_link_sources_extracted_link_id_fkey FOREIGN KEY (extracted_link_id) REFERENCES public.extracted_links(id) ON DELETE CASCADE;


--
-- Name: extracted_link_sources extracted_link_sources_source_url_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_link_sources
    ADD CONSTRAINT extracted_link_sources_source_url_id_fkey FOREIGN KEY (source_url_id) REFERENCES public.urls(id) ON DELETE CASCADE;


--
-- Name: extracted_links extracted_links_new_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_links
    ADD CONSTRAINT extracted_links_new_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id) ON DELETE CASCADE;


--
-- Name: ips ips_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ips
    ADD CONSTRAINT ips_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: job_status job_status_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_status
    ADD CONSTRAINT job_status_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: nuclei_findings nuclei_findings_ip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclei_findings
    ADD CONSTRAINT nuclei_findings_ip_id_fkey FOREIGN KEY (ip_id) REFERENCES public.ips(id);


--
-- Name: nuclei_findings nuclei_findings_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclei_findings
    ADD CONSTRAINT nuclei_findings_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: scheduled_jobs scheduled_jobs_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: scheduled_jobs scheduled_jobs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: screenshots screenshots_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screenshots
    ADD CONSTRAINT screenshots_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.screenshot_files(id);


--
-- Name: screenshots screenshots_url_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screenshots
    ADD CONSTRAINT screenshots_url_id_fkey FOREIGN KEY (url_id) REFERENCES public.urls(id);


--
-- Name: services services_ip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_ip_id_fkey FOREIGN KEY (ip_id) REFERENCES public.ips(id);


--
-- Name: services services_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: subdomain_ips subdomain_ips_ip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subdomain_ips
    ADD CONSTRAINT subdomain_ips_ip_id_fkey FOREIGN KEY (ip_id) REFERENCES public.ips(id);


--
-- Name: subdomain_ips subdomain_ips_subdomain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subdomain_ips
    ADD CONSTRAINT subdomain_ips_subdomain_id_fkey FOREIGN KEY (subdomain_id) REFERENCES public.subdomains(id);


--
-- Name: subdomains subdomains_apex_domain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subdomains
    ADD CONSTRAINT subdomains_apex_domain_id_fkey FOREIGN KEY (apex_domain_id) REFERENCES public.apex_domains(id);


--
-- Name: subdomains subdomains_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subdomains
    ADD CONSTRAINT subdomains_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: technologies technologies_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.technologies
    ADD CONSTRAINT technologies_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id) ON DELETE CASCADE;


--
-- Name: typosquat_apex_domains typosquat_apex_domains_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_apex_domains
    ADD CONSTRAINT typosquat_apex_domains_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: typosquat_certificates typosquat_certificates_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_certificates
    ADD CONSTRAINT typosquat_certificates_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: typosquat_domains typosquat_domains_apex_typosquat_domain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_domains
    ADD CONSTRAINT typosquat_domains_apex_typosquat_domain_id_fkey FOREIGN KEY (apex_typosquat_domain_id) REFERENCES public.typosquat_apex_domains(id) ON DELETE RESTRICT;


--
-- Name: typosquat_domains typosquat_domains_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_domains
    ADD CONSTRAINT typosquat_domains_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: typosquat_screenshots typosquat_screenshots_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_screenshots
    ADD CONSTRAINT typosquat_screenshots_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.typosquat_screenshot_files(id) ON DELETE CASCADE;


--
-- Name: typosquat_screenshots typosquat_screenshots_url_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_screenshots
    ADD CONSTRAINT typosquat_screenshots_url_id_fkey FOREIGN KEY (url_id) REFERENCES public.typosquat_urls(id) ON DELETE CASCADE;


--
-- Name: typosquat_urls typosquat_urls_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_urls
    ADD CONSTRAINT typosquat_urls_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: typosquat_urls typosquat_urls_typosquat_certificate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_urls
    ADD CONSTRAINT typosquat_urls_typosquat_certificate_id_fkey FOREIGN KEY (typosquat_certificate_id) REFERENCES public.typosquat_certificates(id) ON DELETE CASCADE;


--
-- Name: typosquat_urls typosquat_urls_typosquat_domain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.typosquat_urls
    ADD CONSTRAINT typosquat_urls_typosquat_domain_id_fkey FOREIGN KEY (typosquat_domain_id) REFERENCES public.typosquat_domains(id) ON DELETE CASCADE;


--
-- Name: url_services url_services_service_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.url_services
    ADD CONSTRAINT url_services_service_id_fkey FOREIGN KEY (service_id) REFERENCES public.services(id) ON DELETE CASCADE;


--
-- Name: url_services url_services_url_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.url_services
    ADD CONSTRAINT url_services_url_id_fkey FOREIGN KEY (url_id) REFERENCES public.urls(id) ON DELETE CASCADE;


--
-- Name: url_technologies url_technologies_technology_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.url_technologies
    ADD CONSTRAINT url_technologies_technology_id_fkey FOREIGN KEY (technology_id) REFERENCES public.technologies(id) ON DELETE CASCADE;


--
-- Name: url_technologies url_technologies_url_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.url_technologies
    ADD CONSTRAINT url_technologies_url_id_fkey FOREIGN KEY (url_id) REFERENCES public.urls(id) ON DELETE CASCADE;


--
-- Name: urls urls_certificate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.urls
    ADD CONSTRAINT urls_certificate_id_fkey FOREIGN KEY (certificate_id) REFERENCES public.certificates(id);


--
-- Name: urls urls_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.urls
    ADD CONSTRAINT urls_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: urls urls_subdomain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.urls
    ADD CONSTRAINT urls_subdomain_id_fkey FOREIGN KEY (subdomain_id) REFERENCES public.subdomains(id) ON DELETE SET NULL;


--
-- Name: user_program_permissions user_program_permissions_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_program_permissions
    ADD CONSTRAINT user_program_permissions_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: user_program_permissions user_program_permissions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_program_permissions
    ADD CONSTRAINT user_program_permissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: wordlists wordlists_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wordlists
    ADD CONSTRAINT wordlists_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.wordlist_files(id);


--
-- Name: wordlists wordlists_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wordlists
    ADD CONSTRAINT wordlists_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: workflow_logs workflow_logs_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_logs
    ADD CONSTRAINT workflow_logs_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: wpscan_findings wpscan_findings_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wpscan_findings
    ADD CONSTRAINT wpscan_findings_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- PostgreSQL database dump complete
--

