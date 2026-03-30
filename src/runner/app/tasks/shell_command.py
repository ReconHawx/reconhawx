from typing import Any, Dict, List, Optional
from .base import Task, AssetType

class ShellCommand(Task):
    name = "shell_command"
    description = "Executes a shell command and returns its raw output"
    input_type = AssetType.STRING  # Input will be the command to execute
    output_types = [AssetType.STRING]  # Output will be the raw command output
    
    def get_timeout(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> int:
        return 300

    def get_last_execution_threshold(self) -> int:
        return 24
    
    def get_timestamp_hash(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> Optional[str]:
        return None

    def get_command(self, input_data: List[str], params: Optional[Dict[Any, Any]] = None) -> str:
        """
        Returns the command to be executed.
        
        Args:
            input_data (str): The shell command to execute
            
        Returns:
            str: The command to execute
        """
        if params is None:
            params = {}
        cmd_line = " ".join(params.get("command", []))
        if input_data:
            cmd_line = f"cat << 'EOF' | {cmd_line}\n{input_data}\nEOF"
        return cmd_line
    
    def parse_output(self, output: str, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """
        Returns the raw command output without any parsing.
        
        Args:
            output (str): The raw output from the command execution
            
        Returns:
            Dict[AssetType, List[Any]]: Dictionary with the raw output as a string asset
        """
        return {
            AssetType.STRING: [output]
        } 