"""
Domain Variation Generator using dnstwist.

Pre-generates all possible typosquat variations of protected domains
for fast O(1) lookup when matching incoming certificates.

This uses the same dnstwist library as the runner for consistency.
"""

import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

from domain_labels import hostname_without_public_suffix

logger = logging.getLogger(__name__)

# Available dnstwist fuzzers
AVAILABLE_FUZZERS = [
    'addition', 'bitsquatting', 'homoglyph', 'hyphenation',
    'insertion', 'omission', 'plural', 'repetition',
    'replacement', 'subdomain', 'transposition', 'various',
    'vowel-swap'
]

# High-priority fuzzers most likely used in attacks
PRIORITY_FUZZERS = [
    'homoglyph',      # Unicode lookalikes (highest threat)
    'bitsquatting',   # Single bit errors in DNS
    'replacement',    # Adjacent key replacements
    'insertion',      # Extra character insertion
    'omission',       # Missing character
    'transposition',  # Swapped adjacent characters
    'vowel-swap',     # Vowel substitutions
]


@dataclass
class VariationInfo:
    """Information about a domain variation (registrable hostname label, TLD-agnostic)."""
    variation: str
    protected_domain: str
    fuzzer: str
    program_name: str


class DnstwistVariationGenerator:
    """
    Generates domain variations using dnstwist library.
    
    Pre-computes all variations for protected domains and provides
    fast O(1) TLD-agnostic lookup (exact registrable hostname label match).
    """
    
    def __init__(self, fuzzers: Optional[List[str]] = None):
        """
        Initialize the variation generator.
        
        Args:
            fuzzers: List of dnstwist fuzzers to use (default: all)
        """
        self.fuzzers = fuzzers or AVAILABLE_FUZZERS
        
        # Validate fuzzers
        invalid = [f for f in self.fuzzers if f not in AVAILABLE_FUZZERS]
        if invalid:
            logger.warning(f"Invalid fuzzers ignored: {invalid}")
            self.fuzzers = [f for f in self.fuzzers if f in AVAILABLE_FUZZERS]
        
        # Storage for variations (registrable hostname label -> VariationInfo)
        self._variations: Dict[str, VariationInfo] = {}
        
        # Protected domains by program
        # program_name -> set of protected domains
        self._protected_domains: Dict[str, Set[str]] = {}

        # Flat set of all protected FQDNs across programs (O(1) lookups)
        self._protected_fqdn_set: Set[str] = set()
        
        # Statistics
        self._stats = {
            "total_variations": 0,
            "variations_by_fuzzer": {},
            "protected_domains": 0,
            "programs": 0
        }
        
        # Try to import dnstwist
        try:
            from dnstwist import Fuzzer
            self.Fuzzer = Fuzzer
            self.dnstwist_available = True
            logger.info(f"dnstwist library available, using fuzzers: {self.fuzzers}")
        except ImportError:
            logger.error("dnstwist library not available - variation generation disabled!")
            self.Fuzzer = None
            self.dnstwist_available = False
    
    def generate_variations(
        self, 
        domain: str, 
        program_name: str,
        max_variations: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        Generate all variations for a protected domain.
        
        Args:
            domain: Protected domain (e.g., "microsoft.com")
            program_name: Program name for tracking
            max_variations: Cap per domain (None = unlimited)
            
        Returns:
            Dict mapping variation -> fuzzer type
        """
        if not self.dnstwist_available or not self.Fuzzer:
            logger.warning(f"dnstwist not available, cannot generate variations for {domain}")
            return {}
        
        if '.' not in domain:
            logger.warning(f"Invalid domain format: {domain}")
            return {}
        
        variations = {}
        
        try:
            logger.info(f"🔧 Generating variations for protected domain: {domain}")
            
            with self.Fuzzer(domain) as fuzzer:
                fuzzer.generate(fuzzers=self.fuzzers)
                permutations = fuzzer.permutations()
                
                count = 0
                for perm in permutations:
                    if max_variations is not None and count >= max_variations:
                        logger.warning(f"Reached max variations ({max_variations}) for {domain}")
                        break
                    
                    fuzzer_type = perm.get('fuzzer', 'unknown')
                    variation_domain = perm.get('domain', '')
                    
                    # Skip original domain
                    if fuzzer_type == '*original' or variation_domain == domain:
                        continue
                    
                    if variation_domain and variation_domain != domain:
                        variations[variation_domain] = fuzzer_type
                        count += 1
                
                logger.info(f"✅ Generated {len(variations)} variations for {domain}")
                
                # Log fuzzer breakdown
                fuzzer_counts = {}
                for v, f in variations.items():
                    fuzzer_counts[f] = fuzzer_counts.get(f, 0) + 1
                
                for ftype, fcount in sorted(fuzzer_counts.items(), key=lambda x: -x[1])[:5]:
                    logger.debug(f"   {ftype}: {fcount}")
                
        except Exception as e:
            logger.error(f"Error generating variations for {domain}: {e}")
        
        return variations
    
    def add_protected_domain(
        self, 
        domain: str, 
        program_name: str,
        max_variations: Optional[int] = None,
    ) -> int:
        """
        Add a protected domain and generate its variations.
        
        Args:
            domain: Protected domain
            program_name: Program name
            max_variations: Cap per domain (None = unlimited)
            
        Returns:
            Number of variations generated
        """
        domain = domain.lower().strip()
        
        # Track protected domain
        if program_name not in self._protected_domains:
            self._protected_domains[program_name] = set()
        
        # Skip if already processed
        if domain in self._protected_domains[program_name]:
            logger.debug(f"Domain {domain} already processed for {program_name}")
            return 0
        
        self._protected_domains[program_name].add(domain)
        self._protected_fqdn_set.add(domain)
        
        # Generate variations
        variations = self.generate_variations(domain, program_name, max_variations)
        protected_label = hostname_without_public_suffix(domain)

        # Store variations keyed by registrable hostname label (TLD-agnostic)
        added = 0
        for variation_fqdn, fuzzer in variations.items():
            label = hostname_without_public_suffix(variation_fqdn.lower().strip())
            if not label:
                continue
            if protected_label and label == protected_label:
                continue

            # Only add if not already present (first domain wins)
            if label not in self._variations:
                self._variations[label] = VariationInfo(
                    variation=label,
                    protected_domain=domain,
                    fuzzer=fuzzer,
                    program_name=program_name,
                )
                added += 1

                # Update fuzzer stats
                self._stats["variations_by_fuzzer"][fuzzer] = (
                    self._stats["variations_by_fuzzer"].get(fuzzer, 0) + 1
                )
        
        self._stats["total_variations"] = len(self._variations)
        self._stats["protected_domains"] = sum(len(d) for d in self._protected_domains.values())
        self._stats["programs"] = len(self._protected_domains)
        
        return added
    
    def add_protected_domains(
        self, 
        domains: List[str], 
        program_name: str,
        max_variations_per_domain: Optional[int] = None,
    ) -> int:
        """
        Add multiple protected domains for a program.
        
        Args:
            domains: List of protected domains
            program_name: Program name
            max_variations_per_domain: Cap per domain (None = unlimited)
            
        Returns:
            Total number of variations added
        """
        total_added = 0
        
        for domain in domains:
            added = self.add_protected_domain(
                domain, 
                program_name, 
                max_variations_per_domain
            )
            total_added += added
        
        logger.info(
            f"Added {total_added} variations for {len(domains)} protected domains "
            f"(program: {program_name})"
        )
        
        return total_added
    
    def match(self, cert_domain: str) -> Optional[VariationInfo]:
        """
        Check if a certificate domain matches any known variation (any TLD).

        Exact match on registrable hostname label (public suffix stripped via tldextract).
        O(1) lookup for high-volume CT streams.

        Args:
            cert_domain: Domain from certificate

        Returns:
            VariationInfo if match found, None otherwise
        """
        label = hostname_without_public_suffix(cert_domain.lower().strip())
        if not label:
            return None
        return self._variations.get(label)
    
    def is_protected_domain(self, domain: str) -> bool:
        """Check if domain is a protected domain (not a variation)"""
        return domain.lower().strip() in self._protected_fqdn_set
    
    def is_legitimate_subdomain(self, cert_domain: str) -> bool:
        """Check if cert_domain is a legitimate subdomain of a protected domain"""
        if not self._protected_fqdn_set:
            return False
        cert_domain = cert_domain.lower().strip()
        # Each proper label-suffix lookup replaces an O(N) endswith scan.
        labels = cert_domain.split(".")
        for i in range(1, len(labels)):
            if ".".join(labels[i:]) in self._protected_fqdn_set:
                return True
        return False
    
    def clear(self):
        """Clear all variations and protected domains"""
        self._variations.clear()
        self._protected_domains.clear()
        self._protected_fqdn_set.clear()
        self._stats = {
            "total_variations": 0,
            "variations_by_fuzzer": {},
            "protected_domains": 0,
            "programs": 0
        }
        logger.info("Cleared all variations")
    
    def get_stats(self) -> Dict:
        """Get variation generation statistics"""
        return {
            **self._stats,
            "dnstwist_available": self.dnstwist_available,
            "fuzzers_enabled": self.fuzzers
        }
    
    def get_variation_count(self) -> int:
        """Get total number of variations"""
        return len(self._variations)
    
    def get_protected_domain_count(self) -> int:
        """Get total number of protected domains"""
        return sum(len(d) for d in self._protected_domains.values())

