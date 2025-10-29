# LEGACY: Google Vision SDK removed - this module is deprecated
# Use BiometryParser from app.services.biometry_parser instead

def google_ocr_image_or_pdf(path: str) -> str:
    """
    DEPRECATED: Legacy Google Cloud Vision OCR function.
    Use BiometryParser which uses PyTesseract instead.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("google_ocr_image_or_pdf called but is deprecated - use BiometryParser instead")
    return ""

def run_ocr(path: str) -> str:
    """
    DEPRECATED: Legacy OCR runner.
    Use BiometryParser from app.services.biometry_parser instead.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("run_ocr called but is deprecated - use BiometryParser instead")
    return ""
