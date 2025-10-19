"""
Checknote service v2 using file_path-based duplicate detection.

Архитектура:
- SQLite хранит маппинг (file_path, group_id) → (episode_uuid, content_hash)
- Проверка происходит ДО вызова LLM
- Поддерживает три сценария: NEW, DUPLICATE, UPDATED

Ключевые отличия от v01:
- Заметка идентифицируется по file_path, а не по content_hash
- Это позволяет различать повторную обработку (duplicate) от обновления (updated)
"""

import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel


class ChecknoteResult(BaseModel):
    """Результат проверки заметки (3 возможных статуса)"""
    status: Literal["new", "duplicate", "updated"]
    existing_episode_uuid: Optional[str] = None
    old_content_hash: Optional[str] = None  # Для сценария UPDATED
    new_content_hash: str


class ChecknoteService:
    """Сервис для отслеживания заметок через SQLite v2"""

    def __init__(self, db_path: str = "data/episode_metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Инициализация SQLite базы с составным первичным ключом"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episode_metadata (
                    file_path TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    episode_uuid TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processing_status TEXT DEFAULT 'completed',
                    error_message TEXT,
                    PRIMARY KEY (file_path, group_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episode_uuid
                ON episode_metadata(episode_uuid)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processing_status
                ON episode_metadata(processing_status)
            """)

    @staticmethod
    def compute_hash(content: str) -> str:
        """Вычислить SHA-256 хеш контента"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def check_note_status(
        self,
        file_path: str,
        content: str,
        group_id: str
    ) -> ChecknoteResult:
        """
        Проверить статус заметки: NEW, DUPLICATE или UPDATED.

        Алгоритм:
        1. Вычислить хеш нового контента
        2. Поискать запись по (file_path, group_id)
        3. Если не найдена → NEW
        4. Если найдена:
           - Хеш совпадает → DUPLICATE
           - Хеш различается → UPDATED

        Args:
            file_path: Путь к заметке (напр. "coursera/phys/termo.md")
            content: Текст заметки для проверки
            group_id: ID группы графа (для изоляции)

        Returns:
            ChecknoteResult со статусом и метаданными
        """
        new_content_hash = self.compute_hash(content)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT episode_uuid, content_hash
                FROM episode_metadata
                WHERE file_path = ? AND group_id = ? AND processing_status = 'completed'
                """,
                (file_path, group_id)
            )
            result = cursor.fetchone()

        # Сценарий 1: Заметка не найдена → NEW
        if result is None:
            return ChecknoteResult(
                status="new",
                new_content_hash=new_content_hash
            )

        existing_episode_uuid, old_content_hash = result

        # Сценарий 2: Хеш совпадает → DUPLICATE
        if old_content_hash == new_content_hash:
            return ChecknoteResult(
                status="duplicate",
                existing_episode_uuid=existing_episode_uuid,
                old_content_hash=old_content_hash,
                new_content_hash=new_content_hash
            )

        # Сценарий 3: Хеш различается → UPDATED
        return ChecknoteResult(
            status="updated",
            existing_episode_uuid=existing_episode_uuid,
            old_content_hash=old_content_hash,
            new_content_hash=new_content_hash
        )

    def save_metadata(
        self,
        file_path: str,
        episode_uuid: str,
        content_hash: str,
        group_id: str,
        processing_status: str = "completed",
        error_message: Optional[str] = None
    ):
        """
        Сохранить метаданные эпизода после успешной обработки.

        Использует INSERT OR REPLACE для обработки как новых, так и обновленных заметок.

        Args:
            file_path: Путь к заметке
            episode_uuid: UUID созданного эпизода из Neo4j
            content_hash: Хеш контента
            group_id: ID группы графа
            processing_status: Статус обработки
            error_message: Сообщение об ошибке (если есть)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO episode_metadata
                (file_path, group_id, episode_uuid, content_hash,
                 updated_at, processing_status, error_message)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (file_path, group_id, episode_uuid, content_hash,
                 processing_status, error_message)
            )

    def update_content_hash(
        self,
        file_path: str,
        group_id: str,
        new_episode_uuid: str,
        new_content_hash: str
    ):
        """
        Обновить хеш при переобработке заметки (для сценария UPDATED).

        Args:
            file_path: Путь к заметке
            group_id: ID группы графа
            new_episode_uuid: UUID нового эпизода (после переобработки)
            new_content_hash: Новый хеш контента
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE episode_metadata
                SET episode_uuid = ?,
                    content_hash = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE file_path = ? AND group_id = ?
                """,
                (new_episode_uuid, new_content_hash, file_path, group_id)
            )

    def get_metadata_by_path(
        self,
        file_path: str,
        group_id: str
    ) -> Optional[dict]:
        """
        Получить метаданные заметки по пути.

        Args:
            file_path: Путь к заметке
            group_id: ID группы графа

        Returns:
            Словарь с метаданными или None
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT episode_uuid, content_hash, created_at, updated_at, processing_status, error_message
                FROM episode_metadata
                WHERE file_path = ? AND group_id = ?
                """,
                (file_path, group_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def cleanup_orphaned(self, valid_uuids: list[str]):
        """
        Удалить записи для эпизодов, которых больше нет в Neo4j.

        Args:
            valid_uuids: Список UUID эпизодов, существующих в Neo4j
        """
        if not valid_uuids:
            return

        placeholders = ','.join('?' * len(valid_uuids))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"DELETE FROM episode_metadata WHERE episode_uuid NOT IN ({placeholders})",
                valid_uuids
            )
            deleted_count = cursor.rowcount
            print(f"Cleaned up {deleted_count} orphaned metadata records")
