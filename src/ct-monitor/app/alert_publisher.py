"""
Publishes CT monitoring alerts to NATS JetStream for downstream processing.

Events are published to the EVENTS stream which triggers:
1. Automatic typosquat analysis workflow
2. Notifications to security team
3. Dashboard updates
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional
import asyncio

import nats
import nats.js.errors
from nats.js.api import RetentionPolicy
from nats.errors import TimeoutError as NatsTimeoutError

from models import MatchResult, CertificateInfo

logger = logging.getLogger(__name__)


class CTAlertPublisher:
    """
    Publishes Certificate Transparency alerts to NATS JetStream.
    
    Alert events trigger downstream processing:
    - Automatic typosquat_detection task with analyze_input_as_variations=true
    - Discord/Slack notifications via notifier service
    - Dashboard real-time updates
    
    Events are published to subject: events.typosquat.ct_alert
    This matches the event-handler's expected format where event_type is parsed
    by removing the 'events.' prefix -> typosquat.ct_alert
    """
    
    STREAM_NAME = "EVENTS"
    # Subject format matches API's event_publisher: events.{category}.{type}
    # event-handler parses this as event_type = "typosquat.ct_alert"
    SUBJECT = "events.typosquat.ct_alert"
    
    def __init__(self, nats_url: str = "nats://nats:4222"):
        self.nats_url = nats_url
        self._nc: Optional[nats.NATS] = None
        self._js = None
        self._connected = False
    
    async def connect(self, max_retries: int = 5, retry_delay: int = 5):
        """
        Connect to NATS and get JetStream context.
        
        Args:
            max_retries: Maximum connection attempts
            retry_delay: Seconds between retries
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to NATS at {self.nats_url} (attempt {attempt + 1}/{max_retries})...")
                
                self._nc = await nats.connect(
                    self.nats_url,
                    reconnect_time_wait=2,
                    max_reconnect_attempts=10,
                    error_cb=self._error_callback,
                    disconnected_cb=self._disconnected_callback,
                    reconnected_cb=self._reconnected_callback
                )
                
                self._js = self._nc.jetstream()
                
                # Ensure stream exists
                await self._ensure_stream()
                
                self._connected = True
                logger.info(f"✅ Connected to NATS JetStream at {self.nats_url}")
                return
                
            except Exception as e:
                logger.error(f"Failed to connect to NATS: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    raise RuntimeError(f"Failed to connect to NATS after {max_retries} attempts")
    
    async def _ensure_stream(self):
        """Ensure the EVENTS stream exists with correct subjects"""
        try:
            # Try to get existing stream info
            info = await self._js.stream_info(self.STREAM_NAME)
            subjects = info.config.subjects or []
            logger.debug(f"Stream '{self.STREAM_NAME}' exists with subjects: {subjects}")
            
            # Check if our subject pattern is covered (events.> pattern like the API uses)
            if "events.>" not in subjects:
                # Need to update stream to include our subjects
                logger.info(f"Updating stream '{self.STREAM_NAME}' to include events.>")
                new_subjects = list(set(subjects + ["events.>"]))
                await self._js.update_stream(
                    name=self.STREAM_NAME,
                    subjects=new_subjects
                )
                logger.info(f"✅ Updated stream subjects: {new_subjects}")
                
        except nats.js.errors.NotFoundError:
            # Stream doesn't exist, create it with same config as API's event_publisher
            logger.info(f"Creating stream '{self.STREAM_NAME}'...")
            await self._js.add_stream(
                name=self.STREAM_NAME,
                subjects=["events.>"],  # Match API's subject pattern
                retention=RetentionPolicy.LIMITS,
                max_msgs=1000000,
                max_bytes=1024 * 1024 * 1024,  # 1GB
                max_age=7 * 24 * 60 * 60 * 1000000000,  # 7 days in nanoseconds
            )
            logger.info(f"✅ Created stream '{self.STREAM_NAME}'")
    
    async def _error_callback(self, e):
        """Handle NATS errors"""
        logger.error(f"NATS error: {e}")
    
    async def _disconnected_callback(self):
        """Handle NATS disconnection"""
        logger.warning("Disconnected from NATS")
        self._connected = False
    
    async def _reconnected_callback(self):
        """Handle NATS reconnection"""
        logger.info("Reconnected to NATS")
        self._connected = True
    
    async def disconnect(self):
        """Disconnect from NATS gracefully"""
        if self._nc:
            try:
                await self._nc.drain()
                logger.info("Disconnected from NATS")
            except Exception as e:
                logger.error(f"Error disconnecting from NATS: {e}")
            finally:
                self._connected = False
    
    def _calculate_priority(self, match_result: MatchResult) -> str:
        """
        Calculate alert priority based on match characteristics.
        
        Priority levels:
        - critical: Homoglyph attacks (legacy; rare)
        - high: Very high similarity (>0.95) or TLD swap
        - medium: High similarity (>0.85)
        - low: Moderate similarity (threshold to 0.85)
        """
        if match_result.match_type == "homoglyph":
            return "critical"
        elif match_result.match_type == "tld_swap":
            return "high"
        elif match_result.similarity_score >= 0.95:
            return "high"
        elif match_result.similarity_score >= 0.85:
            return "medium"
        else:
            return "low"
    
    async def publish_alert(
        self,
        match_result: MatchResult,
        cert_info: CertificateInfo,
        program_name: str
    ) -> bool:
        """
        Publish a CT alert event for a detected typosquat certificate.
        
        Args:
            match_result: Domain match result
            cert_info: Full certificate information
            program_name: Program this alert belongs to
            
        Returns:
            True if published successfully, False otherwise
        """
        if not self._js or not self._connected:
            logger.error("Not connected to NATS, cannot publish alert")
            return False
        
        try:
            priority = self._calculate_priority(match_result)
            
            # Build payload in format expected by event-handler
            # This matches the handlers.yaml expectations for typosquat.ct_alert
            payload = {
                # Required by event-handler routing
                "event": "ct_typosquat_alert",
                "program_name": program_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                
                # Fields used by handlers.yaml conditions and templates
                "auto_analyze": True,
                "priority": priority,
                
                # Match information
                "protected_domain": match_result.protected_domain,
                "detected_domain": match_result.cert_domain,
                "similarity_score": match_result.similarity_score,
                "match_type": match_result.match_type,
                "match_details": match_result.details,
                
                # For batch processing - single domain as array
                "detected_domain_list_array": [match_result.cert_domain],
                "detected_domain_list": match_result.cert_domain,
                
                # Certificate information (nested for template access like {certificate.issuer})
                "certificate": cert_info.to_dict(),
                
                # Also expose cert fields at root level for easy template access
                "cert_issuer": cert_info.issuer,
                "cert_fingerprint": cert_info.fingerprint,
                "cert_domains": cert_info.domains,
                
                # Metadata
                "source": "ct_monitor",
            }
            
            # Create unique message ID for deduplication
            msg_id = f"ct-{cert_info.fingerprint or 'unknown'}-{match_result.cert_domain}-{program_name}"
            
            ack = await self._js.publish(
                self.SUBJECT,
                json.dumps(payload).encode(),
                headers={"Nats-Msg-Id": msg_id},
                timeout=10.0  # 10 second timeout
            )
            
            logger.info(
                f"📢 Published CT alert: {match_result.cert_domain} -> {match_result.protected_domain} "
                f"(type={match_result.match_type}, score={match_result.similarity_score:.2f}, "
                f"priority={priority}, stream_seq={ack.seq})"
            )
            
            return True
            
        except NatsTimeoutError:
            logger.error("Timeout publishing alert to NATS")
            return False
        except Exception as e:
            logger.error(f"Error publishing alert: {e}")
            return False
    
    async def publish_batch(
        self,
        matches: list,  # List of (MatchResult, CertificateInfo, str) tuples
    ) -> int:
        """
        Publish multiple alerts in batch.
        
        Args:
            matches: List of (match_result, cert_info, program_name) tuples
            
        Returns:
            Number of successfully published alerts
        """
        published = 0
        for match_result, cert_info, program_name in matches:
            if await self.publish_alert(match_result, cert_info, program_name):
                published += 1
        return published
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to NATS"""
        return self._connected

