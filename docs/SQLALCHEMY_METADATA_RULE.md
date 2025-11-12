# SQLAlchemy Metadata Naming Rule

## Critical Rule: Never Use `metadata` as a Column Name

### Problem
SQLAlchemy reserves the attribute name `metadata` for its internal `MetaData` object. Using `metadata` as a column name in declarative models causes an `InvalidRequestError`:

```
sqlalchemy.exc.InvalidRequestError: Attribute name 'metadata' is reserved
```

### Solution
When defining SQLAlchemy models, if you need a `metadata` column in your database:

1. **Define the column with a different Python attribute name**
2. **Use `mapped_column("metadata", ...)` to specify the actual database column name**

### Example (Correct Usage)
```python
from sqlalchemy import JSONB
from sqlalchemy.orm import Mapped, mapped_column

class Trade(Base):
    __tablename__ = "trades"

    # ❌ WRONG - This will cause InvalidRequestError
    # metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ✅ CORRECT - Use different attribute name, map to DB column
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
```

### Files Affected
- `cloud_trader/storage.py` - All model classes (Trade, Position, MarketSnapshot, AgentPerformance, AgentDecision)

### CI Protection
A startup check has been added to `cloudbuild.yaml` that imports all modules and confirms the SQLAlchemy models load without errors:

```yaml
# Test container startup and imports
- name: 'gcr.io/cloud-builders/docker'
  args:
    - 'run'
    - '--rm'
    - '--entrypoint'
    - 'python3'
    - 'us-central1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/cloud-trader:${BUILD_ID}'
    - '-c'
    - 'import sys; from cloud_trader.service import TradingService; from cloud_trader.storage import Trade, Position, MarketSnapshot; print("✅ All imports successful - SQLAlchemy metadata fix confirmed")'
```

### Prevention
- Always review model definitions for reserved SQLAlchemy attribute names
- Run the CI import test after any schema changes
- Consider adding this rule to your code review checklist
