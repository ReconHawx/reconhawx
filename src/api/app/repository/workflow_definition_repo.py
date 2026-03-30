from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
from sqlalchemy import and_, desc
from sqlalchemy.exc import SQLAlchemyError
from models.postgres import Workflow, Program
from db import get_db_session
import uuid

logger = logging.getLogger(__name__)

class WorkflowDefinitionRepository:
    @staticmethod
    async def create_workflow_definition(workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new workflow definition"""
        try:
            async with get_db_session() as db:
                # Map program_name to program_id
                program_name = workflow_data.get("program_name")
                program_id = None
                
                if program_name:
                    program = db.query(Program).filter(Program.name == program_name).first()
                    if not program:
                        raise ValueError(f"Program not found with name: {program_name}")
                    program_id = program.id
                
                # Handle both old format (definition wrapper) and new format (direct fields)
                definition = workflow_data.get("definition", {})
                inputs = workflow_data.get("inputs", {})
                variables = workflow_data.get("variables", {})
                steps = workflow_data.get("steps", [])
                
                # If using old format with definition wrapper
                if definition and isinstance(definition, dict):
                    inputs = definition.get("inputs", inputs)
                    variables = definition.get("variables", variables)
                    steps = definition.get("steps", steps)
                
                # Create workflow definition
                workflow_definition = Workflow(
                    id=uuid.uuid4(),
                    name=workflow_data["name"],
                    program_id=program_id,  # Can be None for global workflows
                    description=workflow_data.get("description"),
                    variables=variables,
                    inputs=inputs,
                    steps={"steps": steps},  # Only store steps, not inputs/variables
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                db.add(workflow_definition)
                db.commit()
                db.refresh(workflow_definition)
                
                return WorkflowDefinitionRepository._to_dict(workflow_definition)
                
        except SQLAlchemyError as e:
            logger.error(f"Database error creating workflow definition: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating workflow definition: {str(e)}")
            raise

    @staticmethod
    async def get_workflow_definition(workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get a workflow definition by ID"""
        try:
            async with get_db_session() as db:
                # Try to parse as UUID
                try:
                    workflow_uuid = uuid.UUID(workflow_id)
                except ValueError:
                    logger.error(f"Invalid workflow ID format: {workflow_id}")
                    return None
                
                workflow = db.query(Workflow).filter(Workflow.id == workflow_uuid).first()
                
                if not workflow:
                    return None
                
                return WorkflowDefinitionRepository._to_dict(workflow)
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting workflow definition: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting workflow definition: {str(e)}")
            raise

    @staticmethod
    async def get_workflow_definitions(program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all workflow definitions, optionally filtered by program"""
        try:
            async with get_db_session() as db:
                query = db.query(Workflow)
                
                if program_name and program_name != 'all':
                    # Join with Program to filter by program name
                    query = query.join(Program).filter(Program.name == program_name)
                elif program_name == 'global':
                    # Filter for global workflows (no program)
                    query = query.filter(Workflow.program_id.is_(None))
                elif program_name == 'all':
                    # Get all workflows (both global and program-specific)
                    pass
                else:
                    # Default: get workflows accessible to user (global + user's programs)
                    # This will be handled by the API layer with proper permission checking
                    pass
                
                # Order by updated_at descending
                workflows = query.order_by(desc(Workflow.updated_at)).all()
                
                return [WorkflowDefinitionRepository._to_dict(workflow) for workflow in workflows]
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting workflow definitions: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting workflow definitions: {str(e)}")
            raise

    @staticmethod
    async def update_workflow_definition(workflow_id: str, workflow_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a workflow definition"""
        try:
            async with get_db_session() as db:
                # Try to parse as UUID
                try:
                    workflow_uuid = uuid.UUID(workflow_id)
                except ValueError:
                    logger.error(f"Invalid workflow ID format: {workflow_id}")
                    return None
                
                workflow = db.query(Workflow).filter(Workflow.id == workflow_uuid).first()
                
                if not workflow:
                    return None
                
                # Map program_name to program_id if provided
                program_name = workflow_data.get("program_name")
                if program_name:
                    program = db.query(Program).filter(Program.name == program_name).first()
                    if not program:
                        raise ValueError(f"Program not found with name: {program_name}")
                    workflow.program_id = program.id
                else:
                    # Set to None for global workflows
                    workflow.program_id = None
                
                # Handle both old format (definition wrapper) and new format (direct fields)
                definition = workflow_data.get("definition", {})
                inputs = workflow_data.get("inputs", {})
                variables = workflow_data.get("variables", {})
                steps = workflow_data.get("steps", [])
                
                # If using old format with definition wrapper
                if definition and isinstance(definition, dict):
                    inputs = definition.get("inputs", inputs)
                    variables = definition.get("variables", variables)
                    steps = definition.get("steps", steps)
                
                # Update fields
                workflow.name = workflow_data["name"]
                workflow.description = workflow_data.get("description")
                workflow.variables = variables
                workflow.inputs = inputs
                workflow.steps = {"steps": steps}  # Only store steps, not inputs/variables
                workflow.updated_at = datetime.utcnow()
                
                db.commit()
                db.refresh(workflow)
                
                return WorkflowDefinitionRepository._to_dict(workflow)
                
        except SQLAlchemyError as e:
            logger.error(f"Database error updating workflow definition: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error updating workflow definition: {str(e)}")
            raise

    @staticmethod
    async def delete_workflow_definition(workflow_id: str) -> bool:
        """Delete a workflow definition and all associated workflow logs (via CASCADE DELETE)"""
        try:
            async with get_db_session() as db:
                # Try to parse as UUID
                try:
                    workflow_uuid = uuid.UUID(workflow_id)
                except ValueError:
                    logger.error(f"Invalid workflow ID format: {workflow_id}")
                    return False
                
                workflow = db.query(Workflow).filter(Workflow.id == workflow_uuid).first()
                
                if not workflow:
                    return False
                
                # Delete the workflow - all associated workflow logs will be automatically deleted
                # due to the CASCADE DELETE constraint on workflow_logs.workflow_id
                db.delete(workflow)
                db.commit()
                
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting workflow definition: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting workflow definition: {str(e)}")
            raise

    @staticmethod
    async def check_name_conflict(name: str, program_name: Optional[str], exclude_id: Optional[str] = None) -> bool:
        """Check if a workflow name already exists in the same scope"""
        try:
            async with get_db_session() as db:
                # If program_name is provided, check for conflicts within that program
                if program_name:
                    program = db.query(Program).filter(Program.name == program_name).first()
                    if not program:
                        return False  # Program doesn't exist, so no conflict
                    
                    query = db.query(Workflow).filter(
                        and_(
                            Workflow.name == name,
                            Workflow.program_id == program.id
                        )
                    )
                else:
                    # For global workflows, check if name exists globally (no program)
                    query = db.query(Workflow).filter(
                        and_(
                            Workflow.name == name,
                            Workflow.program_id.is_(None)
                        )
                    )
                
                if exclude_id:
                    try:
                        exclude_uuid = uuid.UUID(exclude_id)
                        query = query.filter(Workflow.id != exclude_uuid)
                    except ValueError:
                        logger.error(f"Invalid exclude ID format: {exclude_id}")
                
                existing = query.first()
                return existing is not None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error checking name conflict: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error checking name conflict: {str(e)}")
            raise

    @staticmethod
    def _to_dict(workflow: Workflow) -> Dict[str, Any]:
        """Convert Workflow model instance to dictionary"""
        # Extract inputs, variables, and steps from the stored data
        inputs = workflow.inputs
        variables = workflow.variables
        steps = []
        
        # Extract steps from the stored structure
        if isinstance(workflow.steps, dict):
            steps = workflow.steps.get("steps", [])
        
        # Handle backward compatibility for old format where everything was in steps
        # Check if inputs/variables are empty and try to extract from steps
        if (not inputs or inputs == {}) and isinstance(workflow.steps, dict):
            inputs = workflow.steps.get("inputs", {})
        if (not variables or variables == {}) and isinstance(workflow.steps, dict):
            variables = workflow.steps.get("variables", {})
        
        # Ensure we always return the new flattened format
        return {
            "id": str(workflow.id),
            "name": workflow.name,
            "program_name": workflow.program.name if workflow.program else None,
            "description": workflow.description,
            "steps": steps,
            "variables": variables or {},
            "inputs": inputs or {},
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at
        } 