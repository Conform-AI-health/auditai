import os
from pathlib import Path

BETA = os.environ.get("AUDITIA_BETA") == "1"
AI_ENABLED = os.environ.get("AUDITIA_IA_ENABLED", "1") == "1"
ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
ENV_FILE = PROJECT_ROOT / ".env"
STATIC = ROOT / "frontend" / "static"
PORT = int(os.environ.get("AUDITIA_PORT", os.environ.get("PORT", "5000")))
BASE = f"http://127.0.0.1:{PORT}"
REVIEW_LIMIT = min(12000,max(1,int(os.environ.get("AUDITIA_REVIEW_LIMIT","2000"))))
TERM_VERSION = "CFM-2454-2026-v1"
DOCUMENT_ASSETS = ROOT / "assets" / "documentos"
