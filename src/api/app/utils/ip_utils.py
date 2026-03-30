import re
from typing import List

def get_valid_ips(ips: List[str]) -> List[str]:
    """
    Filter a list of strings and return only the valid IP addresses.
    """
    return [ip for ip in ips if is_valid_ip(ip)]

def is_valid_ip(ip: str) -> bool:
    """
    Validate if a string is a valid IP address.
    """
    return re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip) is not None