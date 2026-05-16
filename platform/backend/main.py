import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import boto3
from botocore.config import Config as BotocoreConfig
import pymysql
+from dbutils.pooled_db import PooledDB
 from fastapi import Depends, FastAPI, Header, HTTPException, status, BackgroundTasks
 from fastapi.middleware.cors import CORSMiddleware
 from pydantic import BaseModel, ConfigDict, EmailStr, Field
@@
-DB_HOST = os.getenv("DB_HOST", "database-1.ctkcsksi0yjl.ap-south-1.rds.amazonaws.com")
-DB_PORT = int(os.getenv("DB_PORT", "3306"))
-DB_NAME = os.getenv("DB_NAME", "bug_daddy")
-DB_USER = os.getenv("DB_USER", "bug_daddy")
-DB_PASSWORD = os.getenv("DB_PASSWORD", "bug_daddy")
+DB_HOST = os.getenv("DB_HOST", "database-1.ctkcsksi0yjl.ap-south-1.rds.amazonaws.com")
+DB_PORT = int(os.getenv("DB_PORT", "3306"))
+DB_NAME = os.getenv("DB_NAME", "bug_daddy")
+DB_USER = os.getenv("DB_USER", "bug_daddy")
+DB_PASSWORD = os.getenv("DB_PASSWORD", "bug_daddy")
@@
-def get_db():
-    return pymysql.connect(
-        host=DB_HOST,
-        port=DB_PORT,
-        user=DB_USER,
-        password=DB_PASSWORD,
-        database=DB_NAME,
-        cursorclass=pymysql.cursors.DictCursor,
-        autocommit=True,
-        connect_timeout=10,
-    )
+# Global connection pool (initialized at startup)
+db_pool: PooledDB | None = None
+
+
+def init_db_pool() -> None:
+    """Initialise a thread‑safe connection pool.
+
+    The pool size is deliberately modest (max 20 connections) to stay well
+    within typical RDS Proxy limits while still providing reuse across
+    concurrent FastAPI requests. Adjust ``maxconnections`` via an environment
+    variable if needed.
+    """
+    global db_pool
+    if db_pool is not None:
+        return
+    max_conns = int(os.getenv("DB_POOL_MAX_CONNECTIONS", "20"))
+    db_pool = PooledDB(
+        creator=pymysql,
+        maxconnections=max_conns,
+        mincached=5,
+        maxcached=10,
+        blocking=True,
+        host=DB_HOST,
+        port=DB_PORT,
+        user=DB_USER,
+        password=DB_PASSWORD,
+        database=DB_NAME,
+        cursorclass=pymysql.cursors.DictCursor,
+        autocommit=True,
+        connect_timeout=10,
+    )
+
+
+def get_db():
+    """Acquire a connection from the pool.
+
+    Callers should close the connection when done – ``conn.close()`` returns the
+    connection to the pool rather than terminating it.
+    """
+    if db_pool is None:
+        # Fallback – initialise lazily if startup hook failed for any reason.
+        init_db_pool()
+    return db_pool.connection()
*** End Patch***
*** Begin Patch
*** Update File: platform/backend/requirements.txt
@@
 pymysql==1.1.2
 email-validator==2.2.0
 boto3==1.42.90
 requests>=2.31.0
+DBUtils==3.0.2
*** End Patch***