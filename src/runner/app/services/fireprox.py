#!/usr/bin/env python3
"""
FireProx Service - AWS API Gateway proxy management for reconnaissance tasks

This service uses boto3 to directly manage AWS API Gateway proxies that mask
reconnaissance traffic. This replaces the subprocess-based FireProx wrapper
with a native Python implementation for better performance and control.
"""

import json
import logging
import os
import threading
import time
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass
from datetime import datetime
import tldextract
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class TokenBucket:
    """
    Token bucket rate limiter for AWS API throttling

    Implements a thread-safe token bucket algorithm to limit request rate
    """
    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket

        Args:
            rate: Tokens added per second (requests per second)
            capacity: Maximum bucket capacity (burst size)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1, block: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Consume tokens from the bucket

        Args:
            tokens: Number of tokens to consume
            block: Whether to block until tokens are available
            timeout: Maximum time to wait for tokens (only if block=True)

        Returns:
            True if tokens were consumed, False otherwise
        """
        start_time = time.time()

        while True:
            with self._lock:
                # Refill tokens based on elapsed time
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                # Try to consume tokens
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            # If not blocking, return immediately
            if not block:
                return False

            # Check timeout
            if timeout is not None and (time.time() - start_time) >= timeout:
                return False

            # Wait a bit before trying again
            time.sleep(0.1)

@dataclass
class ProxyMapping:
    """Represents a proxy mapping between original and proxy URLs"""
    original_url: str
    proxy_url: str
    proxy_id: str
    region: str
    created_at: datetime

    def to_dict(self) -> Dict:
        return {
            "original_url": self.original_url,
            "proxy_url": self.proxy_url,
            "proxy_id": self.proxy_id,
            "region": self.region,
            "created_at": self.created_at.isoformat()
        }


class FireProxService:
    """Service for managing AWS API Gateway proxies using boto3 directly"""

    def __init__(
        self,
        aws_region: Optional[str] = None,
        rate_limit: float = 5.0,
        burst_size: int = 10,
        max_retries: int = 10
    ):
        """
        Initialize FireProx service with direct boto3 client and rate limiting

        Args:
            aws_region: AWS region for API Gateway (default: from env or ca-central-1)
            rate_limit: Maximum requests per second (default: 5.0)
            burst_size: Maximum burst capacity (default: 10)
            max_retries: Maximum retry attempts for throttled requests (default: 10)
        """
        self.aws_region = aws_region or os.getenv('AWS_REGION', 'ca-central-1')
        self.max_retries = max_retries

        # Validate AWS credentials
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

        if not self.aws_access_key or not self.aws_secret_key:
            logger.warning("AWS credentials not found in environment variables. FireProx may not work.")

        # Initialize rate limiter (token bucket)
        self.rate_limiter = TokenBucket(rate=rate_limit, capacity=burst_size)

        # Initialize boto3 client with retry configuration
        self.client = self._create_client()

        # Thread-safe proxy tracking
        self._lock = threading.Lock()
        self._proxies: Dict[str, ProxyMapping] = {}  # original_url -> ProxyMapping
        self._proxy_ids: Dict[str, str] = {}  # proxy_id -> original_url

        logger.info(
            f"FireProx service initialized (region: {self.aws_region}, "
            f"rate_limit: {rate_limit} req/s, max_retries: {max_retries})"
        )

    def _create_client(self):
        """Create boto3 API Gateway client with retry configuration"""
        try:
            # Configure exponential backoff retry strategy
            retry_config = Config(
                retries={
                    'max_attempts': self.max_retries,
                    'mode': 'adaptive'  # Adaptive mode for better handling of throttling
                },
                # Increase timeouts for throttled requests
                connect_timeout=10,
                read_timeout=30
            )

            if self.aws_access_key and self.aws_secret_key:
                return boto3.client(
                    'apigateway',
                    aws_access_key_id=self.aws_access_key,
                    aws_secret_access_key=self.aws_secret_key,
                    region_name=self.aws_region,
                    config=retry_config
                )
            else:
                # Try instance profile or default credentials
                return boto3.client(
                    'apigateway',
                    region_name=self.aws_region,
                    config=retry_config
                )
        except Exception as e:
            logger.error(f"Failed to create boto3 client: {e}")
            raise

    def _rate_limited_call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute an AWS API call with rate limiting

        This method:
        1. Waits for a token from the rate limiter
        2. Executes the API call
        3. Handles manual backoff for any remaining throttle errors

        Args:
            func: The boto3 client method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            Result from the API call

        Raises:
            ClientError: If the API call fails after all retries
        """
        # Wait for rate limiter token
        if not self.rate_limiter.consume(tokens=1, block=True, timeout=30):
            raise Exception("Rate limiter timeout - too many concurrent requests")

        # Execute the API call
        # boto3's adaptive retry mode will handle most throttling
        try:
            return func(*args, **kwargs)
        except ClientError as e:
            error_code = e.response['Error']['Code']

            # If still throttled after boto3 retries, add additional backoff
            if error_code == 'TooManyRequestsException':
                logger.warning("Throttled even after retries, adding extra delay")
                time.sleep(2)  # Additional backoff

            raise

    def _get_swagger_template(self, target_url: str) -> bytes:
        """
        Generate Swagger/OpenAPI template for API Gateway proxy configuration

        Args:
            target_url: Target URL to proxy requests to

        Returns:
            Encoded Swagger template as bytes
        """
        # Remove trailing slash
        url = target_url.rstrip('/')

        # Generate title from domain
        domain = tldextract.extract(url).domain
        title = f'fireprox_{domain}'

        # Current timestamp
        version_date = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        template = {
            "swagger": "2.0",
            "info": {
                "version": version_date,
                "title": title
            },
            "basePath": "/",
            "schemes": ["https"],
            "paths": {
                "/": {
                    "get": {
                        "parameters": [
                            {
                                "name": "proxy",
                                "in": "path",
                                "required": True,
                                "type": "string"
                            },
                            {
                                "name": "X-My-X-Forwarded-For",
                                "in": "header",
                                "required": False,
                                "type": "string"
                            }
                        ],
                        "responses": {},
                        "x-amazon-apigateway-integration": {
                            "uri": f"{url}/",
                            "responses": {
                                "default": {
                                    "statusCode": "200"
                                }
                            },
                            "requestParameters": {
                                "integration.request.path.proxy": "method.request.path.proxy",
                                "integration.request.header.X-Forwarded-For": "method.request.header.X-My-X-Forwarded-For"
                            },
                            "passthroughBehavior": "when_no_match",
                            "httpMethod": "ANY",
                            "cacheNamespace": "irx7tm",
                            "cacheKeyParameters": ["method.request.path.proxy"],
                            "type": "http_proxy"
                        }
                    }
                },
                "/{proxy+}": {
                    "x-amazon-apigateway-any-method": {
                        "produces": ["application/json"],
                        "parameters": [
                            {
                                "name": "proxy",
                                "in": "path",
                                "required": True,
                                "type": "string"
                            },
                            {
                                "name": "X-My-X-Forwarded-For",
                                "in": "header",
                                "required": False,
                                "type": "string"
                            }
                        ],
                        "responses": {},
                        "x-amazon-apigateway-integration": {
                            "uri": f"{url}/{{proxy}}",
                            "responses": {
                                "default": {
                                    "statusCode": "200"
                                }
                            },
                            "requestParameters": {
                                "integration.request.path.proxy": "method.request.path.proxy",
                                "integration.request.header.X-Forwarded-For": "method.request.header.X-My-X-Forwarded-For"
                            },
                            "passthroughBehavior": "when_no_match",
                            "httpMethod": "ANY",
                            "cacheNamespace": "irx7tm",
                            "cacheKeyParameters": ["method.request.path.proxy"],
                            "type": "http_proxy"
                        }
                    }
                }
            }
        }

        return json.dumps(template).encode('utf-8')

    def create_proxy(self, target_url: str) -> Optional[ProxyMapping]:
        """
        Create a new API Gateway proxy for the target URL

        Args:
            target_url: Original target URL to proxy

        Returns:
            ProxyMapping if successful, None on failure
        """
        with self._lock:
            # Check if proxy already exists for this URL
            if target_url in self._proxies:
                logger.info(f"Proxy already exists for {target_url}, reusing existing proxy")
                return self._proxies[target_url]

        try:
            logger.info(f"Creating API Gateway proxy for {target_url}")

            # Generate Swagger template
            template = self._get_swagger_template(target_url)

            # Import REST API with proxy configuration (rate-limited)
            response = self._rate_limited_call(
                self.client.import_rest_api,
                parameters={
                    'endpointConfigurationTypes': 'REGIONAL'
                },
                body=template
            )

            api_id = response['id']
            api_name = response['name']
            created_date = response['createdDate']

            logger.info(f"API Gateway created: {api_id} ({api_name})")

            # Create deployment to activate the proxy (rate-limited)
            deployment_response = self._rate_limited_call(
                self.client.create_deployment,
                restApiId=api_id,
                stageName='fireprox',
                stageDescription='FireProx Production',
                description='FireProx Production Deployment'
            )

            # Construct proxy URL
            proxy_url = f'https://{api_id}.execute-api.{self.aws_region}.amazonaws.com/fireprox/'

            mapping = ProxyMapping(
                original_url=target_url,
                proxy_url=proxy_url,
                proxy_id=api_id,
                region=self.aws_region,
                created_at=created_date
            )

            # Store mapping
            with self._lock:
                self._proxies[target_url] = mapping
                self._proxy_ids[api_id] = target_url

            logger.info(f"Created proxy: {target_url} -> {proxy_url} (ID: {api_id})")
            return mapping

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"AWS API error creating proxy for {target_url}: {error_code} - {error_message}")
            return None
        except Exception as e:
            logger.error(f"Error creating proxy for {target_url}: {e}")
            return None

    def delete_proxy(self, proxy_id: str) -> bool:
        """
        Delete an API Gateway proxy by ID

        This is optimized to delete directly without listing first,
        unlike the original FireProx implementation.

        Args:
            proxy_id: API Gateway ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Deleting API Gateway proxy {proxy_id}")

            # Direct delete - no need to list first! (rate-limited)
            self._rate_limited_call(
                self.client.delete_rest_api,
                restApiId=proxy_id
            )

            # Remove from tracking
            with self._lock:
                if proxy_id in self._proxy_ids:
                    original_url = self._proxy_ids[proxy_id]
                    del self._proxies[original_url]
                    del self._proxy_ids[proxy_id]

            logger.info(f"Successfully deleted proxy {proxy_id}")
            return True

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            if error_code == 'NotFoundException':
                logger.warning(f"Proxy {proxy_id} not found (may already be deleted)")
                # Still clean up from tracking
                with self._lock:
                    if proxy_id in self._proxy_ids:
                        original_url = self._proxy_ids[proxy_id]
                        del self._proxies[original_url]
                        del self._proxy_ids[proxy_id]
                return True

            logger.error(f"AWS API error deleting proxy {proxy_id}: {error_code} - {error_message}")
            return False
        except Exception as e:
            logger.error(f"Error deleting proxy {proxy_id}: {e}")
            return False

    def list_proxies(self) -> List[ProxyMapping]:
        """
        List all active proxies managed by this service instance

        Returns:
            List of ProxyMapping objects
        """
        with self._lock:
            return list(self._proxies.values())

    def cleanup_all(self) -> Tuple[int, int]:
        """
        Delete all proxies created by this service instance

        Returns:
            Tuple of (successful_deletions, failed_deletions)
        """
        proxy_list = self.list_proxies()

        if not proxy_list:
            logger.info("No proxies to clean up")
            return (0, 0)

        logger.info(f"Cleaning up {len(proxy_list)} FireProx proxies")

        success_count = 0
        failure_count = 0

        for mapping in proxy_list:
            if self.delete_proxy(mapping.proxy_id):
                success_count += 1
            else:
                failure_count += 1

        logger.info(f"Cleanup complete: {success_count} successful, {failure_count} failed")
        return (success_count, failure_count)
