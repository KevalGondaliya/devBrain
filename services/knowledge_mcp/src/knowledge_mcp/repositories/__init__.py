"""SQLAlchemy repositories: queries only, no business logic.

Every function here takes an already-open `AsyncSession` (from
`unit_of_work.py`) as its first parameter and returns ORM instances or
primitive values — never JSON-ready dicts (that's the services layer's
job). No function in this package makes a business decision (ranking,
merging, cascading) beyond the shape of the SQL query itself.
"""

from __future__ import annotations
