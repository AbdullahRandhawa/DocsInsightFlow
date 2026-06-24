import cloudinary
import cloudinary.uploader
from core.config import settings
import logging

logger = logging.getLogger(__name__)


def init_cloudinary() -> None:
    """Configure Cloudinary SDK from env vars."""
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    logger.info("Cloudinary configured")


def upload_pdf(file_bytes: bytes, public_id: str, folder: str = "docsinsightflow", filename: str = "") -> dict:
    """
    Upload a document file to Cloudinary.
    Returns dict with url, public_id, bytes.
    """
    file_format = filename.split(".")[-1].lower() if filename else "pdf"
    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            public_id=public_id,
            folder=folder,
            resource_type="raw",
            format=file_format,
            overwrite=False,
        )
        logger.info(f"Uploaded PDF to Cloudinary: {result['secure_url']}")
        return {
            "url": result["secure_url"],
            "public_id": result["public_id"],
            "bytes": result.get("bytes", 0),
        }
    except Exception as e:
        logger.error(f"Cloudinary upload failed: {e}")
        raise


def delete_pdf(public_id: str) -> None:
    """Delete a PDF from Cloudinary by its public_id."""
    try:
        cloudinary.uploader.destroy(public_id, resource_type="raw")
        logger.info(f"Deleted PDF from Cloudinary: {public_id}")
    except Exception as e:
        logger.error(f"Cloudinary delete failed: {e}")
        raise
