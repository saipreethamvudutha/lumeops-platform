"""
HIPAA Compliance Services.

This package enforces HIPAA regulatory requirements at the application level:
- Minimum Necessary Rule: Only access/process the minimum PHI needed
- Access controls: Scope-based data access
- Audit requirements: Everything is logged
- Breach detection: Unusual access patterns trigger alerts

LEARNING NOTE:
    HIPAA's "minimum necessary" rule (45 CFR 164.502(b)) says:
    "A covered entity must make reasonable efforts to use, disclose,
    and request only the minimum amount of protected health information
    needed to accomplish the intended purpose."

    For LumeOps, this means:
    1. We strip identifiers because we DON'T NEED them for monitoring
    2. We encrypt clinical data because we only need it for quality checks
    3. We never expose raw data in API responses
    4. Dashboard queries only return aggregated data, never individual records
"""

from app.services.compliance.minimum_necessary import MinimumNecessaryFilter

__all__ = [
    "MinimumNecessaryFilter",
]
