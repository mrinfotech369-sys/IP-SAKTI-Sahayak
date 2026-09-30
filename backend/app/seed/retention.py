"""Apply workspace retention policies. Usage: python -m app.seed.retention [--apply]"""
import json
import sys

from app.db import SessionLocal
from app.services.governance import purge_expired

if __name__ == "__main__":
    db = SessionLocal()
    res = purge_expired(db, dry_run="--apply" not in sys.argv)
    db.commit()
    print(json.dumps(res, indent=1))
