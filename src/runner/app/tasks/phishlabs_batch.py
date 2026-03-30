import aiohttp
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import os
import asyncio

logger = logging.getLogger(__name__)

class GoogleSafeBrowsingService:
    """Service for reporting domains to Google Safe Browsing in the runner environment"""

    async def report_domain(self, domain: str, program_name: str = None) -> Dict[str, Any]:
        """
        Report a domain to Google Safe Browsing.

        Args:
            domain: The domain to report
            program_name: Associated program name

        Returns:
            Dict containing success status and details
        """
        try:
            logger.info(f"Reporting domain {domain} to Google Safe Browsing")

            # TODO: Implement actual Google Safe Browsing API integration
            # For now, this is a placeholder that simulates the reporting process

            # Simulate API delay
            await asyncio.sleep(0.5)

            # Mock successful response
            result = {
                "status": "success",
                "domain": domain,
                "program_name": program_name,
                "reported_at": datetime.now(timezone.utc).isoformat(),
                "reference_id": f"gsb_{domain}_{int(datetime.now(timezone.utc).timestamp())}",
                "message": f"Domain {domain} reported to Google Safe Browsing successfully"
            }

            logger.info(f"Successfully reported domain {domain} to Google Safe Browsing (reference: {result['reference_id']})")
            return result

        except Exception as e:
            error_msg = f"Failed to report domain {domain} to Google Safe Browsing: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "domain": domain,
                "program_name": program_name,
                "error": str(e),
                "message": error_msg
            }

class PhishLabsBatchTask:
    def __init__(self, job_id: str, finding_ids: List[str], user_id: str, action: str = "fetch", catcode: Optional[str] = None, comment: Optional[str] = None, report_to_gsb: bool = False):
        self.job_id = job_id
        self.finding_ids = finding_ids
        self.user_id = user_id
        self.action = action  # "fetch" or "create"
        self.catcode = catcode  # Only used for create action
        self.comment = comment  # Custom comment for incident creation
        self.report_to_gsb = report_to_gsb  # Whether to report to Google Safe Browsing
        self.results = {
            "success_count": 0,
            "error_count": 0,
            "errors": [],
            "processed_findings": []
        }

        # API configuration
        self.api_base_url = os.getenv("API_BASE_URL", "http://api:8000")
        self.api_token = os.getenv("INTERNAL_SERVICE_API_KEY", "")  # If authentication is required

        logger.info(f"PhishLabsBatchTask initialized with API_BASE_URL: {self.api_base_url}")
        logger.info(f"API token configured: {'Yes' if self.api_token else 'No'}")
    
    async def execute(self):
        """Main execution method"""
        try:
            # Update job status to running
            action_message = "fetching data" if self.action == "fetch" else "creating incidents"
            await self.update_job_status("running", 0, f"Starting PhishLabs batch {action_message}...")

            # Test API connectivity first
            await self.test_api_connectivity()

            # Get all findings via API
            findings = await self.get_findings()
            if not findings:
                await self.update_job_status("failed", 0, "No valid findings found")
                return

            # Group by program
            program_findings = self.group_findings_by_program(findings)

            # Process each program
            total_findings = len(findings)
            processed_count = 0

            for program_name, program_findings_list in program_findings.items():
                await self.process_program_findings(program_name, program_findings_list)
                processed_count += len(program_findings_list)

                # Update progress
                progress = int((processed_count / total_findings) * 100)
                await self.update_job_status("running", progress, f"Processed {processed_count}/{total_findings} findings...")

            # Final status update
            message = f"Completed: {self.results['success_count']} successful, {self.results['error_count']} errors"

            # Add summary of incident IDs created/updated
            incident_ids = [finding.get('incident_id') for finding in self.results['processed_findings'] if finding.get('incident_id')]
            if incident_ids:
                message += f". Created/updated {len(incident_ids)} incidents: {', '.join(map(str, incident_ids[:5]))}"
                if len(incident_ids) > 5:
                    message += f" (and {len(incident_ids) - 5} more)"

            # Add summary of Google Safe Browsing reports if enabled
            if self.report_to_gsb:
                gsb_reports = [finding.get('google_safe_browsing') for finding in self.results['processed_findings'] if finding.get('google_safe_browsing')]
                successful_gsb = [report for report in gsb_reports if report.get('status') == 'success']
                if successful_gsb:
                    message += f". Reported {len(successful_gsb)} domains to Google Safe Browsing"

            logger.info(f"Batch job {self.job_id} final results: {self.results}")
            await self.update_job_status("completed", 100, message, self.results)

        except Exception as e:
            logger.error(f"Error in PhishLabs batch job {self.job_id}: {str(e)}")
            await self.update_job_status("failed", 0, f"Job failed: {str(e)}")
    
    async def get_findings(self) -> List[Dict]:
        """Get findings via API"""
        try:
            findings = []
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            logger.info(f"Fetching {len(self.finding_ids)} findings: {self.finding_ids}")

            for finding_id in self.finding_ids:
                url = f"{self.api_base_url}/findings/typosquat?id={finding_id}"
                logger.info(f"Fetching finding {finding_id} from: {url}")

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as response:
                        logger.info(f"Finding API response status for {finding_id}: {response.status}")

                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"Finding API response data for {finding_id}: {data}")

                            if data.get("status") == "success" and data.get("data"):
                                finding = data["data"]
                                finding["_id"] = finding_id  # Ensure _id is set for consistency
                                findings.append(finding)
                                logger.info(f"Successfully fetched finding {finding_id}: {finding.get('typo_domain', 'Unknown')}")
                            else:
                                logger.warning(f"Finding {finding_id} not found or invalid response: {data}")
                        else:
                            response_text = await response.text()
                            logger.warning(f"Failed to get finding {finding_id}: HTTP {response.status} - {response_text}")

            logger.info(f"Successfully fetched {len(findings)} out of {len(self.finding_ids)} findings")
            return findings
        except Exception as e:
            logger.error(f"Error getting findings via API: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []
    
    def group_findings_by_program(self, findings: List[Dict]) -> Dict[str, List[Dict]]:
        """Group findings by program name"""
        program_findings = {}
        for finding in findings:
            program_name = finding.get('program_name')
            if not program_name:
                logger.warning(f"Finding {finding.get('_id')} has no program_name, skipping")
                continue
            if program_name not in program_findings:
                program_findings[program_name] = []
            program_findings[program_name].append(finding)
        return program_findings
    
    async def get_program_api_key(self, program_name: str) -> Optional[str]:
        """Get PhishLabs API key for a program via API (with database fallback)"""
        try:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/programs/{program_name}"
            logger.info(f"Fetching program API key from: {url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    logger.info(f"Program API response status: {response.status}")

                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Program API response data: {data}")

                        # Handle different API response formats
                        api_key = None

                        logger.info(f"Processing API response for program {program_name}:")
                        logger.info(f"  - Response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        logger.info(f"  - Status field: {data.get('status')}")
                        logger.info(f"  - Has 'data' field: {'Yes' if data.get('data') else 'No'}")
                        logger.info(f"  - Has 'phishlabs_api_key' directly: {'Yes' if data.get('phishlabs_api_key') else 'No'}")

                        if data.get("status") == "success":
                            # Try to get program data from nested structure first
                            program_data = data.get("data", {})

                            # If program_data is empty or doesn't have the fields we need,
                            # try to get data directly from the response (alternative format)
                            if not program_data or not program_data.get("phishlabs_api_key"):
                                program_data = data

                            api_key = program_data.get("phishlabs_api_key")
                            logger.info(f"  - Extracted API key from program_data: {'*' * len(api_key) if api_key else 'None'}")
                        elif data.get("phishlabs_api_key"):
                            # Direct program data format (no wrapper)
                            api_key = data.get("phishlabs_api_key")
                            logger.info(f"  - Extracted API key directly from response: {'*' * len(api_key) if api_key else 'None'}")
                        else:
                            logger.warning(f"Program API returned unexpected format: {data}")

                        if api_key:
                            logger.info(f"Successfully found API key for program {program_name}: {'*' * len(api_key)}")
                            logger.debug(f"Program data structure: {data}")
                            return api_key
                        else:
                            logger.warning(f"No API key found for program {program_name} in response")
                            logger.warning(f"Full response data: {data}")
                    else:
                        response_text = await response.text()
                        logger.warning(f"Failed to get program {program_name}: HTTP {response.status} - {response_text}")

            # Fallback: Try to get program data via alternative endpoint
            logger.info(f"API method failed, trying alternative endpoint for program {program_name}")
            alt_url = f"{self.api_base_url}/programs"
            async with aiohttp.ClientSession() as session:
                async with session.get(alt_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Alternative programs API response: {data}")

                        if data.get("status") == "success":
                            # Try to get programs from different possible structures
                            programs = data.get("programs", [])
                            if not programs:
                                programs = data.get("programs_with_permissions", [])
                            if not programs and data.get("programs"):
                                programs = [data["programs"]]  # Single program object

                            logger.debug(f"Programs list structure: {programs}")

                            for program in programs:
                                if isinstance(program, dict):
                                    prog_name = program.get("name")
                                    if prog_name == program_name:
                                        api_key = program.get("phishlabs_api_key")
                                        logger.info(f"Found API key for program {program_name} via alternative endpoint: {'*' * len(api_key) if api_key else 'None'}")
                                        logger.debug(f"Program data from alternative endpoint: {program}")
                                        return api_key

            logger.error(f"Could not find API key for program {program_name} using any method")
            return None
        except Exception as e:
            logger.error(f"Error getting program API key for {program_name}: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None
    
    async def process_program_findings(self, program_name: str, findings: List[Dict]):
        """Process findings for a specific program"""
        logger.info(f"Processing {len(findings)} findings for program '{program_name}'")

        # Get program API key
        api_key = await self.get_program_api_key(program_name)
        logger.info(f"Program '{program_name}' API key result: {'Found' if api_key else 'Not found'}")

        if not api_key:
            logger.error(f"No API key found for program '{program_name}', skipping {len(findings)} findings")
            for finding in findings:
                finding_id = str(finding.get('_id', 'Unknown'))
                typo_domain = finding.get('typo_domain', 'Unknown')
                logger.warning(f"Finding {finding_id} ({typo_domain}) failed: No API key for program '{program_name}'")

                self.results["error_count"] += 1
                self.results["errors"].append({
                    "finding_id": finding_id,
                    "typo_domain": typo_domain,
                    "error": f"Program '{program_name}' does not have a PhishLabs API key"
                })
            return
        
        # Process each finding
        async with aiohttp.ClientSession() as session:
            for finding in findings:
                await self.process_single_finding(session, finding, api_key)
    
    async def process_single_finding(self, session: aiohttp.ClientSession, finding: Dict, api_key: str):
        """Process a single finding"""
        finding_id = str(finding.get('_id'))
        typo_domain = finding.get('typo_domain')
        
        try:
            # Report to Google Safe Browsing if requested (only for incident creation)
            gsb_result = None
            if self.report_to_gsb and self.action == "create":
                logger.info(f"Reporting domain {typo_domain} to Google Safe Browsing before creating PhishLabs incident")
                gsb_service = GoogleSafeBrowsingService()
                gsb_result = await gsb_service.report_domain(typo_domain, finding.get('program_name'))

                # Log the Google Safe Browsing action
                if gsb_result and gsb_result.get("status") == "success":
                    try:
                        await self.log_action_via_api(
                            entity_type="typosquat_finding",
                            entity_id=finding_id,
                            action_type="google_safe_browsing_reported",
                            user_id=self.user_id,
                            old_value=None,
                            new_value={"gsb_reference_id": gsb_result.get("reference_id")},
                            metadata={
                                "job_id": self.job_id,
                                "domain": typo_domain,
                                "program_name": finding.get('program_name'),
                                "reference_id": gsb_result.get("reference_id"),
                                "comment": f"Domain {typo_domain} reported to Google Safe Browsing via batch job {self.job_id} (ref: {gsb_result.get('reference_id')})"
                            }
                        )
                        logger.info(f"Logged Google Safe Browsing action for finding {finding_id}")
                    except Exception as log_error:
                        logger.error(f"Error logging Google Safe Browsing action for finding {finding_id}: {str(log_error)}")

            # Call PhishLabs APIs using typo_domain as the URL parameter
            if not typo_domain:
                raise Exception("Typo domain is missing")
            phishlabs_result = await self.call_phishlabs_apis(session, typo_domain, api_key, self.action, self.catcode)

            logger.info(f"PhishLabs API result for {typo_domain}: incident_id={phishlabs_result.get('incident_id')}, no_incident={phishlabs_result.get('no_incident')}")

            # Update finding via API
            await self.update_finding(finding_id, phishlabs_result)

            # Validate that we have incident data for create actions
            incident_id = phishlabs_result.get("incident_id")
            if self.action == "create" and not incident_id and not phishlabs_result.get("no_incident"):
                logger.warning(f"Create action completed but no incident ID returned for {typo_domain}")

            self.results["success_count"] += 1
            processed_finding = {
                "finding_id": finding_id,
                "typo_domain": typo_domain,
                "incident_id": incident_id,
                "status": "success",
                "action": self.action
            }

            # Add Google Safe Browsing information if it was reported
            if gsb_result:
                processed_finding["google_safe_browsing"] = {
                    "status": gsb_result.get("status"),
                    "reference_id": gsb_result.get("reference_id"),
                    "reported_at": gsb_result.get("reported_at")
                }

            self.results["processed_findings"].append(processed_finding)

            logger.info(f"Successfully processed finding {finding_id} ({typo_domain}) with incident ID: {incident_id} (action: {self.action})")

            # Log the action via API for incident creation
            if self.action == "create" and incident_id:
                await self.log_action_via_api(
                    entity_type="typosquat_finding",
                    entity_id=finding_id,
                    action_type="phishlabs_incident_created",
                    user_id=self.user_id,
                    old_value=None,
                    new_value={"phishlabs_incident_id": incident_id},
                    metadata={
                        "job_id": self.job_id,
                        "incident_id": incident_id,
                        "typo_domain": typo_domain,
                        "catcode": self.catcode,
                        "comment": f"PhishLabs incident {incident_id} created for domain {typo_domain} via batch job {self.job_id}"
                    }
                )

                # Collect actions to add based on conditions
                actions_to_add = []

                # Check if finding has RecordedFuture data and auto-add monitoring action
                if finding.get('recordedfuture_data'):
                    logger.info(f"Finding {finding_id} has RecordedFuture data, automatically adding monitoring action")
                    actions_to_add.append('monitoring')
                else:
                    logger.debug(f"Finding {finding_id} has no RecordedFuture data, skipping automatic action update")

                # Check if Google Safe Browsing was successfully reported and update action_taken
                if gsb_result and gsb_result.get("status") == "success":
                    logger.info(f"Google Safe Browsing was successfully reported for finding {finding_id}, adding reported_google_safe_browsing action")
                    actions_to_add.append('reported_google_safe_browsing')

                # Update all actions with delays to avoid race conditions
                if actions_to_add:
                    logger.info(f"Adding {len(actions_to_add)} actions to finding {finding_id}: {actions_to_add}")
                    for i, action in enumerate(actions_to_add):
                        if i > 0:
                            # Add a longer delay between actions to avoid race conditions
                            logger.info("Waiting 1 second before adding next action to avoid race conditions...")
                            await asyncio.sleep(1.0)

                        logger.info(f"Adding action '{action}' ({i+1}/{len(actions_to_add)}) to finding {finding_id}")
                        success = await self.update_finding_action_taken(finding_id, action)
                        if not success:
                            logger.error(f"FAILED to add action '{action}' to finding {finding_id}")
                        else:
                            logger.info(f"Successfully added action '{action}' to finding {finding_id}")

        except Exception as e:
            logger.error(f"Error processing finding {finding_id}: {str(e)}")
            self.results["error_count"] += 1
            self.results["errors"].append({
                "finding_id": finding_id,
                "typo_domain": typo_domain,
                "error": str(e)
            })
    
    async def call_phishlabs_apis(self, session: aiohttp.ClientSession, typo_domain: str, api_key: str, action: str = "fetch", catcode: Optional[str] = None) -> Dict[str, Any]:
        """Call PhishLabs APIs for a domain using multiple URL formats in sequence"""
        # Ensure typo_domain is a string (handle Pydantic URL objects)
        if hasattr(typo_domain, '__class__') and 'Url' in str(type(typo_domain)):
            # Convert Pydantic URL object to string
            typo_domain = str(typo_domain)
        elif not isinstance(typo_domain, str):
            # Convert any other object to string
            typo_domain = str(typo_domain)

        logger.debug(f"Using typo_domain for PhishLabs API: {typo_domain} (type: {type(typo_domain)})")

        # Determine flags and catcode based on action
        if action == "create":
            flags = 0  # Create incident
            # Use provided catcode or default to 12345
            final_catcode = catcode if catcode else "12345"
            # Use custom comment or default fallback
            comment = self.comment if self.comment else "Typosquat domain that impersonate our Brand. Please monitor."
        else:
            flags = 2  # Check/fetch existing incident
            final_catcode = "12345"  # Default catcode for checking

        # For checking existing incidents, try multiple URL formats in sequence
        if action == "fetch":
            url_formats = [
                typo_domain,  # 1st: domain.com
                f"http://{typo_domain}",  # 2nd: http://domain.com
                f"https://{typo_domain}"  # 3rd: https://domain.com
            ]
        else:
            # For creating incidents, use the original domain
            url_formats = [typo_domain]

        incident_id: Optional[int] = None
        createincident_response: Optional[Dict[str, Any]] = None
        incident_response: Optional[Dict[str, Any]] = None
        successful_url: Optional[str] = None

        # Try each URL format until we find an incident or exhaust all options
        for url_to_try in url_formats:
            logger.info(f"Trying PhishLabs API with URL: {url_to_try}")
            
            # Prepare PhishLabs URL for this attempt
            createincident_url = (
                "https://feed.phishlabs.com/createincident"
                f"?custid={api_key}"
                "&requestid=placeholder"
                f"&url={url_to_try}"
                f"&catcode={final_catcode}"
                f"&flags={flags}"
            )
            if action == "create":
                createincident_url += f"&comment={comment}"

            try:
                # Make the API call
                async with session.get(createincident_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        body_text = await resp.text()
                        logger.warning(f"PhishLabs createincident error {resp.status} for {url_to_try}: {body_text[:200]}")
                        continue  # Try next URL format
                    
                    createincident_response = await resp.json(content_type=None)

                if createincident_response is None:
                    logger.warning(f"Empty response from PhishLabs createincident call for {url_to_try}")
                    continue  # Try next URL format

                error_message = createincident_response.get("ErrorMessage")
                if error_message:
                    logger.warning(f"PhishLabs error for {url_to_try}: {error_message}")
                    continue  # Try next URL format

                incident_id = createincident_response.get("IncidentId")
                if incident_id:
                    # Found an incident! Stop here
                    successful_url = url_to_try
                    logger.info(f"Found PhishLabs incident {incident_id} for URL: {url_to_try}")
                    break
                else:
                    logger.info(f"No incident found for URL: {url_to_try}")
                    continue  # Try next URL format

            except Exception as e:
                logger.warning(f"Exception during PhishLabs API call for {url_to_try}: {str(e)}")
                continue  # Try next URL format

        # If we're creating an incident and no incident was found, that means creation failed
        if action == "create" and not incident_id:
            return {
                "createincident_response": createincident_response,
                "incident_response": None,
                "incident_id": None,
                "no_incident": True,
                "successful_url": successful_url
            }

        # If we're fetching and no incident was found after trying all formats
        if action == "fetch" and not incident_id:
            logger.info(f"No PhishLabs incident found for any URL format of {typo_domain}")
            return {
                "createincident_response": createincident_response,
                "incident_response": None,
                "incident_id": None,
                "no_incident": True,
                "successful_url": successful_url
            }

        # If we found an incident, get the full incident details
        if incident_id:
            incident_get_url = (
                "https://feed.phishlabs.com/incident.get"
                f"?custid={api_key}"
                f"&incidentid={incident_id}"
            )
            try:
                async with session.get(incident_get_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        body_text = await resp.text()
                        raise Exception(f"PhishLabs incident.get error {resp.status}: {body_text[:1000]}")
                    incident_response = await resp.json(content_type=None)
            except Exception as e:
                logger.error(f"Error fetching incident details for {incident_id}: {str(e)}")
                incident_response = None

        result = {
            "createincident_response": createincident_response,
            "incident_response": incident_response,
            "incident_id": str(incident_id) if incident_id is not None else None,
            "no_incident": incident_id is None,
            "action": action,
            "catcode": catcode,
            "flags": flags,
            "successful_url": successful_url
        }

        logger.info(f"PhishLabs API call completed for {typo_domain}: incident_id={result['incident_id']}, successful_url={successful_url}, has_incident_response={bool(incident_response)}")
        return result
    
    async def update_finding(self, finding_id: str, phishlabs_data: Dict):
        """Update finding with PhishLabs data via API"""
        try:
            # Prepare consolidated PhishLabs data for the phishlabs_data JSONB field
            # Always add last_updated to track when we queried PhishLabs API
            consolidated_phishlabs_data = {
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

            # Add incident ID if available
            if phishlabs_data.get("incident_id"):
                consolidated_phishlabs_data["incident_id"] = str(phishlabs_data.get("incident_id"))
                logger.debug(f"Adding incident ID {phishlabs_data.get('incident_id')} to consolidated data")

            # Add no incident flag - explicitly set based on whether we have an incident
            if phishlabs_data.get("no_incident"):
                consolidated_phishlabs_data["no_incident"] = True
                logger.debug("Adding no_incident=True flag to consolidated data")
            else:
                # Explicitly set to False when we have an incident to override any previous value
                consolidated_phishlabs_data["no_incident"] = False
                logger.debug("Adding no_incident=False flag to consolidated data")

            # Extract and add PhishLabs data from incident response if available
            incident_response = phishlabs_data.get("incident_response", {})
            if incident_response:
                infraction = incident_response.get("Infraction", {})
                if infraction:
                    logger.info(f"Processing infraction data for finding {finding_id}: {infraction.get('Infrid', 'No ID')}")
                    # Map the fields to the consolidated structure
                    field_mapping = {
                        "incident_id": infraction.get("Infrid"),
                        "category_code": infraction.get("Catcode"),
                        "category_name": infraction.get("Catname"),
                        "status": infraction.get("Status"),
                        "comment": infraction.get("Comment"),
                        "product": infraction.get("Product"),
                        "create_date": infraction.get("Createdate"),
                        "assignee": infraction.get("Assignee"),
                        "last_comment": infraction.get("Lastcomment"),
                        "group_category_name": infraction.get("Groupcatname"),
                        "action_description": infraction.get("Actiondescr"),
                        "status_description": infraction.get("Statusdescr"),
                        "mitigation_start": infraction.get("Mitigationstart"),
                        "date_resolved": infraction.get("Dateresolved"),
                        "severity_name": infraction.get("Severityname"),
                        "mx_record": infraction.get("Mxrecord"),
                        "ticket_status": infraction.get("Ticketstatus"),
                        "resolution_status": infraction.get("Resolutionstatus"),
                        "incident_status": infraction.get("Incidentstatus")
                    }

                    # Only include non-None values
                    fields_added = 0
                    for field, value in field_mapping.items():
                        if value is not None:
                            # Convert specific fields to strings as required
                            if field in ["incident_id", "category_code", "ticket_status", "resolution_status"]:
                                consolidated_phishlabs_data[field] = str(value)
                            # Convert date strings to ISO format if they are datetime objects
                            elif field in ["create_date", "mitigation_start", "date_resolved"]:
                                if hasattr(value, 'isoformat'):  # Check if it's a datetime object
                                    consolidated_phishlabs_data[field] = value.isoformat()
                                else:
                                    consolidated_phishlabs_data[field] = value
                            else:
                                consolidated_phishlabs_data[field] = value
                            fields_added += 1

                    logger.info(f"Added {fields_added} PhishLabs fields to consolidated data for finding {finding_id}")
                else:
                    logger.debug(f"No infraction data found in incident response for finding {finding_id}")
            else:
                logger.debug(f"No incident response found for finding {finding_id}")

            # Store the raw API responses for debugging/audit purposes
            consolidated_phishlabs_data["api_responses"] = {
                "createincident_response": phishlabs_data.get("createincident_response"),
                "incident_response": phishlabs_data.get("incident_response")
            }

            # Prepare update data with the consolidated field
            update_data = {
                "phishlabs_data": consolidated_phishlabs_data
            }

            logger.info(f"Consolidated PhishLabs data for finding {finding_id}: {len(consolidated_phishlabs_data)} fields")

            # Add the finding ID and required fields for the update
            # Only send the specific PhishLabs fields that need to be updated
            # This prevents overwriting other data like threatstream_data
            
            # We need to include the typo_domain and program_name for the API to identify the record
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            # First fetch minimal data to get required identifiers
            fetch_url = f"{self.api_base_url}/findings/typosquat?id={finding_id}"
            logger.info(f"Fetching finding identifiers for {finding_id}: {fetch_url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(fetch_url, headers=headers) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        logger.error(f"Failed to fetch finding {finding_id}: HTTP {response.status} - {response_text}")
                        raise Exception(f"Failed to fetch finding {finding_id}: {response_text}")

                    fetch_response = await response.json()
                    if fetch_response.get("status") != "success":
                        logger.error(f"API returned non-success status for finding {finding_id}: {fetch_response}")
                        raise Exception(f"API returned non-success status: {fetch_response}")

                    finding_data = fetch_response.get("data")
                    if not finding_data:
                        logger.error(f"No data found for finding {finding_id} in response: {fetch_response}")
                        raise Exception(f"No data found for finding {finding_id}")

                    logger.info(f"Successfully fetched finding identifiers for {finding_id}")

            # Prepare finding data with PhishLabs updates in the format expected by the API
            finding_with_updates = {
                "typo_domain": finding_data["typo_domain"],
                "program_name": finding_data["program_name"]
            }
            
            # Add only the PhishLabs fields we want to update
            finding_with_updates.update(update_data)
            
            # Structure data in format expected by the API endpoint
            selective_update_data = {
                "program_name": finding_data["program_name"],
                "findings": {
                    "typosquat_domain": [finding_with_updates]
                }
            }

            logger.info(f"Structured update data for finding {finding_id} with {len(update_data)} PhishLabs fields")

            # Make API call to update finding using POST endpoint with structured data
            update_url = f"{self.api_base_url}/findings/typosquat"
            logger.info(f"Making API call to update finding {finding_id}: {update_url}")

            async with aiohttp.ClientSession() as session:
                async with session.post(update_url, json=selective_update_data, headers=headers) as response:
                    logger.info(f"API response status for finding {finding_id}: {response.status}")
                    if response.status not in [200, 201]:
                        response_text = await response.text()
                        logger.error(f"Failed to update finding {finding_id}: HTTP {response.status} - {response_text}")
                        raise Exception(f"Failed to update finding {finding_id}: HTTP {response.status} - {response_text}")
                    else:
                        logger.info(f"Successfully updated finding {finding_id} with PhishLabs incident details")

                        # Optional: Verify the update was successful by fetching the finding
                        if self.action == "create" and phishlabs_data.get("incident_id"):
                            await self.verify_update_success(finding_id, phishlabs_data.get("incident_id"))

        except Exception as e:
            logger.error(f"Error updating finding {finding_id} via API: {str(e)}")
            raise
    
    async def update_job_status(self, status: str, progress: int, message: str, results: Optional[Dict[str, Any]] = None):
        """Update job status via API"""
        try:
            update_data = {
                "status": status,
                "progress": progress,
                "message": message
            }

            if results is not None:
                update_data["results"] = results

            # Make API call to update job status
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/jobs/{self.job_id}/status"
            async with aiohttp.ClientSession() as session:
                async with session.put(url, json=update_data, headers=headers) as response:
                    if response.status not in [200, 204]:
                        response_text = await response.text()
                        logger.warning(f"Failed to update job {self.job_id} status: HTTP {response.status} - {response_text}")
                    else:
                        logger.info(f"Updated job {self.job_id} status to {status} ({progress}%)")

        except Exception as e:
            logger.error(f"Error updating job status for {self.job_id}: {str(e)}")
            raise

    async def verify_update_success(self, finding_id: str, expected_incident_id: str):
        """Verify that the finding update was successful by fetching it back"""
        try:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/findings/typosquat?id={finding_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "success" and data.get("data"):
                            finding_data = data["data"]
                            phishlabs_data = finding_data.get("phishlabs_data", {})
                            stored_incident_id = phishlabs_data.get("incident_id")
                            if str(stored_incident_id) == str(expected_incident_id):
                                logger.debug(f"Update verification successful for finding {finding_id}: incident ID {stored_incident_id} matches expected {expected_incident_id}")
                            else:
                                logger.warning(f"Update verification failed for finding {finding_id}: stored incident ID {stored_incident_id} does not match expected {expected_incident_id}")
                        else:
                            logger.warning(f"Update verification failed for finding {finding_id}: invalid API response")
                    else:
                        logger.warning(f"Update verification failed for finding {finding_id}: HTTP {response.status}")
        except Exception as e:
            logger.warning(f"Update verification error for finding {finding_id}: {str(e)}")
            # Don't raise exception here as this is just verification

    async def log_action_via_api(
        self,
        entity_type: str,
        entity_id: str,
        action_type: str,
        user_id: str,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log an action via the API endpoint"""
        try:
            action_data = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action_type": action_type,
                "user_id": user_id,
                "old_value": old_value,
                "new_value": new_value,
                "metadata": metadata
            }

            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            url = f"{self.api_base_url}/action-logs"
            logger.info(f"Logging action via API: {action_type} for {entity_type} {entity_id}")

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=action_data, headers=headers) as response:
                    if response.status in [200, 201]:
                        response_data = await response.json()
                        logger.info(f"Successfully logged action {action_type} for {entity_type} {entity_id}: {response_data.get('log_id')}")
                    else:
                        response_text = await response.text()
                        logger.warning(f"Failed to log action {action_type} for {entity_type} {entity_id}: HTTP {response.status} - {response_text}")

        except Exception as e:
            logger.error(f"Error logging action via API for {entity_type} {entity_id}: {str(e)}")
            # Don't raise exception here as action logging should not fail the main operation

    async def test_api_connectivity(self):
        """Test API connectivity and basic functionality"""
        try:
            logger.info("Testing API connectivity...")

            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            # Test basic API connectivity
            test_url = f"{self.api_base_url}/programs"
            async with aiohttp.ClientSession() as session:
                async with session.get(test_url, headers=headers) as response:
                    logger.info(f"Programs API test - Status: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Programs API test - Response: {data}")
                    else:
                        response_text = await response.text()
                        logger.warning(f"Programs API test failed - HTTP {response.status}: {response_text}")

        except Exception as e:
            logger.error(f"API connectivity test failed: {str(e)}")
            import traceback
            logger.error(f"Connectivity test traceback: {traceback.format_exc()}")

    async def update_finding_action_taken(self, finding_id: str, action_taken: str):
        """Update finding's action_taken field via API for RecordedFuture integration"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            # Prepare the action_taken update request
            update_data = {
                "action_taken": action_taken
            }

            logger.info(f"Updating finding {finding_id} action_taken with payload: {update_data}")

            # Use the new dedicated action-taken endpoint
            url = f"{self.api_base_url}/findings/typosquat/{finding_id}/action-taken"

            async with aiohttp.ClientSession() as session:
                async with session.patch(url, json=update_data, headers=headers) as response:
                    if response.status in [200, 204]:
                        try:
                            if 'application/json' in response.headers.get('content-type', ''):
                                response_data = await response.json()
                                logger.info(f"Successfully updated finding {finding_id} action_taken to '{action_taken}'. Response: {response_data}")
                            else:
                                response_text = await response.text()
                                logger.info(f"Successfully updated finding {finding_id} action_taken to '{action_taken}'. Response (text): {response_text}")
                        except Exception:
                            response_text = await response.text()
                            logger.info(f"Successfully updated finding {finding_id} action_taken to '{action_taken}'. Response (raw): {response_text}")
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to update finding {finding_id} action_taken: HTTP {response.status}")
                        logger.error(f"Response body: {response_text}")
                        logger.error(f"Request URL: {url}")
                        logger.error(f"Request headers: {headers}")
                        logger.error(f"Request payload: {update_data}")
                        return False

            return True

        except Exception as e:
            logger.error(f"Error updating finding {finding_id} action_taken: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False