"""Database connection settings, read from environment variables only.

No password is ever hardcoded. Set these before running the server or the
seed script (PowerShell: $env:RAILWAY_DB_PASSWORD = '...'):

  RAILWAY_DB_HOST      default 127.0.0.1
  RAILWAY_DB_PORT      default 3306
  RAILWAY_DB_USER      default root
  RAILWAY_DB_PASSWORD  required, no default
  RAILWAY_DB_NAME      default RailwayReservationDB
"""
import os
import sys

DB_HOST = os.environ.get("RAILWAY_DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("RAILWAY_DB_PORT", "3306"))
DB_USER = os.environ.get("RAILWAY_DB_USER", "root")
DB_PASSWORD = os.environ.get("RAILWAY_DB_PASSWORD")
DB_NAME = os.environ.get("RAILWAY_DB_NAME", "RailwayReservationDB")

if not DB_PASSWORD:
    sys.stderr.write(
        "ERROR: RAILWAY_DB_PASSWORD is not set. Set it in the environment before "
        "starting the server, e.g. (PowerShell): $env:RAILWAY_DB_PASSWORD = 'yourpassword'\n"
    )
    sys.exit(1)
