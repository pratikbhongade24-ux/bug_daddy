import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import boto3
# import pymysql  # moved to lazy import in get_db()
from fastapi import Depends, FastAPI, Header, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ... (rest of the file unchanged up to get_db) ...

def get_db():
    """Create a new pymysql connection.
    The pymysql import is performed lazily to avoid import-time failures if the
    dependency is missing from the deployment package. This allows the Lambda to
    start and report a clear error only when a DB operation is attempted.
    """
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError(
            "pymysql is required for database access but is not installed. "
            "Ensure it is included in the Lambda deployment package."
        ) from exc
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10,
    )

# ... (rest of the file unchanged) ...