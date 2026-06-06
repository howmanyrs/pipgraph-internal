import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from config.settings import settings

# Настройка логирования для backend (до импорта модулей)
log_level = settings.LOG_LEVEL.upper()
logging.basicConfig(
    level=logging.INFO,  # Базовый уровень для всех
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# # DEBUG только для модулей приложения
# if log_level == "DEBUG":
logging.getLogger("app.services").setLevel(logging.DEBUG)
logging.getLogger("app.crud").setLevel(logging.DEBUG)

# Заглушить шумные библиотеки
logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

print(f"🔧 Logging level set to: {log_level}")
from app.api.endpoints import dev

logger = logging.getLogger(__name__)


async def _verify_neo4j() -> None:
    logger.info(f"Verifying Neo4j connectivity at {settings.NEO4J_URI} ...")
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        await driver.verify_connectivity()
        await driver.verify_authentication()
    except ServiceUnavailable as e:
        logger.error(f"Neo4j unreachable at {settings.NEO4J_URI}: {e}")
        raise RuntimeError(
            f"Neo4j is unreachable at {settings.NEO4J_URI}. "
            "Check that the database is running and NEO4J_URI is correct."
        ) from e
    except AuthError as e:
        logger.error(f"Neo4j authentication failed for user '{settings.NEO4J_USER}': {e}")
        raise RuntimeError(
            f"Neo4j authentication failed for user '{settings.NEO4J_USER}'. "
            "Check NEO4J_USER and NEO4J_PASSWORD."
        ) from e
    finally:
        await driver.close()
    logger.info("Neo4j connectivity OK")


async def _verify_llm() -> None:
    # Лёгкая проверка активного LLM-провайдера через OpenAI-совместимый GET /models.
    # Использует те же base_url и api_key, что и PatchedLLMClient в setup_graphiti.py
    # (через resolve_active_config), но не инстанцирует Graphiti (избегаем
    # build_indices и расхода токенов).
    from app.services.graphiti.llm_config import resolve_active_config

    active = resolve_active_config()
    base_url = active.base_url.rstrip("/")
    url = f"{base_url}/models"
    logger.info(f"Verifying LLM service availability ({active.provider}) at {base_url} ...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {active.api_key}"},
            )
    except httpx.HTTPError as e:
        logger.error(f"LLM service unreachable at {base_url}: {e}")
        raise RuntimeError(
            f"LLM service unreachable at {base_url}. "
            "Check network and the active provider's base_url."
        ) from e

    if resp.status_code == 401 or resp.status_code == 403:
        logger.error(f"LLM authentication failed ({resp.status_code}): {resp.text[:200]}")
        raise RuntimeError(
            f"LLM authentication failed at {base_url} (HTTP {resp.status_code}). "
            "Check the active provider's API key."
        )
    if resp.status_code >= 500:
        logger.error(f"LLM service error ({resp.status_code}): {resp.text[:200]}")
        raise RuntimeError(
            f"LLM service returned HTTP {resp.status_code} at {base_url}."
        )
    if resp.status_code >= 400:
        # 404 на /models у некоторых провайдеров считаем не фатальным — соединение и ключ работают
        logger.warning(
            f"LLM /models returned HTTP {resp.status_code}; "
            "treating as reachable (endpoint may not expose model listing)."
        )
    logger.info("LLM service connectivity OK")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _verify_neo4j()
    await _verify_llm()
    # Start the in-process job-runner (background-worker for slow LLM work, e.g.
    # async episode naming). In-memory + single worker by design — see
    # app/services/jobs/queue.py.
    from app.services.jobs import requeue_in_flight, start_worker, stop_worker
    start_worker()
    logger.info("Job-runner worker started")
    # Re-queue heavy jobs left in flight by a previous (crashed/restarted) run.
    # In-memory queue loses what was queued; the node's status is the only
    # durable trace. Best-effort — never blocks startup. See queue.requeue_in_flight.
    await requeue_in_flight()
    try:
        yield
    finally:
        await stop_worker()
        logger.info("Job-runner worker stopped")


app = FastAPI(title="PipGraph Backend", lifespan=lifespan)

# CORS настройки для разработки
# Разрешаем запросы с frontend (localhost:3000) и других источников
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:3001",  # Alternative port
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Разрешить все методы (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Разрешить все заголовки
)

# REST API роутеры
app.include_router(dev.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"status": "PipGraph Backend is running"}