"""
Shared utility functions for MongoDB-style query filtering and program-based access control.

This module provides reusable filtering logic that can be used across different repositories
(assets, findings) to maintain consistency and avoid code duplication.
"""

from sqlalchemy import and_, or_
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class QueryFilterUtils:
    """Utility class for MongoDB-style query filtering with program access control"""
    
    @staticmethod
    def apply_program_filter(base_query, query_filter: Dict[str, Any], program_model, needs_join: bool = True):
        """
        Apply program name filtering with proper handling of $in operator and empty lists.
        
        Args:
            base_query: SQLAlchemy query object
            query_filter: The filter conditions
            program_model: SQLAlchemy model for Program table
            needs_join: Whether to join the Program table (default: True)
            
        Returns:
            Tuple of (modified_query, list_of_conditions)
        """
        conditions = []
        should_join = False
        
        if 'program_name' in query_filter:
            value = query_filter['program_name']
            
            if isinstance(value, dict) and '$in' in value:
                # Handle $in operator for program_name
                program_list = value['$in']
                if isinstance(program_list, list):
                    if len(program_list) > 0:
                        conditions.append(program_model.name.in_(program_list))
                    else:
                        # Empty list means no programs should match - add impossible condition
                        conditions.append(program_model.name.in_([]))
                should_join = True
            elif isinstance(value, str):
                # Simple string equality
                conditions.append(program_model.name == value)
                should_join = True
        
        # Apply join if needed and requested
        if should_join and needs_join:
            base_query = base_query.join(program_model)
            
        return base_query, conditions
    
    @staticmethod
    def apply_regex_filter(field, filter_value: Any, case_insensitive: bool = False):
        """
        Apply regex filtering to a SQLAlchemy field.
        
        Args:
            field: SQLAlchemy column/field
            filter_value: Filter value (dict with $regex or string)
            case_insensitive: Whether to apply case-insensitive matching
            
        Returns:
            SQLAlchemy condition
        """
        if isinstance(filter_value, dict) and '$regex' in filter_value:
            pattern = filter_value.get('$regex', '')
            options = filter_value.get('$options', '')
            
            # Check if case insensitive option is set
            if 'i' in options or case_insensitive:
                return field.ilike(f'%{pattern}%')
            else:
                return field.like(f'%{pattern}%')
        elif isinstance(filter_value, str):
            # Simple equality
            return field == filter_value
        else:
            # Fallback to equality
            return field == filter_value
    
    @staticmethod
    def apply_logical_operators(base_query, query_filter: Dict[str, Any], filter_function):
        """
        Apply MongoDB-style logical operators ($and, $or) to a query.
        
        Args:
            base_query: SQLAlchemy query object
            query_filter: The filter conditions
            filter_function: Function to apply individual filters (should return conditions list)
            
        Returns:
            List of conditions
        """
        conditions = []
        
        if '$and' in query_filter:
            # Handle $and operator
            and_conditions = []
            for and_filter in query_filter['$and']:
                sub_conditions = filter_function(base_query, and_filter)
                if sub_conditions:
                    and_conditions.extend(sub_conditions)
            if and_conditions:
                conditions.append(and_(*and_conditions))
        
        if '$or' in query_filter:
            # Handle $or operator
            or_conditions = []
            for or_filter in query_filter['$or']:
                sub_conditions = filter_function(base_query, or_filter)
                if sub_conditions:
                    or_conditions.extend(sub_conditions)
            if or_conditions:
                conditions.append(or_(*or_conditions))
        
        return conditions
    
    @staticmethod
    def handle_empty_program_filter(query_filter: Dict[str, Any]) -> bool:
        """
        Check if the query filter contains an empty program list that should return no results.
        
        Args:
            query_filter: The filter conditions
            
        Returns:
            True if the filter should return no results (empty program list)
        """
        if 'program_name' in query_filter:
            value = query_filter['program_name']
            if isinstance(value, dict) and '$in' in value:
                program_list = value['$in']
                return isinstance(program_list, list) and len(program_list) == 0
        return False
    
    @staticmethod
    def optimize_empty_result_query(base_query):
        """
        Return a query that will produce no results efficiently.
        This is used when program filtering determines no results should be returned.
        
        Args:
            base_query: SQLAlchemy query object
            
        Returns:
            Modified query that returns no results
        """
        # Add a condition that will never be true
        return base_query.filter(False)


class ProgramAccessMixin:
    """
    Mixin class that can be used by repository classes to add program access control.
    
    This provides a consistent interface for applying program-based filtering
    across different repositories (assets, findings, etc.)
    """
    
    @staticmethod
    def apply_program_access_filter(base_query, query_filter: Dict[str, Any], program_model, needs_join: bool = True):
        """
        Apply program access filtering to a query based on program permissions.
        
        This method should be called after filter_by_user_programs has been applied
        to the query filter in the route handlers.
        
        Args:
            base_query: SQLAlchemy query object
            query_filter: MongoDB-style filter that may contain program restrictions
            program_model: SQLAlchemy Program model
            needs_join: Whether the Program table needs to be joined (default: True)
            
        Returns:
            Modified SQLAlchemy query with program access restrictions applied
        """
        # Check for empty program filter (no access)
        if QueryFilterUtils.handle_empty_program_filter(query_filter):
            return QueryFilterUtils.optimize_empty_result_query(base_query)
        
        # Apply program filtering
        modified_query, program_conditions = QueryFilterUtils.apply_program_filter(
            base_query, query_filter, program_model, needs_join
        )
        
        # Apply program conditions if any
        if program_conditions:
            modified_query = modified_query.filter(and_(*program_conditions))
        
        return modified_query


# Convenience functions for common use cases

def apply_mongodb_filters(base_query, query_filter: Dict[str, Any], field_mapping: Dict[str, Any]) -> List:
    """
    Apply MongoDB-style filters to a SQLAlchemy query using a field mapping.
    
    Args:
        base_query: SQLAlchemy query object
        query_filter: MongoDB-style filter conditions
        field_mapping: Dictionary mapping filter keys to SQLAlchemy fields
        
    Returns:
        List of SQLAlchemy conditions
    """
    conditions = []
    
    for key, value in query_filter.items():
        if key in field_mapping:
            field = field_mapping[key]
            conditions.append(QueryFilterUtils.apply_regex_filter(field, value))
        elif key.startswith('$'):
            # Skip logical operators, they're handled separately
            continue
        else:
            logger.warning(f"Unrecognized filter key: {key}")
    
    return conditions


def sanitize_mongodb_query(query: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a MongoDB-style query for security.
    
    Args:
        query: Raw query dictionary
        
    Returns:
        Sanitized query dictionary
    """
    # For now, return the query as-is since PostgreSQL is more secure
    # In the future, we might add more sophisticated sanitization
    return query