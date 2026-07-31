# Event Schemas

Add Pydantic event models in this directory.

## Convention

1. One event class per file
2. Class name: `{Entity}{Action}` (PascalCase)
3. `event_type`: `{domain}.{entity}.{action}` (snake_case)
4. All fields must have type annotations
5. Inherit from `skyrict_events.base.BaseEvent`

## Example

```python
# schemas/user_created.py
from skyrict_events.base import BaseEvent

class UserCreated(BaseEvent):
    """Emitted when a new user is registered."""
    event_type: str = "identity.user.created"
    user_id: str
    email: str
```

## Topic Naming

```
{domain}.{entity}.{action}

Examples:
  identity.user.created
  identity.auth.login_success
  inventory.stock.level_changed
  finance.journal_entry.posted
```
