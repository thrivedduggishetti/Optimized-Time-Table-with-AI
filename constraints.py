from typing import Dict, List, Any

def get_enabled_hard_constraints(admin_id: int) -> Dict[str, bool]:
    """Returns a mapping of hard constraint codes to boolean enabled state."""
    import database
    rules = database.get_hard_constraints(admin_id)
    return {r['code']: bool(r['is_enabled']) for r in rules}

def get_enabled_soft_constraints(admin_id: int) -> Dict[str, Dict[str, Any]]:
    """Returns a mapping of soft constraint codes to dict with 'enabled' and 'weight'."""
    import database
    rules = database.get_soft_constraints(admin_id)
    return {r['code']: {'enabled': bool(r['is_enabled']), 'weight': int(r['weight'])} for r in rules}
