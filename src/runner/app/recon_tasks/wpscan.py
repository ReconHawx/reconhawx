from typing import Dict, List, Any, Optional
import json
import logging
from .base import Task, AssetType, FindingType
from models.findings import WPScanFinding
from utils import normalize_url_for_storage
from urllib.parse import urlparse
import base64

logger = logging.getLogger(__name__)

class WPScan(Task):
    name = "wpscan"
    description = "Scan WordPress sites for vulnerabilities in WordPress core, plugins, and themes"
    input_type = AssetType.URL
    output_types = [FindingType.WPSCAN]

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        hash_dict = {
            "task": self.name,
            "target": target,
            "params": params
        }
        # Create a reversible hash by using base64 encoding of the dict string
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[str]:
        """Generate WPScan commands - one command per target URL"""
        # Handle both string and list inputs
        targets_to_process = input_data if isinstance(input_data, list) else [input_data]
        
        # Filter valid URLs
        valid_urls = []
        for target in targets_to_process:
            if isinstance(target, str) and (target.startswith('http://') or target.startswith('https://')):
                valid_urls.append(target.strip())
        
        if not valid_urls:
            return ["echo ''"]
        
        # Build base WPScan command options
        api_token = params.get("api_token") if params else None
        enumerate_options = params.get("enumerate", []) if params else []
        
        # Build base command
        base_command_parts = ["wpscan", "--ignore-main-redirect", "--random-user-agent", "--no-banner", "-f", "json"]
        
        # Add API token if provided
        if api_token:
            base_command_parts.extend(["--api-token", api_token])
        
        # Add enumeration options
        if enumerate_options:
            enumerate_str = ','.join(enumerate_options)
            base_command_parts.extend(["--enumerate", enumerate_str])
        else:
            # Default enumeration: vulnerable plugins, vulnerable themes, users
            base_command_parts.extend(["--enumerate", "ap,at,u"])
        
        # Generate one command per URL
        commands = []
        for url in valid_urls:
            # Escape URL for shell safety
            escaped_url = url.replace("'", "'\\''")
            command = f"{' '.join(base_command_parts)} --url '{escaped_url}'"
            commands.append(command)
        
        logger.debug(f"Generated {len(commands)} WPScan commands for {len(valid_urls)} URLs")
        return commands

    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse WPScan JSON output into findings"""
        findings = []
        
        # Use the base class helper to normalize output format
        normalized_output = self.normalize_output_for_parsing(output)
        
        if not normalized_output:
            return {FindingType.WPSCAN: []}
        
        try:
            # WPScan outputs a single JSON object (not JSON lines like nuclei)
            wpscan_data = json.loads(normalized_output)
            
            logger.debug(f"WPScan JSON keys: {list(wpscan_data.keys())}")
            
            # Get the target URL - try multiple possible locations
            target_url = wpscan_data.get("target_url") or wpscan_data.get("url") or wpscan_data.get("effective_url") or ""
            if not target_url:
                logger.warning("Could not determine target URL from WPScan output")
                logger.debug(f"Available keys: {list(wpscan_data.keys())}")
                return {FindingType.WPSCAN: []}
            
            logger.debug(f"Extracted target_url: {target_url}")
            
            # Normalize URL
            target_url = normalize_url_for_storage(target_url)
            
            # Extract hostname, port, scheme from URL
            parsed_url = urlparse(target_url)
            hostname = parsed_url.hostname.lower() if parsed_url.hostname else None
            port = parsed_url.port
            scheme = parsed_url.scheme.lower() if parsed_url.scheme else None
            
            # Build enumeration data from scan results
            enumeration_data = {}
            
            # Extract WordPress version (from version.number)
            version_info = wpscan_data.get("version", {})
            if version_info and isinstance(version_info, dict):
                wp_version = version_info.get("number")
                if wp_version:
                    enumeration_data["wordpress_version"] = wp_version
            
            # Extract plugins (both vulnerable and non-vulnerable)
            plugins_data = wpscan_data.get("plugins", {})
            discovered_plugins = []
            plugin_versions = {}
            if plugins_data:
                for plugin_name, plugin_info in plugins_data.items():
                    if isinstance(plugin_info, dict):
                        discovered_plugins.append(plugin_name)
                        # Plugin version can be in version.number or directly in version
                        plugin_version_obj = plugin_info.get("version", {})
                        if isinstance(plugin_version_obj, dict):
                            plugin_version = plugin_version_obj.get("number")
                        else:
                            plugin_version = plugin_version_obj
                        if plugin_version:
                            plugin_versions[plugin_name] = plugin_version
            
            if discovered_plugins:
                enumeration_data["plugins"] = discovered_plugins
                enumeration_data["plugin_versions"] = plugin_versions
            
            # Extract themes (both vulnerable and non-vulnerable)
            # Include main_theme and themes dict
            themes_data = wpscan_data.get("themes", {})
            main_theme = wpscan_data.get("main_theme", {})
            discovered_themes = []
            theme_versions = {}
            
            # Add main theme
            if main_theme and isinstance(main_theme, dict):
                theme_slug = main_theme.get("slug")
                if theme_slug:
                    discovered_themes.append(theme_slug)
                    theme_version_obj = main_theme.get("version", {})
                    if isinstance(theme_version_obj, dict):
                        theme_version = theme_version_obj.get("number")
                    else:
                        theme_version = theme_version_obj
                    if theme_version:
                        theme_versions[theme_slug] = theme_version
            
            # Add other themes
            if themes_data:
                for theme_name, theme_info in themes_data.items():
                    if isinstance(theme_info, dict):
                        if theme_name not in discovered_themes:
                            discovered_themes.append(theme_name)
                        theme_version_obj = theme_info.get("version", {})
                        if isinstance(theme_version_obj, dict):
                            theme_version = theme_version_obj.get("number")
                        else:
                            theme_version = theme_version_obj
                        if theme_version:
                            theme_versions[theme_name] = theme_version
            
            if discovered_themes:
                enumeration_data["themes"] = discovered_themes
                enumeration_data["theme_versions"] = theme_versions
            
            # Extract users
            users_data = wpscan_data.get("users", {})
            enumerated_users = []
            if users_data:
                if isinstance(users_data, dict):
                    # Users as dict with usernames as keys
                    for username, user_info in users_data.items():
                        if isinstance(user_info, dict):
                            # Use the key (username) or extract from user_info
                            display_name = user_info.get("name") or user_info.get("slug") or username
                            enumerated_users.append(display_name)
                        elif isinstance(user_info, str):
                            enumerated_users.append(user_info)
                        else:
                            enumerated_users.append(username)
                elif isinstance(users_data, list):
                    # Users as list
                    for user_item in users_data:
                        if isinstance(user_item, dict):
                            username = user_item.get("name") or user_item.get("slug") or str(user_item)
                            enumerated_users.append(username)
                        elif isinstance(user_item, str):
                            enumerated_users.append(user_item)
            
            if enumerated_users:
                enumeration_data["users"] = enumerated_users
            
            # Log enumeration data collection for debugging
            if enumeration_data:
                logger.debug(f"Collected enumeration data for {target_url}: {json.dumps(enumeration_data, indent=2)}")
            
            # Process WordPress core vulnerabilities (from version.vulnerabilities)
            if version_info and isinstance(version_info, dict):
                wordpress_vulns = version_info.get("vulnerabilities", [])
                if isinstance(wordpress_vulns, list) and wordpress_vulns:
                    for vuln in wordpress_vulns:
                        finding = self._create_finding_from_vulnerability(
                            target_url=target_url,
                            item_name="WordPress",
                            item_type="wordpress",
                            vulnerability=vuln,
                            hostname=hostname,
                            port=port,
                            scheme=scheme,
                            enumeration_data=None  # Don't include enumeration data in vulnerability findings
                        )
                        if finding:
                            findings.append(finding)
            
            # Process plugin vulnerabilities
            if plugins_data:
                for plugin_name, plugin_info in plugins_data.items():
                    if isinstance(plugin_info, dict):
                        plugin_vulns = plugin_info.get("vulnerabilities", [])
                        if isinstance(plugin_vulns, list) and plugin_vulns:
                            for vuln in plugin_vulns:
                                finding = self._create_finding_from_vulnerability(
                                    target_url=target_url,
                                    item_name=plugin_name,
                                    item_type="plugin",
                                    vulnerability=vuln,
                                    hostname=hostname,
                                    port=port,
                                    scheme=scheme,
                                    enumeration_data=None  # Don't include enumeration data in vulnerability findings
                                )
                                if finding:
                                    findings.append(finding)
            
            # Process theme vulnerabilities (from main_theme and themes)
            # Check main_theme vulnerabilities
            if main_theme and isinstance(main_theme, dict):
                main_theme_vulns = main_theme.get("vulnerabilities", [])
                if isinstance(main_theme_vulns, list) and main_theme_vulns:
                    theme_slug = main_theme.get("slug", "unknown")
                    for vuln in main_theme_vulns:
                        finding = self._create_finding_from_vulnerability(
                            target_url=target_url,
                            item_name=theme_slug,
                            item_type="theme",
                            vulnerability=vuln,
                            hostname=hostname,
                            port=port,
                            scheme=scheme,
                            enumeration_data=None  # Don't include enumeration data in vulnerability findings
                        )
                        if finding:
                            findings.append(finding)
            
            # Check themes dict vulnerabilities
            if themes_data:
                for theme_name, theme_info in themes_data.items():
                    if isinstance(theme_info, dict):
                        theme_vulns = theme_info.get("vulnerabilities", [])
                        if isinstance(theme_vulns, list) and theme_vulns:
                            for vuln in theme_vulns:
                                finding = self._create_finding_from_vulnerability(
                                    target_url=target_url,
                                    item_name=theme_name,
                                    item_type="theme",
                                    vulnerability=vuln,
                                    hostname=hostname,
                                    port=port,
                                    scheme=scheme,
                                    enumeration_data=None  # Don't include enumeration data in vulnerability findings
                                )
                                if finding:
                                    findings.append(finding)
            
            # Process interesting findings (non-vulnerability findings)
            interesting_findings = wpscan_data.get("interesting_findings", [])
            if isinstance(interesting_findings, list):
                for interesting_finding in interesting_findings:
                    if isinstance(interesting_finding, dict):
                        finding = self._create_finding_from_interesting_finding(
                            interesting_finding=interesting_finding,
                            target_url=target_url,
                            hostname=hostname,
                            port=port,
                            scheme=scheme,
                            enumeration_data=None  # Don't include enumeration data in interesting findings
                        )
                        if finding:
                            findings.append(finding)
            
            # Create separate enumeration findings
            # Enumerated users finding
            if enumerated_users:
                enum_finding = self._create_enumeration_finding(
                    target_url=target_url,
                    item_name="Enumerated users",
                    item_type="enumeration",
                    enumeration_type="users",
                    enumeration_data={"users": enumerated_users},
                    hostname=hostname,
                    port=port,
                    scheme=scheme
                )
                if enum_finding:
                    findings.append(enum_finding)
            
            # Enumerated plugins finding
            if discovered_plugins:
                plugin_enum_data = {"plugins": discovered_plugins}
                if plugin_versions:
                    plugin_enum_data["plugin_versions"] = plugin_versions
                enum_finding = self._create_enumeration_finding(
                    target_url=target_url,
                    item_name="Enumerated plugins",
                    item_type="enumeration",
                    enumeration_type="plugins",
                    enumeration_data=plugin_enum_data,
                    hostname=hostname,
                    port=port,
                    scheme=scheme
                )
                if enum_finding:
                    findings.append(enum_finding)
            
            # Enumerated themes finding
            if discovered_themes:
                theme_enum_data = {"themes": discovered_themes}
                if theme_versions:
                    theme_enum_data["theme_versions"] = theme_versions
                enum_finding = self._create_enumeration_finding(
                    target_url=target_url,
                    item_name="Enumerated themes",
                    item_type="enumeration",
                    enumeration_type="themes",
                    enumeration_data=theme_enum_data,
                    hostname=hostname,
                    port=port,
                    scheme=scheme
                )
                if enum_finding:
                    findings.append(enum_finding)
            
            # WordPress version finding
            if enumeration_data.get("wordpress_version"):
                enum_finding = self._create_enumeration_finding(
                    target_url=target_url,
                    item_name="WordPress version",
                    item_type="enumeration",
                    enumeration_type="wordpress_version",
                    enumeration_data={"wordpress_version": enumeration_data["wordpress_version"]},
                    hostname=hostname,
                    port=port,
                    scheme=scheme
                )
                if enum_finding:
                    findings.append(enum_finding)
            
            if findings:
                logger.info(f"Parsed WPScan output: {len(findings)} findings for {target_url}")
            else:
                # Log enumeration data even when no vulnerabilities found
                enum_summary = []
                if enumeration_data.get("wordpress_version"):
                    enum_summary.append(f"WordPress {enumeration_data['wordpress_version']}")
                if enumeration_data.get("plugins"):
                    enum_summary.append(f"{len(enumeration_data['plugins'])} plugins")
                if enumeration_data.get("themes"):
                    enum_summary.append(f"{len(enumeration_data['themes'])} themes")
                if enumeration_data.get("users"):
                    enum_summary.append(f"{len(enumeration_data['users'])} users")
                
                if enum_summary:
                    logger.info(f"Parsed WPScan output: 0 vulnerabilities, but found {', '.join(enum_summary)} for {target_url}")
                else:
                    logger.info(f"Parsed WPScan output: 0 findings for {target_url}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing WPScan JSON output: {e}")
            logger.debug(f"Output content: {normalized_output[:500]}...")
            return {FindingType.WPSCAN: []}
        except Exception as e:
            logger.error(f"Unexpected error parsing WPScan output: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {FindingType.WPSCAN: []}
        
        return {FindingType.WPSCAN: findings}

    def _create_finding_from_vulnerability(
        self,
        target_url: str,
        item_name: str,
        item_type: str,
        vulnerability: Dict[str, Any],
        hostname: Optional[str] = None,
        port: Optional[int] = None,
        scheme: Optional[str] = None,
        enumeration_data: Optional[Dict[str, Any]] = None
    ) -> Optional[WPScanFinding]:
        """Create a WPScanFinding from a vulnerability dictionary"""
        try:
            # Extract vulnerability details
            title = vulnerability.get("title") or vulnerability.get("name") or f"{item_name} Vulnerability"
            description = vulnerability.get("description") or ""
            severity = self._map_wpscan_severity(vulnerability.get("severity") or vulnerability.get("cvss_score"))
            fixed_in = vulnerability.get("fixed_in") or vulnerability.get("fixed_in_version")
            
            # Extract references
            references = []
            if vulnerability.get("references"):
                refs = vulnerability.get("references", {})
                if isinstance(refs, dict):
                    # References can be a dict with different types
                    for ref_type, ref_list in refs.items():
                        if isinstance(ref_list, list):
                            references.extend(ref_list)
                        elif isinstance(ref_list, str):
                            references.append(ref_list)
                elif isinstance(refs, list):
                    references.extend(refs)
            
            # Extract CVE IDs
            cve_ids = []
            if vulnerability.get("cve"):
                cve = vulnerability.get("cve")
                if isinstance(cve, list):
                    cve_ids.extend(cve)
                elif isinstance(cve, str):
                    cve_ids.append(cve)
            
            # If no CVE but references contain CVE links, extract them
            if not cve_ids and references:
                import re
                cve_pattern = r'CVE-\d{4}-\d{4,}'
                for ref in references:
                    if isinstance(ref, str):
                        matches = re.findall(cve_pattern, ref, re.IGNORECASE)
                        cve_ids.extend(matches)
            
            # Determine vulnerability type
            vulnerability_type = "CVE" if cve_ids else "Other"
            
            finding = WPScanFinding(
                url=target_url,
                item_name=item_name,
                item_type=item_type,
                vulnerability_type=vulnerability_type,
                severity=severity,
                title=title,
                description=description,
                fixed_in=fixed_in,
                references=references[:10] if references else [],  # Limit to 10 references
                cve_ids=cve_ids[:10] if cve_ids else [],  # Limit to 10 CVEs
                enumeration_data=enumeration_data,
                hostname=hostname,
                port=port,
                scheme=scheme
            )
            
            return finding
            
        except Exception as e:
            logger.error(f"Error creating WPScan finding from vulnerability: {str(e)}")
            logger.error(f"Vulnerability data: {vulnerability}")
            return None

    def _create_finding_from_interesting_finding(
        self,
        interesting_finding: Dict[str, Any],
        target_url: str,
        hostname: Optional[str] = None,
        port: Optional[int] = None,
        scheme: Optional[str] = None,
        enumeration_data: Optional[Dict[str, Any]] = None
    ) -> Optional[WPScanFinding]:
        """Create a WPScanFinding from an interesting finding (non-vulnerability finding)"""
        try:
            # Get the finding URL (may differ from target_url)
            finding_url = interesting_finding.get("url", target_url)
            finding_url = normalize_url_for_storage(finding_url)
            
            # Extract finding details
            finding_type = interesting_finding.get("type", "unknown")
            title = interesting_finding.get("to_s") or f"WordPress {finding_type.title()} Finding"
            description = interesting_finding.get("description") or title
            
            # Map finding type to severity
            severity = self._map_finding_type_to_severity(finding_type)
            
            # Extract references
            references = []
            refs = interesting_finding.get("references", {})
            if isinstance(refs, dict):
                for ref_type, ref_list in refs.items():
                    if isinstance(ref_list, list):
                        references.extend(ref_list)
                    elif isinstance(ref_list, str):
                        references.append(ref_list)
            elif isinstance(refs, list):
                references.extend(refs)
            
            # Extract interesting entries as additional description
            interesting_entries = interesting_finding.get("interesting_entries", [])
            if interesting_entries and isinstance(interesting_entries, list):
                entries_text = "\n".join(interesting_entries)
                if description:
                    description = f"{description}\n\nInteresting entries:\n{entries_text}"
                else:
                    description = f"Interesting entries:\n{entries_text}"
            
            # Update hostname/port/scheme from finding URL if different
            parsed_finding_url = urlparse(finding_url)
            finding_hostname = parsed_finding_url.hostname.lower() if parsed_finding_url.hostname else hostname
            finding_port = parsed_finding_url.port or port
            finding_scheme = parsed_finding_url.scheme.lower() if parsed_finding_url.scheme else scheme
            
            finding = WPScanFinding(
                url=finding_url,
                item_name=finding_type,
                item_type="finding",  # Use "finding" as item_type for interesting findings
                vulnerability_type="Information",  # Not a vulnerability, but informational finding
                severity=severity,
                title=title,
                description=description,
                fixed_in=None,
                references=references[:10] if references else [],
                cve_ids=[],
                enumeration_data=enumeration_data,
                hostname=finding_hostname,
                port=finding_port,
                scheme=finding_scheme
            )
            
            return finding
            
        except Exception as e:
            logger.error(f"Error creating WPScan finding from interesting finding: {str(e)}")
            logger.error(f"Interesting finding data: {interesting_finding}")
            return None

    def _map_finding_type_to_severity(self, finding_type: str) -> str:
        """Map WPScan interesting finding type to severity level"""
        if not finding_type:
            return "info"
        
        finding_type_lower = finding_type.lower()
        
        # Higher severity findings
        high_severity_types = [
            "upload_directory_listing",  # Can expose sensitive files
            "xmlrpc",  # Can be used for attacks
        ]
        
        # Medium severity findings
        medium_severity_types = [
            "wp_cron",  # Can be abused for DoS
            "readme",  # Information disclosure
        ]
        
        # Low severity findings (most others)
        low_severity_types = [
            "robots_txt",  # Information disclosure
            "headers",  # Information disclosure
        ]
        
        if finding_type_lower in high_severity_types:
            return "medium"  # Not critical, but notable
        elif finding_type_lower in medium_severity_types:
            return "low"
        elif finding_type_lower in low_severity_types:
            return "info"
        else:
            # Default to info for unknown types
            return "info"

    def _map_wpscan_severity(self, severity: Any) -> str:
        """Map WPScan severity to standard severity levels"""
        if not severity:
            return "info"
        
        severity_str = str(severity).lower()
        
        # Handle numeric CVSS scores
        try:
            cvss_score = float(severity_str)
            if cvss_score >= 9.0:
                return "critical"
            elif cvss_score >= 7.0:
                return "high"
            elif cvss_score >= 4.0:
                return "medium"
            elif cvss_score >= 0.1:
                return "low"
            else:
                return "info"
        except (ValueError, TypeError):
            pass
        
        # Handle text severity levels
        if severity_str in ["critical", "high", "medium", "low", "info"]:
            return severity_str
        
        # Map common variations
        severity_mapping = {
            "crit": "critical",
            "high": "high",
            "med": "medium",
            "medium": "medium",
            "low": "low",
            "info": "info",
            "informational": "info"
        }
        
        return severity_mapping.get(severity_str, "info")
    
    def _create_enumeration_finding(
        self,
        target_url: str,
        item_name: str,
        item_type: str,
        enumeration_type: str,
        enumeration_data: Dict[str, Any],
        hostname: Optional[str] = None,
        port: Optional[int] = None,
        scheme: Optional[str] = None
    ) -> Optional[WPScanFinding]:
        """Create a WPScanFinding for enumeration data (users, plugins, themes, WordPress version)"""
        try:
            # Create description based on enumeration type
            if enumeration_type == "users":
                user_count = len(enumeration_data.get("users", []))
                description = f"WPScan enumerated {user_count} user(s) on this WordPress site."
                if user_count > 0:
                    description += "\n\nEnumerated users:\n" + "\n".join(f"- {user}" for user in enumeration_data["users"])
            elif enumeration_type == "plugins":
                plugin_count = len(enumeration_data.get("plugins", []))
                description = f"WPScan discovered {plugin_count} plugin(s) on this WordPress site."
                if plugin_count > 0:
                    plugin_list = []
                    for plugin in enumeration_data["plugins"]:
                        version = enumeration_data.get("plugin_versions", {}).get(plugin)
                        if version:
                            plugin_list.append(f"- {plugin} (version: {version})")
                        else:
                            plugin_list.append(f"- {plugin}")
                    description += "\n\nDiscovered plugins:\n" + "\n".join(plugin_list)
            elif enumeration_type == "themes":
                theme_count = len(enumeration_data.get("themes", []))
                description = f"WPScan discovered {theme_count} theme(s) on this WordPress site."
                if theme_count > 0:
                    theme_list = []
                    for theme in enumeration_data["themes"]:
                        version = enumeration_data.get("theme_versions", {}).get(theme)
                        if version:
                            theme_list.append(f"- {theme} (version: {version})")
                        else:
                            theme_list.append(f"- {theme}")
                    description += "\n\nDiscovered themes:\n" + "\n".join(theme_list)
            elif enumeration_type == "wordpress_version":
                wp_version = enumeration_data.get("wordpress_version", "unknown")
                description = f"WPScan detected WordPress version {wp_version} on this site."
            else:
                description = f"WPScan enumeration data: {enumeration_type}"
            
            finding = WPScanFinding(
                url=target_url,
                item_name=item_name,
                item_type=item_type,
                vulnerability_type="Information",  # Enumeration findings are informational
                severity="info",
                title=item_name,
                description=description,
                fixed_in=None,
                references=[],
                cve_ids=[],
                enumeration_data=enumeration_data,
                hostname=hostname,
                port=port,
                scheme=scheme
            )
            
            return finding
            
        except Exception as e:
            logger.error(f"Error creating enumeration finding: {str(e)}")
            logger.error(f"Enumeration data: {enumeration_data}")
            return None
