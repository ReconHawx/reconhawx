"""
Refactored typosquat detection components following Single Responsibility Principle

This module breaks down the monolithic TyposquatDetection class into focused components:
- VariationGenerator: Domain variation generation
- VariationCacheManager: Redis-based caching of tested variations with TTL
- TyposquatAnalyzer: Core detection and analysis logic
- SubdomainWorkflowOrchestrator: Multi-phase workflow management
- ScreenshotProcessor: Screenshot handling and API uploads
- ApiClient: API communication layer
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
import json
import base64
import os
import subprocess
from datetime import datetime
import aiohttp
import requests
import tempfile
import tarfile
import redis
import ipaddress

from .base import FindingType
from models.findings import TyposquatDomain
from utils import normalize_url_for_storage
from utils.html_extractor import extract_text_from_gowitness_jsonl, extract_text_from_image_ocr

logger = logging.getLogger(__name__)


def _decode_gowitness_filename_to_url(filename: str) -> Optional[str]:
    """
    Decode screenshot filename back to URL.
    Filenames are created by screenshotter.sh with encoding: :// -> ---, : -> -, / -> ---.
    Example: https---example.com-443.png -> https://example.com:443/
    Returns None if decoding fails.
    """
    if not filename or not filename.lower().endswith('.png'):
        return None
    try:
        url = filename[:-4]  # Remove .png extension
        # First --- is :// for the protocol
        url = url.replace('---', '://', 1)
        # Remaining --- are / for path segments
        url = url.replace('---', '/')
        # Handle port numbers: -PORT at end of hostname (before any path)
        if '://' in url:
            after_proto = url.split('://', 1)[1]
            host_part = after_proto.split('/')[0]
            if ':' not in host_part:
                port_match = re.search(r'-(\d+)-?$', host_part)
                if port_match:
                    port = port_match.group(1)
                    new_host = re.sub(r'-\d+-?$', f':{port}', host_part)
                    url = url.replace(host_part, new_host, 1)
        # Clean up trailing dashes
        url = url.rstrip('-')
        # Ensure root path has trailing slash for consistency
        if not url.endswith('/') and '/' not in url.split('://', 1)[1]:
            url += '/'
        return url
    except Exception as e:
        logger.debug(f"Failed to decode gowitness filename {filename}: {e}")
        return None


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def _levenshtein_similarity(s1: str, s2: str) -> float:
    """Calculate Levenshtein similarity ratio (0.0-1.0)"""
    if s1 == s2:
        return 1.0
    
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    
    distance = _levenshtein_distance(s1, s2)
    return 1.0 - (distance / max_len)


def _extract_apex_domain(domain: str) -> str:
    """Extract apex domain (e.g., 'example.com' from 'www.example.com')"""
    parts = domain.lower().split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain.lower()


def _calculate_domain_similarity(typo_domain: str, protected_domains: List[str]) -> Tuple[float, Optional[str], float]:
    """
    Calculate maximum similarity between typo_domain and any protected domain.
    
    Returns:
        Tuple of (max_similarity: float, matched_protected_domain: Optional[str], similarity_percent: float)
        - max_similarity: Maximum similarity score (0.0-1.0)
        - matched_protected_domain: The protected domain that matched (or None if no match)
        - similarity_percent: Similarity as percentage (0-100)
    """
    if not protected_domains:
        return 0.0, None, 0.0
    
    typo_apex = _extract_apex_domain(typo_domain)
    max_similarity = 0.0
    matched_domain = None
    
    for protected in protected_domains:
        protected_apex = _extract_apex_domain(protected)
        similarity = _levenshtein_similarity(typo_apex, protected_apex)
        if similarity > max_similarity:
            max_similarity = similarity
            matched_domain = protected
    
    similarity_percent = max_similarity * 100
    logger.info(f"Max similarity for {typo_domain} is {max_similarity} ({similarity_percent:.1f}%) with {matched_domain}")
    return max_similarity, matched_domain, similarity_percent

# ---------------------------------------------------------------------------
# Parking service indicators (derived from parking_services.json)
# ---------------------------------------------------------------------------

# IP ranges commonly used by parking providers (A records)
PARKING_A_CIDRS: List[str] = [
    # ParkingCrew
    "185.53.176.0/22",
    # dan.com
    "3.64.163.50/32",
    "52.58.78.16/32",
    # GoDaddy Parking / CashParking
    "34.102.136.180/32",
    "34.98.99.30/32",
    "35.186.238.101/32",
    # Sedo
    "91.195.240.0/23",
    "64.190.62.0/23",
    # Uniregistry
    "52.128.23.153/32",
    "34.102.221.37/32",
    # BODIS
    "199.59.240.0/22",
    # Namecheap
    "99.83.154.118/32",
    # Above
    "103.224.182.0/23",
    "103.224.212.0/23",
    # DomainSponsor / RookMedia
    "66.81.199.0/24",
    "141.8.224.195/32",
    # Bluehost
    "74.220.199.6/32",
    "74.220.199.8/32",
    "74.220.199.9/32",
    "74.220.199.14/32",
    "74.220.199.15/32",
    # Dynadot
    "75.2.18.233/32",
    "75.2.115.196/32",
]

PARKING_A_NETWORKS = [ipaddress.ip_network(cidr) for cidr in PARKING_A_CIDRS]


class VariationGenerator:
    """Handles domain variation generation using dnstwist with fallback strategies"""

    def __init__(self, redis_client=None):
        self.available_fuzzers = [
            'insertion', 'replacement', 'omission', 'repetition', 'transposition',
            'hyphenation', 'vowel-swap', 'homoglyph', 'addition', 'bitsquatting',
            'subdomain', 'plural', 'various'
        ]

        # Initialize with optional dictionaries
        self.dictionary = []
        self.tld_dictionary = []

        # Redis client for offset tracking
        self.redis_client = redis_client

        # Try to import dnstwist Fuzzer class
        try:
            from dnstwist import Fuzzer
            self.Fuzzer = Fuzzer
            self.dnstwist_available = True
            logger.info("dnstwist library available for variation generation")
        except ImportError:
            logger.warning("dnstwist library not available - using fallback subprocess method")
            self.Fuzzer = None
            self.dnstwist_available = False

    def _get_variation_offset(self, domain: str, program_name: str) -> int:
        """Get the current offset for variation generation for a domain"""
        if not self.redis_client:
            return 0

        try:
            offset_key = f"typosquat:variation_offset:{program_name}:{domain}"
            stored_offset = self.redis_client.get(offset_key)
            if stored_offset:
                offset_str = stored_offset.decode('utf-8') if isinstance(stored_offset, bytes) else str(stored_offset)
                return int(offset_str)
        except Exception as e:
            logger.debug(f"Error getting variation offset for {domain}: {e}")

        return 0

    def _update_variation_offset(self, domain: str, program_name: str, new_offset: int):
        """Update the offset for variation generation for a domain"""
        if not self.redis_client:
            return

        try:
            offset_key = f"typosquat:variation_offset:{program_name}:{domain}"
            self.redis_client.set(offset_key, str(new_offset))
            logger.debug(f"Updated variation offset for {domain} to {new_offset}")
        except Exception as e:
            logger.warning(f"Error updating variation offset for {domain}: {e}")

    def generate_variations_with_fuzzers(self, domain: str, max_variations: int = 100,
                                       fuzzers: Optional[List[str]] = None, program_name: str = "") -> Dict[str, List[str]]:
        """Generate domain variations using dnstwist library with offset-based rotation"""
        if '.' not in domain:
            logger.warning(f"Invalid domain format: {domain}")
            return {}

        # Analyze domain characteristics
        parts = domain.rsplit('.', 1)
        if len(parts) == 2:
            domain_name, tld = parts
            logger.info(f"🔍 DOMAIN ANALYSIS for {domain}:")
            logger.info(f"   Domain name: {domain_name}")
            logger.info(f"   TLD: {tld}")
            logger.info(f"   Name length: {len(domain_name)} characters")
            logger.info(f"   Total domain length: {len(domain)} characters")

            # Estimate variation potential
            char_count = len(domain_name)
            if char_count < 5:
                logger.info("   ⚠️ SHORT DOMAIN: Shorter domains (<5 chars) generate fewer variations")
            elif char_count > 15:
                logger.info("   ℹ️ LONG DOMAIN: Longer domains (>15 chars) can generate many variations")

            # Check for numbers
            has_numbers = any(c.isdigit() for c in domain_name)
            if has_numbers:
                logger.info("   ℹ️ Contains numbers: May generate additional numeric variations")

            # Check for hyphens
            has_hyphens = '-' in domain_name
            if has_hyphens:
                logger.info("   ℹ️ Contains hyphens: May affect hyphenation fuzzer")

        # Log fuzzer configuration
        if fuzzers:
            logger.info(f"📋 Requested fuzzers: {fuzzers}")
            invalid_fuzzers = [f for f in fuzzers if f not in self.available_fuzzers]
            if invalid_fuzzers:
                logger.warning(f"⚠️ Invalid fuzzers (will be ignored): {invalid_fuzzers}")
            valid_fuzzers = [f for f in fuzzers if f in self.available_fuzzers]
            logger.info(f"✅ Valid fuzzers to use: {valid_fuzzers}")
        else:
            logger.info("📋 No specific fuzzers requested - using ALL available fuzzers")
            logger.info(f"📋 Available fuzzers: {self.available_fuzzers}")

        # Log dictionary configuration
        logger.debug(f"Dictionary words: {len(self.dictionary)}")
        logger.debug(f"TLD dictionary: {len(self.tld_dictionary)}")

        # Use dnstwist library if available
        if self.dnstwist_available and self.Fuzzer:
            try:
                logger.info(f"🔧 Generating variations for {domain} using dnstwist library")

                # Use dnstwist's Fuzzer class to generate variations (with dictionaries)
                with self.Fuzzer(domain, dictionary=self.dictionary, tld_dictionary=self.tld_dictionary) as fuzzer:
                    fuzzer.generate(fuzzers=fuzzers)

                    # Get all permutations except the original
                    permutations = fuzzer.permutations()

                    # Filter out the original domain and track fuzzer statistics
                    all_variations = []
                    fuzzer_stats = {}
                    for perm in permutations:
                        fuzzer_type = perm.get('fuzzer', 'unknown')
                        domain_name = perm.get('domain', '')

                        # Skip original domain
                        if fuzzer_type == '*original' or domain_name == domain:
                            continue

                        if domain_name and domain_name != domain:
                            all_variations.append(perm)
                            # Track fuzzer statistics
                            fuzzer_stats[fuzzer_type] = fuzzer_stats.get(fuzzer_type, 0) + 1

                    total_variations = len(all_variations)

                    # Log generation statistics
                    logger.info(f"📊 GENERATION STATS for {domain}:")
                    logger.info(f"   Total variations generated: {total_variations}")

                    # Provide context about variation count
                    domain_name_len = len(domain.rsplit('.', 1)[0]) if '.' in domain else len(domain)
                    if total_variations < 100:
                        logger.warning(f"   ⚠️ LOW VARIATION COUNT: Only {total_variations} variations")
                        logger.warning(f"   This may be normal for short domains ({domain_name_len} chars)")
                        logger.warning("   Consider: Using dictionaries, enabling more fuzzers, or different TLDs")
                    elif total_variations < 500:
                        logger.info(f"   ℹ️ MODERATE VARIATION COUNT: {total_variations} variations")
                        logger.info(f"   Typical for domains of {domain_name_len} characters")
                    elif total_variations < 2000:
                        logger.info(f"   ✅ GOOD VARIATION COUNT: {total_variations} variations")
                    else:
                        logger.info(f"   🎯 HIGH VARIATION COUNT: {total_variations} variations")
                        logger.info(f"   Excellent coverage for domain {domain}")

                    logger.info("   Variations by fuzzer type:")
                    for fuzzer_type, count in sorted(fuzzer_stats.items(), key=lambda x: x[1], reverse=True):
                        percentage = (count / total_variations * 100) if total_variations > 0 else 0
                        logger.info(f"      {fuzzer_type:20s}: {count:4d} ({percentage:5.1f}%)")

                    # Check if any fuzzers produced no variations
                    requested_fuzzers = set(fuzzers) if fuzzers else set(self.available_fuzzers)
                    active_fuzzers = set(fuzzer_stats.keys())
                    inactive_fuzzers = requested_fuzzers - active_fuzzers
                    if inactive_fuzzers:
                        logger.warning(f"   ⚠️ Fuzzers with ZERO variations: {sorted(inactive_fuzzers)}")
                        logger.warning("   These fuzzers may not be applicable to this domain")

                    logger.debug(f"Generated {total_variations} variations for {domain} using dnstwist library")

                    # Get current offset for this domain
                    offset = self._get_variation_offset(domain, program_name) if program_name else 0

                    # If offset is beyond total variations, wrap around
                    if offset >= total_variations:
                        offset = 0
                        logger.info(f"🔄 Variation offset wrapped around for {domain}, starting from 0")

                    logger.info(f"📍 SELECTION WINDOW for {domain}:")
                    logger.info(f"   Requesting: {max_variations} variations")
                    logger.info(f"   Available: {total_variations} total variations")
                    logger.info(f"   Selection offset: {offset}")
                    logger.info(f"   Will select: variations {offset} to {min(offset + max_variations, total_variations)}")

                    # Select variations starting from offset
                    selected_variations = []
                    end_offset = min(offset + max_variations, total_variations)

                    for i in range(offset, end_offset):
                        selected_variations.append(all_variations[i])

                    # If we didn't get enough variations, wrap around from the beginning
                    remaining = max_variations - len(selected_variations)
                    if remaining > 0 and offset > 0:
                        logger.info(f"🔄 Wrapping around to beginning to get {remaining} more variations")
                        logger.info(f"   Will also select: variations 0 to {min(remaining, offset)}")
                        for i in range(0, min(remaining, offset)):
                            selected_variations.append(all_variations[i])

                    # Build a dictionary mapping domains to their fuzzers
                    domain_to_fuzzers = {}
                    selected_fuzzer_stats = {}
                    for perm in selected_variations:
                        fuzzer_type = perm.get('fuzzer', 'unknown')
                        domain_name = perm.get('domain', '')

                        if domain_name not in domain_to_fuzzers:
                            domain_to_fuzzers[domain_name] = []

                        if fuzzer_type not in domain_to_fuzzers[domain_name]:
                            domain_to_fuzzers[domain_name].append(fuzzer_type)

                        # Track selected fuzzer statistics
                        selected_fuzzer_stats[fuzzer_type] = selected_fuzzer_stats.get(fuzzer_type, 0) + 1

                    # Update offset for next run
                    new_offset = end_offset if end_offset < total_variations else 0

                    # Log selection results
                    logger.info(f"✅ SELECTED {len(selected_variations)} variations for {domain}:")
                    logger.info("   Selected by fuzzer type:")
                    for fuzzer_type, count in sorted(selected_fuzzer_stats.items(), key=lambda x: x[1], reverse=True):
                        percentage = (count / len(selected_variations) * 100) if len(selected_variations) > 0 else 0
                        logger.info(f"      {fuzzer_type:20s}: {count:4d} ({percentage:5.1f}%)")

                    if program_name:
                        self._update_variation_offset(domain, program_name, new_offset)
                        logger.info(f"📍 Offset updated: {offset} -> {new_offset} (of {total_variations} total)")
                        if new_offset == 0:
                            logger.warning("⚠️ Offset wrapped to 0 - next run will start from beginning (all variations cycled)")
                    else:
                        logger.info(f"Generated {len(domain_to_fuzzers)} variations for {domain} using library")

                    return domain_to_fuzzers
                    
            except Exception as e:
                logger.error(f"Error using dnstwist library for {domain}: {e}")
                logger.info("Falling back to subprocess method")
        
        # Fallback: use subprocess method
        return self._generate_via_subprocess(domain, max_variations, fuzzers)
    
    def _generate_via_subprocess(self, domain: str, max_variations: int, fuzzers: Optional[List[str]]) -> Dict[str, List[str]]:
        """Fallback method using dnstwist binary subprocess"""
        try:
            logger.info(f"Generating variations for {domain} using dnstwist binary (fallback)")
            
            # Build dnstwist command
            cmd = ['dnstwist', '--format', 'json', domain]
            
            # Add fuzzer filters if specified
            if fuzzers:
                valid_fuzzers = [f for f in fuzzers if f in self.available_fuzzers]
                if valid_fuzzers:
                    cmd.extend(['--fuzzers', ','.join(valid_fuzzers)])
            
            # Run dnstwist
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logger.error(f"dnstwist failed: {result.stderr}")
                return {}
            
            # Parse JSON output
            variations_data = json.loads(result.stdout)
            domain_to_fuzzers = {}
            
            count = 0
            for item in variations_data:
                if count >= max_variations:
                    break
                    
                fuzzer_type = item.get('fuzzer', 'unknown')
                domain_name = item.get('domain', '')
                
                # Skip original domain
                if fuzzer_type == '*original' or domain_name == domain:
                    continue
                
                if domain_name and domain_name != domain:
                    if domain_name not in domain_to_fuzzers:
                        domain_to_fuzzers[domain_name] = []
                    
                    if fuzzer_type not in domain_to_fuzzers[domain_name]:
                        domain_to_fuzzers[domain_name].append(fuzzer_type)
                    
                    count += 1
            
            logger.info(f"Generated {len(domain_to_fuzzers)} variations for {domain} using binary")
            return domain_to_fuzzers
            
        except subprocess.TimeoutExpired:
            logger.error(f"dnstwist timeout for domain {domain}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse dnstwist output: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error generating variations for {domain}: {e}")
            return {}


class VariationCacheManager:
    """Manages Redis-based caching of tested domain variations with TTL"""

    def __init__(self, redis_url: Optional[str] = None, default_ttl: Optional[int] = None):
        """
        Initialize the variation cache manager

        Args:
            redis_url: Redis connection URL (default: redis://redis:6379/0)
            default_ttl: Default TTL in seconds for cached entries (default: 2592000 = 30 days)
        """
        # Get configuration from environment
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://redis:6379/0')
        self.default_ttl = default_ttl or int(os.getenv('TYPOSQUAT_CACHE_TTL', '2592000'))  # 30 days default
        self.cache_enabled = os.getenv('TYPOSQUAT_USE_CACHE', 'true').lower() == 'true'

        # Initialize Redis client
        self.redis_client = None
        if self.cache_enabled:
            try:
                self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                logger.info(f"✅ Redis cache initialized for typosquat variations (TTL: {self.default_ttl}s)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to connect to Redis cache: {e}. Cache will be disabled.")
                self.cache_enabled = False
                self.redis_client = None
        else:
            logger.info("Redis cache disabled by configuration")

    def _get_cache_key(self, variation_domain: str, program_name: str) -> str:
        """Generate Redis cache key for a variation (format: typosquat:tested:{program_name}:{variation_domain})"""
        return f"typosquat:tested:{program_name}:{variation_domain}"

    def mark_variation_as_tested(self, variation_domain: str, program_name: str,
                                ttl: Optional[int] = None) -> bool:
        """
        Mark a variation as tested in the cache

        Args:
            variation_domain: The variation domain that was tested
            program_name: Program name for cache segregation
            ttl: Time-to-live in seconds (default: use default_ttl)

        Returns:
            True if successfully cached, False otherwise
        """
        if not self.cache_enabled or not self.redis_client:
            return False

        try:
            cache_key = self._get_cache_key(variation_domain, program_name)
            ttl_to_use = ttl if ttl is not None else self.default_ttl

            cache_value = json.dumps({
                "tested_at": datetime.utcnow().isoformat(),
                "variation_domain": variation_domain
            })

            self.redis_client.setex(cache_key, ttl_to_use, cache_value)
            logger.debug(f"Cached tested variation: {variation_domain} (TTL: {ttl_to_use}s)")
            return True

        except Exception as e:
            logger.warning(f"Failed to cache variation {variation_domain}: {e}")
            return False

    def is_variation_tested(self, variation_domain: str, program_name: str) -> bool:
        """
        Check if a variation has been tested recently (within TTL)

        Args:
            variation_domain: The variation domain to check
            program_name: Program name for cache segregation

        Returns:
            True if variation is cached (recently tested), False otherwise
        """
        if not self.cache_enabled or not self.redis_client:
            return False

        try:
            cache_key = self._get_cache_key(variation_domain, program_name)
            return self.redis_client.exists(cache_key) > 0

        except Exception as e:
            logger.debug(f"Error checking cache for variation {variation_domain}: {e}")
            return False

    def get_tested_variations(self, program_name: str) -> set:
        """
        Get all tested variation domains for a program from cache

        Args:
            program_name: Program name for cache segregation

        Returns:
            Set of variation domains that have been tested (within TTL)
        """
        if not self.cache_enabled or not self.redis_client:
            return set()

        try:
            pattern = f"typosquat:tested:{program_name}:*"
            tested_variations = set()

            for key in self.redis_client.scan_iter(match=pattern, count=100):
                # Key format: typosquat:tested:{program_name}:{variation_domain}
                parts = key.split(":", 3)
                if len(parts) >= 4:
                    variation_domain = parts[3]
                    tested_variations.add(variation_domain)

            logger.debug(f"Found {len(tested_variations)} cached tested variations for {program_name}")
            return tested_variations

        except Exception as e:
            logger.warning(f"Error retrieving tested variations from cache: {e}")
            return set()

    def filter_untested_variations(self, variations: Dict[str, List[str]],
                                  program_name: str) -> Dict[str, List[str]]:
        """
        Filter out variations that have been tested recently (cached in Redis)

        Args:
            variations: Dict mapping variation domain to list of fuzzer types
            program_name: Program name for cache segregation

        Returns:
            Filtered dict with only untested variations
        """
        if not self.cache_enabled or not self.redis_client:
            return variations

        try:
            tested_variations = self.get_tested_variations(program_name)

            if not tested_variations:
                logger.debug("No cached tested variations found")
                return variations

            untested_variations = {
                domain: fuzzers
                for domain, fuzzers in variations.items()
                if domain not in tested_variations
            }

            filtered_count = len(variations) - len(untested_variations)
            if filtered_count > 0:
                logger.info(f"🔍 Redis cache: Filtered out {filtered_count} recently tested variations")
                logger.debug(f"Remaining untested variations: {len(untested_variations)}")

            return untested_variations

        except Exception as e:
            logger.warning(f"Error filtering variations with cache: {e}")
            return variations

    def mark_variations_as_tested(self, variations: List[str], program_name: str,
                                 ttl: Optional[int] = None) -> int:
        """
        Mark multiple variations as tested in batch

        Args:
            variations: List of variation domains to mark as tested
            program_name: Program name for cache segregation
            ttl: Time-to-live in seconds (default: use default_ttl)

        Returns:
            Number of variations successfully cached
        """
        if not self.cache_enabled or not self.redis_client:
            return 0

        cached_count = 0
        for variation in variations:
            if self.mark_variation_as_tested(variation, program_name, ttl):
                cached_count += 1

        if cached_count > 0:
            logger.info(f"✅ Cached {cached_count} tested variations")

        return cached_count

    def cleanup(self):
        """Clean up Redis connection"""
        if self.redis_client:
            try:
                self.redis_client.close()
                logger.debug("Redis cache connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")


class ApiClient:
    """API communication layer for typosquat detection"""
    
    def __init__(self, api_url: Optional[str] = None, internal_api_key: Optional[str] = None):
        # Get API configuration from environment variables
        self.api_url = api_url or os.getenv('API_URL', 'http://api:8000')
        self.internal_api_key = internal_api_key or os.getenv('INTERNAL_SERVICE_API_KEY', '')
        
        # Remove trailing slash from API URL
        self.api_url = self.api_url.rstrip('/')
        
        # Set up headers for API requests
        self.headers = {}
        if self.internal_api_key:
            self.headers['Authorization'] = f'Bearer {self.internal_api_key}'
            self.headers['Content-Type'] = 'application/json'
            logger.info(f"Initialized API client with internal API key (length: {len(self.internal_api_key)})")
        else:
            logger.warning("No internal API key provided, API calls may fail")
    
    def get_already_tested_domains(self, original_domain: Optional[str] = None, program_name: str = "default") -> set:
        """Get set of domains that have already been tested via API call (original_domain param ignored - no longer filterable)"""
        logger.debug(f"Getting already tested domains for program_name: {program_name}")
        tested_domains = set()
        
        if not self.api_url:
            logger.warning("Data API URL not provided, cannot check already tested domains")
            return tested_domains
        
        try:
            # Prepare the search request body
            search_body = {
                "hide_false_positives": False,
                "program": program_name,
                "sort_by": "timestamp",
                "sort_dir": "desc",
                "page": 1,
                "page_size": 100  # Use larger page size to get more results
            }
            
            logger.debug("Querying typosquat results")
            
            logger.debug(f"Making API request to: {self.api_url}/findings/typosquat/search")
            
            response = requests.post(
                f"{self.api_url}/findings/typosquat/search",
                json=search_body,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "success":
                    items = data.get("items", [])
                    pagination = data.get("pagination", {})
                    
                    logger.debug(f"API returned {len(items)} items from page {pagination.get('current_page', 1)}")
                    logger.debug(f"Total items available: {pagination.get('total_items', 0)}")
                    
                    # Extract domains from the response
                    for item in items:
                        typo_domain = item.get("typo_domain")
                        if typo_domain:
                            tested_domains.add(typo_domain)
                    
                    logger.debug(f"Found {len(tested_domains)} unique tested domains from API")
                    
                    # If there are more pages and we want to get all results, we could paginate
                    # For now, we'll just use the first page to avoid excessive API calls
                    if pagination.get("has_next", False):
                        logger.info(f"More pages available ({pagination.get('total_pages', 1)} total), using first page only")
                else:
                    logger.warning(f"API returned error status: {data.get('status')}")
            else:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Error retrieving already tested domains from API: {e}")
        
        return tested_domains
    
    def get_program_config(self, program_name: str) -> Dict[str, Any]:
        """Get program configuration via API call"""
        if not self.api_url:
            logger.debug("Data API URL not provided, cannot fetch program configuration")
            return {}
        
        try:
            logger.debug(f"Making API request to: {self.api_url}/programs/{program_name}")
            
            response = requests.get(
                f"{self.api_url}/programs/{program_name}",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                program_config = response.json()
                logger.debug(f"Successfully retrieved program configuration for {program_name}")
                return program_config
            elif response.status_code == 404:
                logger.warning(f"Program configuration not found for {program_name}")
                return {}
            else:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Error retrieving program configuration for {program_name} from API: {e}")
            return {}
    
    def check_domain_filtering(self, domains: List[str], program_name: str) -> Dict[str, Any]:
        """Pre-flight filter check against the API.

        Returns dict with keys: allowed (list), filtered (list),
        filtering_enabled (bool), summary (dict).
        Falls back to allowing all domains on error.
        """
        fallback = {
            "filtering_enabled": False,
            "allowed": list(domains),
            "filtered": [],
            "summary": {"total": len(domains), "allowed": len(domains), "filtered": 0},
        }
        if not self.api_url or not domains:
            return fallback

        try:
            response = requests.post(
                f"{self.api_url}/findings/typosquat/check-filter",
                json={"program_name": program_name, "domains": list(domains)},
                headers=self.headers,
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"Pre-flight filter: {data.get('summary', {}).get('allowed', 0)} allowed, "
                    f"{data.get('summary', {}).get('filtered', 0)} filtered out of {len(domains)} domains"
                )
                return data
            else:
                logger.warning(f"Filter check failed ({response.status_code}), allowing all domains")
                return fallback
        except Exception as e:
            logger.warning(f"Filter check error ({e}), allowing all domains")
            return fallback

    def cleanup(self):
        """Clean up method - no longer needed for API client"""
        logger.debug("API client cleanup - no resources to clean up")


class ScreenshotProcessor:
    """Handles screenshot processing and API uploads"""
    
    def __init__(self):
        self.program_name = os.getenv('PROGRAM_NAME', 'default')
    
    async def upload_screenshot(self, session: aiohttp.ClientSession, screenshot_path: str, url: str, headers: Dict[str, str], api_url: str, extracted_text: Optional[str] = None):
        """Upload a screenshot to the typosquat-screenshot endpoint"""
        logger.info(f"🔄 Starting screenshot upload for {url} -> {screenshot_path}")

        # Read the screenshot file
        try:
            with open(screenshot_path, 'rb') as f:
                screenshot_data = f.read()
            logger.debug(f"Successfully read screenshot file: {len(screenshot_data)} bytes")
        except Exception as e:
            logger.error(f"Failed to read screenshot file {screenshot_path}: {e}")
            raise

        # Prepare form data for file upload
        try:
            form_data = aiohttp.FormData()
            form_data.add_field('file', screenshot_data, filename=os.path.basename(screenshot_path), content_type='image/png')
            form_data.add_field('program_name', self.program_name)
            form_data.add_field('url', url)
            form_data.add_field('workflow_id', os.getenv('WORKFLOW_ID', 'unknown'))
            form_data.add_field('step_name', 'typosquat_detection')
            if extracted_text:
                form_data.add_field('extracted_text', extracted_text)
            logger.debug("Form data prepared successfully")
        except Exception as e:
            logger.error(f"Failed to prepare form data: {e}")
            raise

        # Upload screenshot
        async with session.post(
            f"{api_url}/findings/typosquat-screenshot",
            data=form_data,
            headers={"Authorization": headers.get("Authorization", "")},
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            if response.status == 200:
                result = await response.json()
                logger.info(f"Screenshot uploaded successfully for {url}: {result.get('file_id', 'unknown')}")
                
                # Clean up the screenshot file after successful upload
                try:
                    os.unlink(screenshot_path)
                    logger.debug(f"Cleaned up screenshot file: {screenshot_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up screenshot file {screenshot_path}: {e}")
                    
            else:
                error_text = await response.text()
                logger.warning(f"Failed to upload screenshot for {url}: {response.status} - {error_text}")
                raise Exception(f"Screenshot upload failed: {response.status} - {error_text}")
    
    async def process_and_upload_screenshots(self, output_data: Any, context: Optional[Dict[str, Any]] = None):
        """Process base64-encoded tar.gz screenshot data and upload individual screenshots to API"""
        task_id = context.get('task_id', 'unknown') if context else 'unknown'
        logger.info(f"Processing screenshots for task {task_id}")

        try:
            # Handle different output formats
            if isinstance(output_data, str):
                base64_data = output_data
            elif isinstance(output_data, dict) and 'output' in output_data:
                base64_data = output_data['output']
            else:
                logger.error(f"Unexpected screenshot output format for task {task_id}: {type(output_data)}")
                return

            # Check if we have valid base64 data
            if not base64_data or len(base64_data.strip()) == 0:
                logger.warning(f"Empty screenshot data for task {task_id}")
                return

            # Check if it's an error response (JSON)
            try:
                # Try to decode as JSON first
                json_data = base64.b64decode(base64_data).decode('utf-8')
                error_info = json.loads(json_data)
                if 'error' in error_info:
                    logger.warning(f"Screenshot task {task_id} failed: {error_info.get('error', 'Unknown error')}")
                    return
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Not JSON, proceed with tar.gz extraction
                pass

            # Decode base64 data
            try:
                compressed_data = base64.b64decode(base64_data)
                logger.info(f"Decoded base64 data for task {task_id}, size: {len(compressed_data)} bytes")
            except Exception as e:
                logger.error(f"Failed to decode base64 data for task {task_id}: {e}")
                return

            # Extract tar.gz archive
            with tempfile.TemporaryDirectory() as temp_dir:
                tar_path = os.path.join(temp_dir, 'screenshots.tar.gz')

                # Write compressed data to file
                with open(tar_path, 'wb') as f:
                    f.write(compressed_data)

                # Extract archive
                try:
                    with tarfile.open(tar_path, 'r:gz') as tar:
                        tar.extractall(temp_dir)
                        extracted_files = tar.getnames()
                        logger.info(f"Extracted {len(extracted_files)} files for task {task_id}: {extracted_files}")
                except Exception as e:
                    logger.error(f"Failed to extract tar.gz archive for task {task_id}: {e}")
                    return

                # Find PNG files
                png_files = []
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.lower().endswith('.png'):
                            png_files.append(os.path.join(root, file))

                if not png_files:
                    logger.warning(f"No PNG files found in extracted archive for task {task_id}")
                    return

                logger.info(f"Found {len(png_files)} PNG files for task {task_id}")

                # Get API configuration
                api_url = os.getenv('API_URL', 'http://api:8000')
                internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
                headers = {}
                if internal_api_key:
                    headers['Authorization'] = f'Bearer {internal_api_key}'

                # Get original URLs from context
                original_urls = context.get('original_urls', []) if context else []
                # Build normalized URL set for matching (filename order is non-deterministic)
                original_urls_normalized = {
                    normalize_url_for_storage(u): u for u in original_urls
                } if original_urls else {}

                # Upload each screenshot - match by decoded filename, NOT by index
                uploaded_count = 0
                async with aiohttp.ClientSession() as session:
                    for i, png_file in enumerate(png_files):
                        try:
                            url = None
                            filename = os.path.basename(png_file)
                            # Decode gowitness filename to URL for correct screenshot-to-URL mapping
                            decoded_url = _decode_gowitness_filename_to_url(filename)
                            if decoded_url and original_urls_normalized:
                                normalized_decoded = normalize_url_for_storage(decoded_url)
                                url = original_urls_normalized.get(
                                    normalized_decoded,
                                    original_urls_normalized.get(decoded_url)
                                )
                            if not url and decoded_url:
                                url = decoded_url
                            if not url:
                                # Fallback: index-based (may cause mismatches - log warning)
                                url = original_urls[i] if i < len(original_urls) else f"http://{filename}"
                                logger.warning(
                                    f"Screenshot {filename}: could not decode/match URL, using index fallback "
                                    f"(may cause wrong screenshot-URL association)"
                                )

                            logger.info(f"Uploading screenshot {i+1}/{len(png_files)} for task {task_id}: {filename} -> {url}")

                            # Extract text from matching JSONL (same encoded filename)
                            jsonl_path = os.path.join(os.path.dirname(png_file), filename[:-4] + '.jsonl')
                            extracted_text = None
                            if os.path.exists(jsonl_path):
                                extracted_text = extract_text_from_gowitness_jsonl(jsonl_path, url)
                            # OCR fallback when HTML yields no text
                            if not extracted_text or not extracted_text.strip():
                                extracted_text = extract_text_from_image_ocr(png_file)

                            await self.upload_screenshot(session, png_file, url, headers, api_url, extracted_text=extracted_text)
                            uploaded_count += 1

                        except Exception as e:
                            logger.error(f"Failed to upload screenshot {png_file} for task {task_id}: {e}")

                logger.info(f"Successfully uploaded {uploaded_count}/{len(png_files)} screenshots for task {task_id}")

        except Exception as e:
            logger.error(f"Error processing screenshots for task {task_id}: {e}")
            logger.exception("Full traceback:")


class SubdomainWorkflowOrchestrator:
    """Manages multi-phase subdomain discovery workflows"""
    
    def __init__(self):
        self.phase2_task_ids = set()  # Track Phase 2 (SubdomainFinder) task IDs
        self.phase3_task_ids = set()  # Track Phase 3 (subdomain analysis) task IDs
        self.phase2_processed_for_phase3 = set()  # Track which Phase 2 tasks have already triggered Phase 3
        self.apex_to_original_mapping = {}  # Map apex domains to their original domains for Phase 3
        self.spawned_job_contexts = {}  # Store contexts for spawned jobs
    
    def extract_apex_domains(self, findings) -> List[str]:
        """Extract unique apex domains from typosquat findings"""
        apex_domains = set()
        
        for finding in findings:
            typo_domain = finding.typo_domain
            if typo_domain:
                # Extract apex domain (remove subdomains)
                parts = typo_domain.split('.')
                if len(parts) >= 2:
                    apex_domain = '.'.join(parts[-2:])
                    apex_domains.add(apex_domain)
        
        unique_apex_domains = list(apex_domains)
        logger.info(f"Extracted {len(unique_apex_domains)} unique apex domains from {len(findings)} findings")
        
        return unique_apex_domains
    
    def extract_apex_domains_with_original(self, findings) -> Dict[str, str]:
        """Extract unique apex domains - returns empty dict as original_domain is no longer stored on findings"""
        return {}
    
    def is_phase2_task(self, task_id: str) -> bool:
        """Check if a task ID belongs to Phase 2 (SubdomainFinder)"""
        return task_id in self.phase2_task_ids
    
    def is_phase3_task(self, task_id: str) -> bool:
        """Check if a task ID belongs to Phase 3 (subdomain analysis)"""
        return task_id in self.phase3_task_ids
    
    async def start_phase3_workflow_async(self, subdomains: List[str], program_name: str):
        """Start a new workflow execution for Phase 3 analysis of subdomains as potential typosquats"""
        try:
            logger.info(f"🚀 Phase 3: Starting new workflow for {len(subdomains)} subdomains")
            
            # Get workflow API URL from environment
            api_url = os.getenv('API_URL', 'http://api:8000')
            if not api_url.endswith('/'):
                api_url += '/'
            
            # Get current workflow name for Phase 3 naming
            current_workflow_name = os.getenv('WORKFLOW_NAME', 'typosquat_detection')
            phase3_workflow_name = f"{current_workflow_name}_phase3_subdomains"
            
            # Create workflow definition for Phase 3
            workflow_definition = {
                "workflow_name": phase3_workflow_name,
                "program_name": program_name,
                "description": f"Phase 3: Analyze {len(subdomains)} subdomains as potential typosquats",
                "steps": [
                    {
                        "name": "phase3_analysis",
                        "tasks": [
                            {
                                "name": "typosquat_detection",
                                "force": True,
                                "params": {
                                    "include_subdomains": False,  # No further subdomain discovery
                                    "analyze_input_as_variations": True  # Treat subdomains as typosquat variations
                                },
                                "task_type": "typosquat_detection",
                                "input_mapping": {
                                    "domains": "inputs.subdomains_input"
                                }
                            }
                        ]
                    }
                ],
                "variables": {},
                "inputs": {
                    "subdomains_input": {
                        "type": "direct",
                        "values": subdomains,
                        "value_type": "domains"
                    }
                },
                "workflow_definition_id": ""
            }
            
            # Send POST request to start new workflow
            url = f"{api_url}workflows/run"
            headers = {
                'Content-Type': 'application/json'
            }
            
            # Add authorization if available
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
            if internal_api_key:
                headers['Authorization'] = f'Bearer {internal_api_key}'
            
            logger.info(f"📡 Sending Phase 3 workflow request to: {url}")
            logger.info(f"📋 Workflow will analyze subdomains: {subdomains}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=workflow_definition, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        result = await response.json()
                        workflow_id = result.get('workflow_id', 'unknown')
                        execution_id = result.get('execution_id', 'unknown')
                        
                        logger.info("✅ Phase 3: Successfully started workflow")
                        logger.info(f"📋 Workflow ID: {workflow_id}")
                        logger.info(f"📋 Execution ID: {execution_id}")
                        logger.info(f"🔍 Phase 3 will analyze {len(subdomains)} subdomains as potential typosquats")
                        
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Phase 3: Failed to start workflow: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.error(f"Error starting Phase 3 workflow: {e}")
            logger.exception("Full traceback:")


class TyposquatAnalyzer:
    """Core typosquat detection and analysis logic"""
    
    def __init__(self):
        self.program_name = os.getenv('PROGRAM_NAME', 'default')
        self._protected_domains_cache: Optional[List[str]] = None
        self._protected_domains_cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 300  # 5 minutes cache TTL
    
    def _get_program_protected_domains(self, program_name: str) -> List[str]:
        """
        Fetch protected domains for a program from the API.
        Uses caching to avoid repeated API calls.
        
        Returns:
            List of protected domain strings
        """
        # Check cache
        if self._protected_domains_cache is not None and self._protected_domains_cache_timestamp:
            elapsed = (datetime.utcnow() - self._protected_domains_cache_timestamp).total_seconds()
            if elapsed < self._cache_ttl:
                return self._protected_domains_cache
        
        # Fetch from API
        try:
            api_url = os.getenv("API_URL", "http://data-api:8000")
            url = f"{api_url}/programs/{program_name}"
            
            headers = {}
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
            if internal_api_key:
                headers['Authorization'] = f'Bearer {internal_api_key}'
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                protected_domains = data.get("protected_domains", [])
                self._protected_domains_cache = protected_domains
                self._protected_domains_cache_timestamp = datetime.utcnow()
                logger.debug(f"Fetched {len(protected_domains)} protected domains for program {program_name}")
                return protected_domains
            else:
                logger.warning(f"Failed to fetch protected domains for program {program_name}: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching protected domains for program {program_name}: {e}")
            return []
    
    def detect_parked_domain(
        self,
        nameservers: List[str],
        mx_servers: List[str],
        a_records: List[str],
        http_title: Optional[str],
        http_body: Optional[str],
        domain: str
    ) -> Tuple[bool, Dict[str, Any], int]:
        """
        Detect if a domain is parked based on multiple indicators.
        
        Args:
            nameservers: List of nameserver domains
            mx_servers: List of MX server records
            a_records: List of A record IP addresses
            http_title: HTTP page title
            http_body: HTTP page body preview
            domain: Domain name being checked
        
        Returns:
            (is_parked: bool, reasons: Dict[str, Any], indicator_score: int)
            indicator_score is 0-100 based on detected parking indicators
        """
        reasons: Dict[str, Any] = {
            "nameserver_matches": [],
            "mx_matches": [],
            "a_matches": [],
            "title_keywords": [],
            "body_keywords": [],
            "indicators": []
        }
        is_parked = False
        
        # Known parking service nameservers (derived from multiple providers in
        # parking_services.json, simplified as domain fragments)
        parking_nameservers = [
            # ParkingCrew & related
            "parkingcrew.com",
            "parkingcrew.net",
            "fastpark.net",
            "parkingspa.com",
            "ibspark.com",
            # dan.com
            "dan.com",
            "undeveloped.com",
            "park.do",
            # GoDaddy CashParking / NameFind / SmartName
            "cashparking.com",
            "smartname.com",
            "namefind.com",
            # Sedo
            "sedoparking.com",
            # Uniregistry
            "uniregistrymarket.link",
            "uniregistry-dns.com",
            # Bodis
            "bodis.com",
            # Namecheap (WHOIS / parking related)
            "namecheap.com",
            "failed-whois-verification.namecheap.com",
            "verify-contact-details.namecheap.com",
            # Above
            "above.com",
            "abovedomains.com",
            # DomainSponsor / RookMedia
            "dsredirection.com",
            "dsredirects.com",
            "rookdns.com",
            "dnsspark.com",
            # The Parking Place
            "pql.net",
            "tppns.com",
            # Sav
            "sav.com",
            # Various parking-focused namespaces
            "ztomy.com",
            "cnomy.com",
            "malkm.com",
            "parking-page.net",
            "searchreinvented.com",
            "nsresolution.com",
            "searchmagnified.com",
            # Generic parking-style hostnames
            "parklogic.com",
            "parked.com",
            "parkeddomain.com",
            "domainparking.com",
            "parkingdomain.com",
        ]
        
        # Parking-related keywords for title and body
        parking_title_keywords = [
            "parked",
            "domain parking",
            "this domain is for sale",
            "domain for sale",
            "buy this domain",
            "domain parking page",
            "parked domain",
            "domain is parked",
            "this domain name is parked"
        ]
        
        parking_body_keywords = [
            "parked domain",
            "domain for sale",
            "buy this domain",
            "domain parking",
            "this domain is parked",
            "parked by",
            "domain parking service",
            "parking page",
            "this domain name is parked"
        ]

        # Known MX hosts used by parking services
        parking_mx_hosts = [
            "park-mx.above.com",
        ]
        parking_mx_keywords = [
            "park-mx",
            "domainparking",
            "parkingmail",
            "parking-mx",
            "mxpark",
        ]

        # Check nameservers
        if nameservers:
            for ns in nameservers:
                ns_lower = ns.lower()
                # Check for exact matches
                for parking_ns in parking_nameservers:
                    if parking_ns in ns_lower:
                        reasons["nameserver_matches"].append(ns)
                        is_parked = True
                        break
                
                # Check for pattern matches (parking, parked in nameserver)
                if "parking" in ns_lower or "parked" in ns_lower:
                    if ns not in reasons["nameserver_matches"]:
                        reasons["nameserver_matches"].append(ns)
                        is_parked = True
        
        # Check MX servers
        if mx_servers:
            normalized_mx_hosts: List[str] = []
            for raw_mx in mx_servers:
                try:
                    # MX records often look like: \"10 mail.example.com.\"
                    parts = str(raw_mx).split()
                    host = parts[-1] if parts else str(raw_mx)
                    host = host.rstrip(".").lower()
                    normalized_mx_hosts.append(host)
                except Exception:
                    continue

            for host in normalized_mx_hosts:
                # Exact host matches
                for parking_mx in parking_mx_hosts:
                    if host == parking_mx:
                        reasons["mx_matches"].append(host)
                        is_parked = True
                        break

                # Keyword-based matches
                for keyword in parking_mx_keywords:
                    if keyword in host:
                        if host not in reasons["mx_matches"]:
                            reasons["mx_matches"].append(host)
                            is_parked = True

        # Check A records (IP addresses) against known parking IP ranges
        if a_records:
            for ip_str in a_records:
                try:
                    ip_obj = ipaddress.ip_address(ip_str)
                except Exception:
                    continue

                for net in PARKING_A_NETWORKS:
                    if ip_obj in net:
                        reasons["a_matches"].append(f"{ip_str} in {net.with_prefixlen}")
                        is_parked = True
                        break

        # Check HTTP title
        if http_title:
            title_lower = http_title.lower()
            for keyword in parking_title_keywords:
                if keyword in title_lower:
                    reasons["title_keywords"].append(keyword)
                    is_parked = True
        
        # Check HTTP body
        if http_body:
            body_lower = http_body.lower()
            for keyword in parking_body_keywords:
                if keyword in body_lower:
                    reasons["body_keywords"].append(keyword)
                    is_parked = True
            
            # Check for minimal content (very short body might indicate parking)
            if len(http_body.strip()) < 200:
                reasons["indicators"].append("minimal_content")
        
        # Clean up reasons dict - remove empty lists
        reasons = {k: v for k, v in reasons.items() if v}
        
        # Calculate indicator-based score (0-100)
        indicator_score = 0
        if reasons.get("a_matches"):
            indicator_score += 40  # A record matches are strong indicators
        if reasons.get("mx_matches"):
            indicator_score += 30  # MX matches are strong indicators
        if reasons.get("nameserver_matches"):
            indicator_score += 25  # Nameserver matches are strong indicators
        if reasons.get("body_keywords"):
            indicator_score += 15  # Body keywords are moderate indicators
        if reasons.get("title_keywords"):
            indicator_score += 10  # Title keywords are moderate indicators
        if reasons.get("indicators"):
            # Additional indicators like minimal_content
            indicator_score += 5
        
        # Cap at 100
        indicator_score = min(100, indicator_score)
        
        if is_parked:
            logger.debug(f"Detected parked domain: {domain}, reasons: {reasons}, indicator_score: {indicator_score}")
        
        return is_parked, reasons, indicator_score
    
    def parse_worker_output(self, output: str, params: Optional[Dict[Any, Any]] = None) -> tuple:
        """Parse typosquat detection JSON output into TyposquatDomain findings"""
        findings = []
        typosquat_urls = []
        logger.debug(f"Parsing worker output: {output}")
        # Handle both WorkerJobManager dict format and legacy string format
        if isinstance(output, dict):
            if 'output' in output:
                actual_output = output['output']
            else:
                return {}, False, [], []
        else:
            actual_output = output

        # Check if this is a risk recalculation operation result
        if isinstance(actual_output, str) and (actual_output.strip().startswith("Risk recalculation completed") or actual_output.strip().startswith("Error in risk recalculation")):
            logger.info(f"Risk recalculation result: {actual_output.strip()}")
            return {}, False, [], []

        # Get program name from environment variable
        program_name = os.getenv('PROGRAM_NAME', '')

        # Source: explicit param takes precedence (e.g. "ct_monitoring"), else derive from detection mode
        explicit_source = params.get("source") if params else None
        if explicit_source is not None and explicit_source != "" and str(explicit_source).lower() != "null":
            source = str(explicit_source)
        elif params and params.get("analyze_input_as_variations"):
            source = "domain_analysis"
        else:
            source = "variation_detection"

        # Track if this chunk has subdomain discovery enabled
        include_subdomains = params.get("include_subdomains", False) if params else False
        subdomain_discovery_enabled = include_subdomains
        found_subdomain_discovery_marker = False
        subdomains_for_phase3 = []

        # Handle both string and parsed dict outputs
        if isinstance(actual_output, str):
            lines_to_process = actual_output.splitlines()
        elif isinstance(actual_output, dict):
            lines_to_process = [json.dumps(actual_output)]
        else:
            logger.error(f"[PARSE_OUTPUT] Unexpected output type: {type(actual_output)}")
            return {}, False, [], []

        for line in lines_to_process:
            if not line.strip() or line.startswith('stderr:'):
                continue
                
            try:
                # Parse JSON output from the worker
                result = json.loads(line)
                
                # Check if this result indicates subdomain discovery should be enabled
                if result.get("_subdomain_discovery_enabled"):
                    found_subdomain_discovery_marker = True
                    logger.debug(f"Found _subdomain_discovery_enabled marker in result for {result.get('typo_domain', 'unknown')}")
                
                # Extract subdomains from worker output (when worker ran subfinder inline)
                if "subdomains" in result and isinstance(result["subdomains"], list):
                    subdomains_for_phase3.extend(result["subdomains"])
                
                # Get domain info without calculating risk score (API will handle this)
                domain_info = result.get("info", {})
                
                # Extract typosquat URLs for parked domain detection
                typosquat_urls_for_detection = result.get("typosquat_urls", [])
                http_title = None
                http_body = None
                if typosquat_urls_for_detection and len(typosquat_urls_for_detection) > 0:
                    first_url = typosquat_urls_for_detection[0]
                    http_title = first_url.get("title")
                    http_body = first_url.get("body_preview")
                
                # Extract nameservers and MX/A records for parked domain detection
                nameservers = domain_info.get("dns_ns", [])
                mx_servers = domain_info.get("dns_mx", [])
                a_records = domain_info.get("dns_a", [])
                
                # Detect parked domain
                is_parked, detection_reasons, indicator_score = self.detect_parked_domain(
                    nameservers=nameservers,
                    mx_servers=mx_servers,
                    a_records=a_records,
                    http_title=http_title,
                    http_body=http_body,
                    domain=result.get("typo_domain", "")
                )
                
                # Calculate parked confidence based purely on indicator score
                # Protected domain similarity is now calculated API-side and stored separately
                typo_domain = result.get("typo_domain", "")
                parked_confidence = None
                if is_parked:
                    parked_confidence = int(round(min(100, indicator_score)))
                    logger.debug(f"Parked domain confidence for {typo_domain}: {parked_confidence}% (indicator score only)")
                
                # Build TyposquatDomain parameters
                typosquat_params = {
                    "typo_domain": result.get("typo_domain", ""),
                    "fuzzers": result.get("fuzzers", []),
                    "timestamp": datetime.utcnow(),
                    "program_name": program_name,
                    # Map domain information from worker output
                    "domain_registered": domain_info.get("registered"),
                    "dns_a_records": domain_info.get("dns_a", []),
                    "dns_mx_records": domain_info.get("dns_mx", []),
                    "dns_ns_records": domain_info.get("dns_ns", []),
                    "is_wildcard": domain_info.get("is_wildcard"),
                    "wildcard_types": domain_info.get("wildcard_types", []),
                    # Map WHOIS information
                    "whois_registrar": domain_info.get("whois", {}).get("registrar"),
                    "whois_creation_date": domain_info.get("whois", {}).get("creation_date"),
                    "whois_expiration_date": domain_info.get("whois", {}).get("expiration_date"),
                    "whois_registrant_name": domain_info.get("whois", {}).get("registrant_name"),
                    "whois_registrant_country": domain_info.get("whois", {}).get("registrant_country"),
                    "whois_admin_email": domain_info.get("whois", {}).get("admin_email"),
                    # Map GeoIP information
                    "geoip_country": domain_info.get("geoip", {}).get("country"),
                    "geoip_city": domain_info.get("geoip", {}).get("city"),
                    "geoip_organization": domain_info.get("geoip", {}).get("org"),
                    # Include source if provided in params
                    "source": source,
                    # Parked domain detection
                    "is_parked": is_parked if is_parked else None,
                    "parked_detection_timestamp": datetime.utcnow() if is_parked else None,
                    "parked_detection_reasons": detection_reasons if is_parked else None,
                    "parked_confidence": parked_confidence,
                }
                
                # Only include threatstream_data if it exists in the result to avoid overwriting existing data
                if "threatstream_data" in result and result.get("threatstream_data") is not None:
                    typosquat_params["threatstream_data"] = result.get("threatstream_data")
                
                typosquat_finding = TyposquatDomain(**typosquat_params)
                findings.append(typosquat_finding)
                
                # Extract typosquat URLs from the new format
                if "typosquat_urls" in result and isinstance(result["typosquat_urls"], list):
                    for url_data in result["typosquat_urls"]:
                        # Add program_name to each URL for proper storage
                        url_data["program_name"] = program_name
                        typosquat_urls.append(url_data)
                        logger.debug(f"Extracted typosquat URL: {url_data.get('url', 'unknown')}")
                
            except json.JSONDecodeError:
                logger.debug(f"Skipping non-JSON line: {line[:100]}...")
                continue
            except Exception as e:
                logger.error(f"Error processing typosquat finding: {str(e)}")
                continue
        
        logger.info(f"Parsed {len(findings)} typosquat findings from {program_name}")
        logger.info(f"Extracted {len(typosquat_urls)} typosquat URLs for storage")
        
        # Update subdomain discovery flag based on actual results
        subdomain_discovery_enabled = subdomain_discovery_enabled or found_subdomain_discovery_marker
        
        # Deduplicate subdomains for Phase 3
        subdomains_for_phase3 = list(dict.fromkeys(subdomains_for_phase3))
        
        # Convert TyposquatDomain objects to dictionaries for API consumption
        findings_dicts = []
        for finding in findings:
            # Helper function to safely convert datetime to ISO format
            def safe_isoformat(dt_value):
                """Safely convert datetime to ISO format, handling both datetime objects and strings"""
                if dt_value is None:
                    return None
                if isinstance(dt_value, datetime):
                    return dt_value.isoformat()
                if isinstance(dt_value, str):
                    try:
                        # Try to parse string as datetime
                        parsed_dt = datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
                        return parsed_dt.isoformat()
                    except (ValueError, AttributeError):
                        # If parsing fails, return the string as-is
                        return dt_value
                return str(dt_value)

            # Convert TyposquatDomain object to dictionary
            finding_dict = {
                "typo_domain": finding.typo_domain,
                "fuzzers": finding.fuzzers,
                "timestamp": safe_isoformat(finding.timestamp),
                "program_name": finding.program_name,
                "domain_registered": finding.domain_registered,
                "dns_a_records": finding.dns_a_records or [],
                "dns_mx_records": finding.dns_mx_records or [],
                "dns_ns_records": finding.dns_ns_records or [],
                "is_wildcard": finding.is_wildcard,
                "wildcard_types": finding.wildcard_types or [],
                "whois_registrar": finding.whois_registrar,
                "whois_creation_date": safe_isoformat(finding.whois_creation_date),
                "whois_expiration_date": safe_isoformat(finding.whois_expiration_date),
                "whois_registrant_name": finding.whois_registrant_name,
                "whois_registrant_country": finding.whois_registrant_country,
                "whois_admin_email": finding.whois_admin_email,
                "geoip_country": finding.geoip_country,
                "geoip_city": finding.geoip_city,
                "geoip_organization": finding.geoip_organization,
                "threatstream_data": finding.threatstream_data,
                "status": finding.status,
                "assigned_to": finding.assigned_to,
                "source": finding.source,
                "is_parked": finding.is_parked,
                "parked_detection_timestamp": safe_isoformat(finding.parked_detection_timestamp),
                "parked_detection_reasons": finding.parked_detection_reasons,
                "parked_confidence": finding.parked_confidence
            }
            findings_dicts.append(finding_dict)

        # Build the result in the format expected by the API
        result = {
            FindingType.TYPOSQUAT_DOMAIN: findings_dicts,
            FindingType.TYPOSQUAT_URL: typosquat_urls
        }

        return result, subdomain_discovery_enabled, findings, subdomains_for_phase3
    
    def store_typosquat_urls(self, typosquat_urls: List[Dict[str, Any]]):
        """Store typosquat URLs to the API"""
        try:
            # Get API configuration
            api_url = os.getenv('API_URL', 'http://api:8000')
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')

            headers = {}
            if internal_api_key:
                headers['Authorization'] = f'Bearer {internal_api_key}'

            logger.info(f"Storing {len(typosquat_urls)} typosquat URLs to API")

            # Send URLs to the API
            response = requests.post(
                f"{api_url}/findings/typosquat-url",
                json={"urls": typosquat_urls},
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                logger.info("✅ Successfully stored typosquat URLs")
            else:
                logger.error(f"Failed to store typosquat URLs: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"Error storing typosquat URLs: {e}")
            raise