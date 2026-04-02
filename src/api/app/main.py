from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from routes import assets, programs, findings, workflows, auth, nuclei_templates, jobs, admin, admin_database, admin_database_maintenance, wordlists, scheduled_jobs, subdomain_assets, ip_assets, url_assets, service_assets, apexdomain_assets, certificate_assets, screenshot_assets, typosquat_findings, nuclei_findings, wpscan_findings, common_assets, common_findings, action_logs, broken_links, social_media_credentials, ai, event_handler_configs, ct_monitor_internal, internal_database_restore
from middleware.auth import AuthMiddleware
from middleware.maintenance import MaintenanceMiddleware
from config.settings import settings
import asyncio
import logging
import os

if os.getenv("LOG_LEVEL"):
    logging.basicConfig(level=os.getenv("LOG_LEVEL"))
else:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Recon API",
    description="API for Recon",
    version=os.getenv("APP_VERSION", "dev"),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error on {request.url.path} from {request.client.host}: {exc.errors()}")
    if request.url.path.startswith("/auth/login"):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid username or password"}
        )
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request"}
    )

# Include data-api routes (no prefix to maintain backward compatibility)
app.include_router(auth.router, prefix="/auth")
app.include_router(assets.router, prefix="/assets")
app.include_router(subdomain_assets.router, prefix="/assets")
app.include_router(ip_assets.router, prefix="/assets")
app.include_router(url_assets.router, prefix="/assets")
app.include_router(service_assets.router, prefix="/assets")
app.include_router(apexdomain_assets.router, prefix="/assets")
app.include_router(certificate_assets.router, prefix="/assets")
app.include_router(screenshot_assets.router, prefix="/assets")
app.include_router(common_assets.router, prefix="/assets")
app.include_router(programs.router, prefix="/programs")
app.include_router(findings.router, prefix="/findings")
app.include_router(typosquat_findings.router, prefix="/findings")
app.include_router(nuclei_findings.router, prefix="/findings")
app.include_router(wpscan_findings.router, prefix="/findings")
app.include_router(broken_links.router, prefix="/findings")
app.include_router(common_findings.router, prefix="/findings")
app.include_router(nuclei_templates.router, prefix="/nuclei-templates")
app.include_router(social_media_credentials.router, prefix="")
app.include_router(wordlists.router, prefix="/wordlists")
app.include_router(jobs.router, prefix="/jobs")
app.include_router(scheduled_jobs.router, prefix="/scheduled-jobs")
app.include_router(admin.router, prefix="/admin")
app.include_router(admin_database.router, prefix="/admin")
app.include_router(admin_database_maintenance.router, prefix="/admin")
app.include_router(event_handler_configs.admin_router, prefix="/admin")
app.include_router(event_handler_configs.internal_router, prefix="/internal")
app.include_router(internal_database_restore.internal_router, prefix="/internal")
app.include_router(ct_monitor_internal.internal_ct_monitor_router, prefix="/internal")
app.include_router(workflows.router, prefix="/workflows")
app.include_router(action_logs.router, prefix="/action-logs")
app.include_router(ai.router, prefix="/ai")

# Configure CORS
# Add authentication middleware (enabled by default - disable for local tests via DISABLE_AUTH_MIDDLEWARE=true)
if os.getenv("DISABLE_AUTH_MIDDLEWARE", "false").lower() != "true":
    app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://dev.h3x.recon",
        "http://prod.h3x.recon",
        "http://local.h3x.recon",
        "http://dev.h3x.recon:8080",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Outermost: maintenance gate before auth/CORS inner layers
app.add_middleware(MaintenanceMiddleware)

@app.on_event("startup")
async def startup_event():
    """Initialize database and nuclei templates repository on startup"""
    try:
        from auth.utils import validate_secret_keys
        validate_secret_keys()

        # Initialize database tables and default data
        logger.info("Starting database initialization...")
        initialize_database()
        logger.info("Database initialization completed")
        
        # Ensure internal_service_tokens table exists
        try:
            from services.internal_token_service import InternalTokenService
            token_service = InternalTokenService()
            await token_service.ensure_table_exists()
            logger.info("Internal service tokens table ensured")
        except Exception as e:
            logger.error(f"Error ensuring internal service tokens table: {e}")
            # Don't raise this error as it's not critical for basic functionality
        
        # Initialize internal service token (retry while Postgres / K8s API may be warming up)
        logger.info("Starting internal service token initialization...")
        max_attempts = int(os.getenv("INTERNAL_SERVICE_TOKEN_INIT_ATTEMPTS", "5"))
        delay_sec = float(os.getenv("INTERNAL_SERVICE_TOKEN_INIT_DELAY_SEC", "2"))
        for attempt in range(1, max_attempts + 1):
            await initialize_internal_service_token()
            if os.getenv("INTERNAL_SERVICE_API_KEY"):
                logger.info("Internal service token initialization completed")
                break
            if attempt < max_attempts:
                logger.warning(
                    "INTERNAL_SERVICE_API_KEY unset after token init (attempt %s/%s); retrying in %ss",
                    attempt,
                    max_attempts,
                    delay_sec,
                )
                await asyncio.sleep(delay_sec)
        else:
            logger.error(
                "INTERNAL_SERVICE_API_KEY still unset after %s attempts; "
                "API internal auth may fail until the key is available (runner jobs use the cluster Secret)",
                max_attempts,
            )
        
        # Initialize asset processor
        try:
            logger.debug("Asset processor initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing asset processor: {e}")
            # Don't raise this error as it's not critical for basic functionality
        
        # Verify the environment variable is set
        final_token = os.getenv("INTERNAL_SERVICE_API_KEY")
        if final_token:
            logger.debug(f"✅ Internal service token environment variable set: {final_token[:20]}...")
        else:
            logger.error("❌ Internal service token environment variable NOT set!")
            logger.error("Internal service authentication will not work!")
        logger.debug(f"REFRESH_TOKEN_EXPIRE_DAYS: {os.getenv('REFRESH_TOKEN_EXPIRE_DAYS')}")
        logger.debug(f"ACCESS_TOKEN_EXPIRE_MINUTES: {os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES')}")
        logger.info("API startup completed successfully")
        
    except Exception as e:
        logger.error(f"Error during API startup: {e}")
        logger.error("API may not function properly due to startup errors")
        # Don't raise the error as it would prevent the API from starting

def initialize_database():
    """Initialize database tables and default parameters"""
    try:
        from db import init_database, test_connection
        logger.debug("Testing database connection...")
        
        # Test connection first
        if test_connection():
            logger.debug("Database connection test successful")
        else:
            logger.error("Database connection test failed")
            raise Exception("Database connection test failed")
        
        logger.debug("Initializing database tables and default parameters...")
        init_database()
        logger.debug("Database initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

async def initialize_internal_service_token():
    """Initialize or retrieve the internal service token on startup and upsert K8s Secret"""
    import os
    import time
    from services.internal_token_service import InternalTokenService

    def _export_env_token(token: str):
        os.environ["INTERNAL_SERVICE_API_KEY"] = token
        logger.debug("Exported INTERNAL_SERVICE_API_KEY to process env")

    try:
        # 1) Prefer env if set and valid
        existing_token = os.getenv("INTERNAL_SERVICE_API_KEY")
        if existing_token:
            token_service = InternalTokenService()
            await token_service.ensure_table_exists()  # Ensure table exists for validation
            token_data = await token_service.validate_token(existing_token)
            if token_data:
                logger.info(f"INTERNAL_SERVICE_API_KEY from env is valid (token: {token_data['name']})")
                return
            else:
                logger.warning("INTERNAL_SERVICE_API_KEY present but invalid; continuing")

        # 2) Try reading from Kubernetes Secret
        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            v1 = client.CoreV1Api()
            namespace = os.getenv("KUBERNETES_NAMESPACE", "recon")
            secret_name = os.getenv("INTERNAL_SERVICE_SECRET_NAME", "internal-service-secret")
            secret = v1.read_namespaced_secret(secret_name, namespace)
            if getattr(secret, 'data', None) and secret.data.get("token"):
                import base64
                token_from_secret = base64.b64decode(secret.data["token"]).decode("utf-8")
                token_service = InternalTokenService()
                await token_service.ensure_table_exists()
                token_data = await token_service.validate_token(token_from_secret)
                if token_data:
                    _export_env_token(token_from_secret)
                    logger.info("Loaded INTERNAL_SERVICE_API_KEY from Kubernetes Secret")
                    return
                else:
                    logger.warning("Token found in Secret but invalid; will create a new one")
        except Exception as e:
            logger.info(f"Kubernetes Secret read skipped/failed: {e}")

        # 3) Create/ensure default token exists
        token_service = InternalTokenService()
        await token_service.ensure_table_exists()
        token = await token_service.get_or_create_default_token()

        if token == "existing-token-needs-rotation":
            # Default exists but plaintext unknown; rotate a new default token
            logger.info("Default internal token exists; creating a new default for distribution")
            token = await token_service.create_internal_token(
                name=f"{token_service.DEFAULT_TOKEN_NAME}-{int(time.time())}",
                description="Default internal token for API-to-service communication (rotated)"
            )

        # 4) Upsert Kubernetes Secret with plaintext for other services
        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            v1 = client.CoreV1Api()
            namespace = os.getenv("KUBERNETES_NAMESPACE", "recon")
            secret_name = os.getenv("INTERNAL_SERVICE_SECRET_NAME", "internal-service-secret")
            import base64
            secret_body = client.V1Secret(
                metadata=client.V1ObjectMeta(name=secret_name),
                type="Opaque",
                data={"token": base64.b64encode(token.encode("utf-8")).decode("utf-8")},
            )
            try:
                v1.create_namespaced_secret(namespace, secret_body)
            except client.exceptions.ApiException as e:
                if e.status == 409:
                    v1.patch_namespaced_secret(secret_name, namespace, secret_body)
                else:
                    raise
            _export_env_token(token)
        except Exception as e:
            logger.warning(f"Failed to upsert internal token Secret: {e}")
            _export_env_token(token)

    except Exception as e:
        logger.error(f"Failed to initialize internal service token: {e}")
        logger.warning("Internal service authentication may not work properly")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    try:
        # Shutdown the thread pool used for background Kubernetes operations
        if hasattr(workflows, 'thread_pool'):
            logger.info("Shutting down workflow thread pool...")
            workflows.thread_pool.shutdown(wait=True)
            logger.info("Workflow thread pool shut down successfully")
        
        # Shutdown unified asset processor
        try:
            from services.unified_asset_processor import unified_asset_processor
            await unified_asset_processor.shutdown()
            logger.info("Unified asset processor shut down successfully")
        except Exception as e:
            logger.error(f"Error shutting down unified asset processor: {e}")
            
    except Exception as e:
        logger.error(f"Error during shutdown cleanup: {str(e)}")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "healthy", "service": "unified-api"}

@app.get("/status")
async def status():
    """Service status endpoint"""
    return {
        "status": "operational",
        "service": "unified-api",
        "version": os.getenv("APP_VERSION", "dev"),
        "features": ["data-management", "workflow-execution"]
    } 