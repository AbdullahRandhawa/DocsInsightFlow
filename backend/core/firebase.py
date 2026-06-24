import firebase_admin
from firebase_admin import credentials, firestore, auth
from core.config import settings
import logging

logger = logging.getLogger(__name__)

_firebase_app = None
_db = None


def init_firebase() -> None:
    """Initialize Firebase Admin SDK (idempotent)."""
    global _firebase_app, _db
    if _firebase_app is not None:
        return

    try:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": settings.FIREBASE_PROJECT_ID,
            "private_key_id": settings.FIREBASE_PRIVATE_KEY_ID,
            "private_key": settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n"),
            "client_email": settings.FIREBASE_CLIENT_EMAIL,
            "client_id": settings.FIREBASE_CLIENT_ID,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": settings.FIREBASE_CLIENT_CERT_URL,
        })
        _firebase_app = firebase_admin.initialize_app(cred)
        _db = firestore.client()
        logger.info("Firebase initialized successfully")
    except Exception as e:
        logger.error(f"Firebase initialization failed: {e}")
        raise


def get_db() -> firestore.Client:
    """Return Firestore client. Raises if not initialized."""
    if _db is None:
        raise RuntimeError("Firebase not initialized. Call init_firebase() first.")
    return _db


def verify_token(token: str) -> dict:
    """Verify Firebase ID token and return decoded claims."""
    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except auth.ExpiredIdTokenError:
        raise ValueError("Token has expired.")
    except auth.InvalidIdTokenError:
        raise ValueError("Invalid token.")
    except Exception as e:
        raise ValueError(f"Token verification failed: {e}")
