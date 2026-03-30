from sqlalchemy import text
from typing import Dict, Any, Optional, List
import logging
import uuid
from datetime import datetime, timezone
import json
from db import get_db_session

logger = logging.getLogger(__name__)


class ActionLogRepository:
    """Repository for action logging operations"""

    @staticmethod
    async def log_action(
        entity_type: str,
        entity_id: str,
        action_type: str,
        user_id: str,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log an action performed by a user on an entity.

        Args:
            entity_type: Type of entity (e.g., 'typosquat_finding')
            entity_id: ID of the entity being acted upon
            action_type: Type of action (e.g., 'status_change')
            user_id: ID of the user performing the action
            old_value: Previous state of the entity
            new_value: New state of the entity
            metadata: Additional metadata (comments, action_taken, etc.)

        Returns:
            str: ID of the created action log
        """
        try:
            async with get_db_session() as session:
                log_id = str(uuid.uuid4())

                logger.debug(f"Attempting to log action: {action_type} for entity {entity_type}:{entity_id}")

                # Use raw SQL with named parameters
                query = text("""
                    INSERT INTO action_logs (
                        id, entity_type, entity_id, action_type, user_id,
                        old_value, new_value, metadata, created_at
                    ) VALUES (
                        :id, :entity_type, :entity_id, :action_type, :user_id,
                        CAST(:old_value AS jsonb), CAST(:new_value AS jsonb), CAST(:metadata AS jsonb), :created_at
                    )
                """)

                # Convert to JSON strings for JSONB fields
                old_value_json = json.dumps(old_value) if old_value else None
                new_value_json = json.dumps(new_value) if new_value else None
                metadata_json = json.dumps(metadata) if metadata else None

                # Execute with dictionary parameters
                session.execute(query, {
                    'id': log_id,
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'action_type': action_type,
                    'user_id': user_id,
                    'old_value': old_value_json,
                    'new_value': new_value_json,
                    'metadata': metadata_json,
                    'created_at': datetime.now(timezone.utc)
                })

                session.commit()

                logger.info(f"Action logged successfully: {action_type} on {entity_type} {entity_id} by user {user_id}")
                return log_id

        except Exception as e:
            logger.error(f"Error logging action: {str(e)}", exc_info=True)
            # Don't re-raise to avoid breaking the main functionality
            return None

    @staticmethod
    async def get_action_logs_for_entity(
        entity_type: str,
        entity_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get action logs for a specific entity.

        Args:
            entity_type: Type of entity
            entity_id: ID of the entity
            limit: Maximum number of logs to return
            offset: Number of logs to skip

        Returns:
            List of action log dictionaries
        """
        try:
            async with get_db_session() as session:
                query = text("""
                    SELECT
                        al.id,
                        al.entity_type,
                        al.entity_id,
                        al.action_type,
                        al.user_id,
                        al.old_value,
                        al.new_value,
                        al.metadata,
                        al.created_at,
                        u.username,
                        u.first_name,
                        u.last_name
                    FROM action_logs al
                    LEFT JOIN users u ON al.user_id = u.id
                    WHERE al.entity_type = :entity_type
                    AND al.entity_id = :entity_id
                    ORDER BY al.created_at DESC
                    LIMIT :limit OFFSET :offset
                """)

                result = session.execute(query, {
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'limit': limit,
                    'offset': offset
                })

                rows = result.fetchall()
                logs = []

                for row in rows:
                    logs.append({
                        'id': row.id,
                        'entity_type': row.entity_type,
                        'entity_id': row.entity_id,
                        'action_type': row.action_type,
                        'user_id': row.user_id,
                        'old_value': row.old_value,
                        'new_value': row.new_value,
                        'metadata': row.metadata,
                        'created_at': row.created_at,
                        'user': {
                            'username': row.username,
                            'first_name': row.first_name,
                            'last_name': row.last_name
                        } if row.username else None
                    })

                return logs

        except Exception as e:
            logger.error(f"Error getting action logs for entity {entity_type} {entity_id}: {str(e)}")
            raise

    @staticmethod
    async def get_user_actions(
        user_id: str,
        entity_type: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get actions performed by a specific user.

        Args:
            user_id: ID of the user
            entity_type: Optional filter by entity type
            action_type: Optional filter by action type
            limit: Maximum number of logs to return
            offset: Number of logs to skip

        Returns:
            List of action log dictionaries
        """
        try:
            async with get_db_session() as session:
                where_conditions = ["al.user_id = :user_id"]
                params = {'user_id': user_id, 'limit': limit, 'offset': offset}

                if entity_type:
                    where_conditions.append("al.entity_type = :entity_type")
                    params['entity_type'] = entity_type

                if action_type:
                    where_conditions.append("al.action_type = :action_type")
                    params['action_type'] = action_type

                where_clause = " AND ".join(where_conditions)

                query = text(f"""
                    SELECT
                        al.id,
                        al.entity_type,
                        al.entity_id,
                        al.action_type,
                        al.user_id,
                        al.old_value,
                        al.new_value,
                        al.metadata,
                        al.created_at
                    FROM action_logs al
                    WHERE {where_clause}
                    ORDER BY al.created_at DESC
                    LIMIT :limit OFFSET :offset
                """)

                result = session.execute(query, params)
                rows = result.fetchall()

                logs = []
                for row in rows:
                    logs.append({
                        'id': row.id,
                        'entity_type': row.entity_type,
                        'entity_id': row.entity_id,
                        'action_type': row.action_type,
                        'user_id': row.user_id,
                        'old_value': row.old_value,
                        'new_value': row.new_value,
                        'metadata': row.metadata,
                        'created_at': row.created_at
                    })

                return logs

        except Exception as e:
            logger.error(f"Error getting user actions for user {user_id}: {str(e)}")
            raise

    @staticmethod
    async def get_action_logs_with_filters(
        filters: Dict[str, Any],
        search_term: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get action logs with various filters.

        Args:
            filters: Dictionary of filters (entity_type, action_type, entity_id, program_name, program_names)
            search_term: Optional search term to search in log content
            limit: Maximum number of logs to return
            offset: Number of logs to skip

        Returns:
            List of action log dictionaries
        """
        try:
            async with get_db_session() as session:
                where_conditions = []
                params = {'limit': limit, 'offset': offset}

                # Base filters
                if filters.get('entity_type'):
                    where_conditions.append("al.entity_type = :entity_type")
                    params['entity_type'] = filters['entity_type']

                if filters.get('action_type'):
                    where_conditions.append("al.action_type = :action_type")
                    params['action_type'] = filters['action_type']

                if filters.get('entity_id'):
                    where_conditions.append("al.entity_id = :entity_id")
                    params['entity_id'] = filters['entity_id']

                # Program filtering
                if filters.get('program_name'):
                    where_conditions.append("p.name = :program_name")
                    params['program_name'] = filters['program_name']
                elif filters.get('program_names'):
                    program_placeholders = []
                    for i, program_name in enumerate(filters['program_names']):
                        placeholder = f"program_name_{i}"
                        program_placeholders.append(f":{placeholder}")
                        params[placeholder] = program_name
                    where_conditions.append(f"p.name IN ({', '.join(program_placeholders)})")

                # Search functionality
                if search_term:
                    search_conditions = [
                        "al.action_type ILIKE :search",
                        "al.entity_id::text ILIKE :search",
                        "al.old_value::text ILIKE :search",
                        "al.new_value::text ILIKE :search",
                        "al.metadata::text ILIKE :search",
                        "u.username ILIKE :search"
                    ]
                    where_conditions.append(f"({' OR '.join(search_conditions)})")
                    params['search'] = f"%{search_term}%"

                where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

                query = text(f"""
                    SELECT
                        al.id,
                        al.entity_type,
                        al.entity_id,
                        al.action_type,
                        al.user_id,
                        al.old_value,
                        al.new_value,
                        al.metadata,
                        al.created_at,
                        u.username,
                        u.first_name,
                        u.last_name,
                        td.typo_domain,
                        p.name as program_name
                    FROM action_logs al
                    LEFT JOIN users u ON al.user_id = u.id
                    LEFT JOIN typosquat_domains td ON al.entity_id::uuid = td.id AND al.entity_type = 'typosquat_finding'
                    LEFT JOIN programs p ON td.program_id = p.id
                    WHERE {where_clause}
                    ORDER BY al.created_at DESC
                    LIMIT :limit OFFSET :offset
                """)

                result = session.execute(query, params)
                rows = result.fetchall()

                logs = []
                for row in rows:
                    log_entry = {
                        'id': row.id,
                        'entity_type': row.entity_type,
                        'entity_id': row.entity_id,
                        'action_type': row.action_type,
                        'user_id': row.user_id,
                        'old_value': row.old_value,
                        'new_value': row.new_value,
                        'metadata': row.metadata,
                        'created_at': row.created_at,
                        'user': {
                            'username': row.username,
                            'first_name': row.first_name,
                            'last_name': row.last_name
                        } if row.username else None
                    }

                    # Add entity details for typosquat findings
                    if row.entity_type == 'typosquat_finding' and hasattr(row, 'typo_domain') and row.typo_domain:
                        log_entry['entity_details'] = {
                            'typo_domain': row.typo_domain,
                            'program_name': row.program_name
                        }

                    logs.append(log_entry)

                return logs

        except Exception as e:
            logger.error(f"Error getting action logs with filters: {str(e)}")
            raise