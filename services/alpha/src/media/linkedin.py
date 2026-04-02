import os
from typing import Optional

from loguru import logger


class LinkedInClient:
    """
    Client for interacting with LinkedIn API.
    Uses Official Documentation for publishing content and images.
    """

    def __init__(self):
        self.enabled = str(os.getenv("SAPPHIRE_MEDIA_LINKEDIN_ENABLED", "false")).lower() == "true"
        self.api_key = os.getenv("SAPPHIRE_LINKEDIN_CLIENT_ID", "")
        self.api_secret = os.getenv("SAPPHIRE_LINKEDIN_CLIENT_SECRET", "")
        self.access_token = os.getenv("SAPPHIRE_LINKEDIN_ACCESS_TOKEN", "")
        self.organization_urn = os.getenv("SAPPHIRE_LINKEDIN_ORG_URN", "")
        self.ready = False

    async def start(self):
        """Initialize Client."""
        if not self.enabled:
             logger.info("🚫 LinkedIn automation disabled via config.")
             return

        if self.access_token:
            self.ready = True
            logger.info("✅ LinkedInClient initialized.")
        else:
            logger.warning("⚠️ LinkedIn credentials missing.")

    async def post(self, text: str, image_url: Optional[str] = None) -> Optional[str]:
        """
        Post text and optionally an image to LinkedIn.
        
        Args:
            text: Post content.
            image_url: URL to an image.
            
        Returns:
            Post URN if successful, None otherwise.
        """
        if not self.ready:
            logger.warning("⚠️ LinkedInClient not ready.")
            return None
            
        logger.info(f"👔 [MOCK] Publishing to LinkedIn: {text[:50]}...")
        # Implementation TODO
        return "mock-linkedin-urn"
