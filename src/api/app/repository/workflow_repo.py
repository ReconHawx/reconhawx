from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
from sqlalchemy import and_, or_, not_, desc, asc
from sqlalchemy.exc import SQLAlchemyError
from models.postgres import WorkflowLog
from db import get_db_session

logger = logging.getLogger(__name__)

class WorkflowRepository:
    @staticmethod
    async def create_workflow_log(log_object: Dict[str, Any]) -> str:
        """Create a new workflow log entry for each execution"""
        try:
            async with get_db_session() as db:
                # First, get the execution_id to check if log exists
                execution_id = log_object.get("execution_id", "")# or log_object.get("workflow_id", "")

                # Check if a log with this execution_id already exists
                existing_log = db.query(WorkflowLog).filter(
                    WorkflowLog.execution_id == execution_id
                ).first()

                # Map runner data format to WorkflowLog model format
                mapped_log_object = WorkflowRepository._map_runner_data_to_workflow_log(log_object, db, existing_log)
                
                if existing_log:
                    # Update the existing log (same execution, different status updates)
                    logger.info(f"Updating existing log for execution {mapped_log_object['execution_id']}")
                    # Remove timestamps from update data - let database handle them
                    mapped_log_object.pop('created_at', None)
                    mapped_log_object.pop('updated_at', None)

                    for key, value in mapped_log_object.items():
                        if hasattr(existing_log, key):
                            if key == 'workflow_steps':
                                # Special handling for workflow_steps - merge instead of replace
                                existing_steps = existing_log.workflow_steps or []
                                new_steps = value or []
                                merged_steps = WorkflowRepository._merge_workflow_steps(existing_steps, new_steps)
                                existing_log.workflow_steps = merged_steps
                                logger.debug(f"Merged workflow_steps: {len(existing_steps)} existing + {len(new_steps)} new = {len(merged_steps)} total")
                            elif key == 'task_execution_logs':
                                # Special handling for task_execution_logs - append array
                                existing_logs = existing_log.task_execution_logs or []
                                new_logs = value or []
                                if not isinstance(existing_logs, list):
                                    existing_logs = []
                                if not isinstance(new_logs, list):
                                    new_logs = []
                                existing_log.task_execution_logs = existing_logs + new_logs
                                logger.debug(f"Merged task_execution_logs: {len(existing_logs)} existing + {len(new_logs)} new = {len(existing_log.task_execution_logs)} total")
                            elif key == 'runner_pod_output':
                                # Special handling for runner_pod_output - append text
                                existing_output = existing_log.runner_pod_output or ""
                                new_output = value or ""
                                existing_log.runner_pod_output = existing_output + new_output
                                logger.debug(f"Appended runner_pod_output: {len(existing_output)} + {len(new_output)} = {len(existing_log.runner_pod_output)} chars")
                            else:
                                setattr(existing_log, key, value)

                    db.commit()
                    return str(existing_log.id)
                else:
                    # Create new workflow log entry for this execution
                    logger.debug("Creating workflow log - letting database handle timestamps")
                    workflow_log = WorkflowLog(**mapped_log_object)
                    db.add(workflow_log)
                    db.commit()
                    db.refresh(workflow_log)
                    logger.debug(f"After commit/refresh: created_at={workflow_log.created_at}, updated_at={workflow_log.updated_at}")
                    logger.debug(f"Created new workflow log entry for execution {mapped_log_object['execution_id']}")
                    return str(workflow_log.id)
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error creating/updating workflow: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating/updating workflow: {str(e)}")
            raise

    @staticmethod
    def _merge_workflow_steps(existing_steps: List[Dict], new_steps: List[Dict]) -> List[Dict]:
        """Merge workflow steps, preserving existing steps and updating/replacing with new ones"""
        if not existing_steps:
            return new_steps or []
        if not new_steps:
            return existing_steps

        # Create a dictionary of existing steps by step name for quick lookup
        existing_steps_dict = {}
        for step in existing_steps:
            if isinstance(step, dict) and len(step) == 1:
                step_name = list(step.keys())[0]
                existing_steps_dict[step_name] = step

        # Process new steps
        merged_steps = list(existing_steps)  # Start with all existing steps

        for new_step in new_steps:
            if isinstance(new_step, dict) and len(new_step) == 1:
                step_name = list(new_step.keys())[0]

                # Check if this step already exists
                if step_name in existing_steps_dict:
                    # Replace the existing step with the new one
                    for i, existing_step in enumerate(merged_steps):
                        if isinstance(existing_step, dict) and step_name in existing_step:
                            merged_steps[i] = new_step
                            break
                else:
                    # Add the new step
                    merged_steps.append(new_step)

        return merged_steps

    @staticmethod
    def _map_runner_data_to_workflow_log(log_object: Dict[str, Any], db_session, existing_log=None) -> Dict[str, Any]:
        """Map runner data format to WorkflowLog model format"""
        from models.postgres import Program
        
        mapped_data = {}
        
        # Map workflow_id (convert string to UUID if needed, or set to None for custom workflows)
        if "workflow_definition_id" in log_object:
            workflow_definition_id = log_object["workflow_definition_id"]
            if workflow_definition_id is None or workflow_definition_id == "":
                # Custom/adhoc workflow - no workflow definition ID
                mapped_data["workflow_id"] = None
            else:
                try:
                    import uuid
                    # Try to convert to UUID if it's a string
                    if isinstance(workflow_definition_id, str):
                        workflow_uuid = uuid.UUID(workflow_definition_id)
                    else:
                        workflow_uuid = workflow_definition_id
                    mapped_data["workflow_id"] = workflow_uuid
                except ValueError:
                    logger.error(f"Invalid workflow_id format: {workflow_definition_id}")
                    raise ValueError(f"Invalid workflow_id format: {workflow_definition_id}")
        
        # Map workflow_name
        if "workflow_name" in log_object:
            mapped_data["workflow_name"] = log_object["workflow_name"]
        
        # Map program_name to program_id
        if "program_name" in log_object:
            program_name = log_object["program_name"]
            # Look up program by name to get program_id
            program = db_session.query(Program).filter(Program.name == program_name).first()
            if program:
                mapped_data["program_id"] = program.id
            else:
                logger.error(f"Program not found with name: {program_name}")
                raise ValueError(f"Program not found with name: {program_name}")
        
        # Map result to status
        if "result" in log_object:
            mapped_data["status"] = log_object["result"]
        
        # Map workflow_steps
        if "workflow_steps" in log_object:
            mapped_data["workflow_steps"] = log_object["workflow_steps"]
        
        # Map workflow_definition
        if "workflow_definition" in log_object:
            mapped_data["workflow_definition"] = log_object["workflow_definition"]
        
        # Map runner_pod_output (append if existing)
        if "runner_pod_output" in log_object:
            new_output = log_object["runner_pod_output"]
            if existing_log and existing_log.runner_pod_output:
                # Append new output to existing output
                mapped_data["runner_pod_output"] = existing_log.runner_pod_output + new_output
            else:
                mapped_data["runner_pod_output"] = new_output
        
        # Map task_execution_logs (merge/append array)
        if "task_execution_logs" in log_object:
            new_logs = log_object["task_execution_logs"]
            if existing_log and existing_log.task_execution_logs:
                # Merge new logs with existing logs
                existing_logs = existing_log.task_execution_logs or []
                # Ensure both are lists
                if not isinstance(existing_logs, list):
                    existing_logs = []
                if not isinstance(new_logs, list):
                    new_logs = []
                mapped_data["task_execution_logs"] = existing_logs + new_logs
            else:
                mapped_data["task_execution_logs"] = new_logs if isinstance(new_logs, list) else []
        
        # Map execution_id
        if "execution_id" in log_object:
            mapped_data["execution_id"] = str(log_object["execution_id"])
        else:
            # Fallback: use workflow_id as execution_id for backward compatibility
            mapped_data["execution_id"] = str(log_object.get("workflow_id", "unknown"))
        
        # Add other fields that exist in the model
        for field in ["result_data"]:
            if field in log_object:
                mapped_data[field] = log_object[field]

        # Handle workflow timing
        now = datetime.utcnow()
        if not existing_log:  # New workflow log
            # Set started_at for new workflows
            mapped_data["started_at"] = now
            # Don't set completed_at for new workflows
        else:
            # For updates, check if workflow is completing
            if log_object.get("result") in ["success", "completed", "failed"]:
                mapped_data["completed_at"] = now

        # Note: created_at and updated_at are handled by database defaults
        # Do not explicitly set them in the mapping to allow database defaults to work
        # They will be set automatically when the record is inserted/updated

        return mapped_data
    
    @staticmethod   
    async def get_all_workflow_logs() -> List[Dict[str, Any]]:
        """Get all workflow logs"""
        try:
            async with get_db_session() as db:
                workflow_logs = db.query(WorkflowLog).all()
                return [workflow_log.to_dict() for workflow_log in workflow_logs]
        except SQLAlchemyError as e:
            logger.error(f"Database error getting all workflow logs: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting all workflow logs: {str(e)}")
            raise

    @staticmethod
    async def count_workflow_logs(query: Optional[Dict[str, Any]] = None) -> int:
        """Count the number of workflow logs matching the query"""
        try:
            async with get_db_session() as db:
                if query is None:
                    count = db.query(WorkflowLog).count()
                else:
                    # Convert MongoDB-style query to SQLAlchemy filter
                    filter_conditions = WorkflowRepository._convert_query_to_filter(query)
                    # Handle program_name joins if needed
                    db_query = db.query(WorkflowLog)
                    if any("program_name" in str(cond) for cond in filter_conditions):
                        from models.postgres import Program
                        db_query = db_query.join(Program)
                    count = db_query.filter(*filter_conditions).count()
                
                logger.info(f"Count result: {count} documents")
                return count
        except SQLAlchemyError as e:
            logger.error(f"Database error counting workflow logs: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error counting workflow logs: {str(e)}")
            raise

    @staticmethod
    async def get_workflow_logs_by_execution_id(execution_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow logs by execution ID (for custom workflows)"""
        try:
            async with get_db_session() as db:
                workflow_log = db.query(WorkflowLog).filter(
                    WorkflowLog.execution_id == execution_id
                ).first()

                if workflow_log:
                    result = workflow_log.to_dict()
                    return result
                return None
        except SQLAlchemyError as e:
            logger.error(f"Database error fetching workflow by execution_id: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching workflow by execution_id: {str(e)}")
            raise

    @staticmethod
    async def sanitize_query(query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize and validate the query to prevent injection and ensure safety
        """
        ALLOWED_OPERATORS = {
            "$and", "$or", "$not", "$nor",  # Logical operators
            "$eq", "$ne", "$gt", "$gte", "$lt", "$lte",  # Comparison operators
            "$in", "$nin",  # Array operators
            "$regex", "$options", "$exists", "$type",  # Element operators
            "$all", "$elemMatch", "$size"  # Array operators
        }
        
        def validate_query_dict(q: Dict[str, Any]) -> Dict[str, Any]:
            sanitized = {}
            for key, value in q.items():
                # Validate operators
                if key.startswith("$"):
                    if key not in ALLOWED_OPERATORS:
                        raise ValueError(f"Operator {key} is not allowed")
                    
                    # Handle nested queries in logical operators
                    if key in {"$and", "$or", "$nor"}:
                        if not isinstance(value, list):
                            raise ValueError(f"{key} operator requires a list of conditions")
                        sanitized[key] = [validate_query_dict(item) for item in value]
                    
                    # Handle $not operator
                    elif key == "$not":
                        if not isinstance(value, dict):
                            raise ValueError("$not operator requires a dictionary")
                        sanitized[key] = validate_query_dict(value)
                    
                    # Handle other operators
                    else:
                        sanitized[key] = value
                else:
                    # Handle nested fields
                    if isinstance(value, dict):
                        sanitized[key] = validate_query_dict(value)
                    else:
                        sanitized[key] = value
            
            return sanitized
        
        return validate_query_dict(query)

    @staticmethod
    def _convert_query_to_filter(query: Dict[str, Any]) -> List:
        """Convert MongoDB-style query to SQLAlchemy filter conditions"""
        conditions = []
        
        for key, value in query.items():
            if key.startswith("$"):
                # Handle MongoDB operators
                if key == "$and":
                    and_conditions = []
                    for item in value:
                        and_conditions.extend(WorkflowRepository._convert_query_to_filter(item))
                    conditions.append(and_(*and_conditions))
                elif key == "$or":
                    or_conditions = []
                    for item in value:
                        or_conditions.extend(WorkflowRepository._convert_query_to_filter(item))
                    conditions.append(or_(*or_conditions))
                elif key == "$not":
                    not_conditions = WorkflowRepository._convert_query_to_filter(value)
                    conditions.append(not_(*not_conditions))
                # Add more operator conversions as needed
            else:
                # Handle field comparisons
                if key == "program_name":
                    # Special handling for program_name - convert to program_id lookup
                    from models.postgres import Program
                    if isinstance(value, dict):
                        # Handle comparison operators for program_name
                        for op, op_value in value.items():
                            if op == "$eq":
                                conditions.append(WorkflowLog.program.has(Program.name == op_value))
                            elif op == "$ne":
                                conditions.append(~WorkflowLog.program.has(Program.name == op_value))
                            elif op == "$in":
                                conditions.append(WorkflowLog.program.has(Program.name.in_(op_value)))
                            elif op == "$nin":
                                conditions.append(~WorkflowLog.program.has(Program.name.in_(op_value)))
                            elif op == "$regex":
                                conditions.append(WorkflowLog.program.has(Program.name.ilike(f"%{op_value}%")))
                    else:
                        # Simple equality for program_name
                        conditions.append(WorkflowLog.program.has(Program.name == value))
                elif hasattr(WorkflowLog, key):
                    field = getattr(WorkflowLog, key)
                    if isinstance(value, dict):
                        # Handle comparison operators
                        for op, op_value in value.items():
                            if op == "$eq":
                                conditions.append(field == op_value)
                            elif op == "$ne":
                                conditions.append(field != op_value)
                            elif op == "$gt":
                                conditions.append(field > op_value)
                            elif op == "$gte":
                                conditions.append(field >= op_value)
                            elif op == "$lt":
                                conditions.append(field < op_value)
                            elif op == "$lte":
                                conditions.append(field <= op_value)
                            elif op == "$in":
                                conditions.append(field.in_(op_value))
                            elif op == "$nin":
                                conditions.append(~field.in_(op_value))
                            elif op == "$regex":
                                conditions.append(field.ilike(f"%{op_value}%"))
                    else:
                        # Simple equality
                        conditions.append(field == value)
        
        return conditions

    @staticmethod
    async def execute_query(query: Dict[str, Any], limit: Optional[int] = None, skip: int = 0, sort: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
        """
        Execute the sanitized query against the workflow logs with pagination support
        """
        try:
            logger.info(f"Executing query: {query}")
            async with get_db_session() as db:
                # Build query
                db_query = db.query(WorkflowLog)
                
                # Apply filters
                if query:
                    filter_conditions = WorkflowRepository._convert_query_to_filter(query)
                    # Handle program_name joins if needed
                    if any("program_name" in str(cond) for cond in filter_conditions):
                        from models.postgres import Program
                        db_query = db_query.join(Program)
                    db_query = db_query.filter(*filter_conditions)
                
                # Apply sorting
                if sort:
                    for field_name, direction in sort.items():
                        if field_name == "program_name":
                            # Special handling for program_name sorting
                            from models.postgres import Program
                            if direction == 1:
                                db_query = db_query.join(Program).order_by(asc(Program.name))
                            else:
                                db_query = db_query.join(Program).order_by(desc(Program.name))
                        elif hasattr(WorkflowLog, field_name):
                            field = getattr(WorkflowLog, field_name)
                            if direction == 1:
                                db_query = db_query.order_by(asc(field))
                            else:
                                db_query = db_query.order_by(desc(field))
                
                # Apply pagination
                if skip:
                    db_query = db_query.offset(skip)
                if limit is not None:
                    db_query = db_query.limit(limit)
                
                # Execute query
                workflow_logs = db_query.all()
                results = [workflow_log.to_dict() for workflow_log in workflow_logs]
                                
                return results
                
        except SQLAlchemyError as e:
            logger.error(f"Database error executing query: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            raise 