import os
import asyncio
from typing import Optional, List
from loguru import logger
import tweepy

class TwitterClient:
    """
    Client for interacting with X (Twitter) API v2 using Tweepy.
    Handles authentication, text composition, and thread splitting.
    """

    def __init__(self):
        self.enabled = str(os.getenv("SAPPHIRE_MEDIA_TWITTER_ENABLED", "true")).lower() == "true"
        self.api_key = os.getenv("SAPPHIRE_TWITTER_API_KEY", "").strip()
        self.api_secret = os.getenv("SAPPHIRE_TWITTER_API_SECRET", "").strip()
        self.access_token = os.getenv("SAPPHIRE_TWITTER_ACCESS_TOKEN", "").strip()
        self.access_secret = os.getenv("SAPPHIRE_TWITTER_ACCESS_SECRET", "").strip()
        self.bearer_token = os.getenv("SAPPHIRE_TWITTER_BEARER_TOKEN", "").strip()
        
        self.client: Optional[tweepy.Client] = None
        self.ready = False
        self.handle = os.getenv("SAPPHIRE_TWITTER_HANDLE", "")

    async def start(self):
        """Initialize the Tweepy client."""
        if not self.enabled:
            logger.info("🚫 Twitter automation disabled via config.")
            return

        if not all([self.api_key, self.api_secret, self.access_token, self.access_secret]):
            logger.warning("⚠️ Twitter API credentials missing. Twitter automation will be unavailable.")
            return

        try:
            # Initialize Tweepy Client for API v2
            self.client = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_secret,
                wait_on_rate_limit=True
            )
            
            # Verify credentials by fetching own user
            # Run is_blocking because tweepy is synchronous by default, usually wrap in executor if heavy
            # But initialization is one-off.
            # me = self.client.get_me()
            # self.handle = me.data.username
            
            self.ready = True
            logger.info(f"✅ TwitterClient initialized. Handle: @{self.handle}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize TwitterClient: {e}")
            self.ready = False

    async def post(self, text: str) -> Optional[str]:
        """
        Post a tweet or thread.
        
        Args:
            text: Content to tweet.
            
        Returns:
            ID of the (first) tweet, or None if failed.
        """
        if not self.ready or not self.client:
            logger.warning("⚠️ TwitterClient not ready. Cannot post.")
            raise RuntimeError("TwitterClient not ready")

        # Split into thread if necessary
        tweets = self._split_thread(text)
        
        try:
            # Tweepy calls are synchronous, so we run them in a thread to avoid blocking the event loop
            return await asyncio.to_thread(self._post_thread_sync, tweets)
        except Exception as e:
            logger.error(f"❌ Error posting to Twitter: {e}")
            raise e

    def _post_thread_sync(self, tweets: List[str]) -> str:
        """Synchronous implementation of posting a thread."""
        first_id = None
        previous_id = None
        
        for i, tweet_text in enumerate(tweets):
            response = self.client.create_tweet(
                text=tweet_text,
                in_reply_to_tweet_id=previous_id
            )
            
            if response.data:
                tweet_id = response.data['id']
                if i == 0:
                    first_id = tweet_id
                previous_id = tweet_id
                logger.info(f"🐦 Tweet posted: {tweet_id}")
            else:
                raise Exception("Empty response from Twitter API")
                
        return first_id

    def _split_thread(self, text: str, limit: int = 280) -> List[str]:
        """Split long text into a thread of tweets."""
        if len(text) <= limit:
            return [text]
            
        words = text.split()
        tweets = []
        current_tweet = ""
        
        for word in words:
            # Check length + space
            if len(current_tweet) + len(word) + 1 <= limit:
                current_tweet += (" " if current_tweet else "") + word
            else:
                tweets.append(current_tweet)
                current_tweet = word
                
        if current_tweet:
            tweets.append(current_tweet)
            
        # Add thread counter (1/X) if multiple tweets? 
        # For simplicity, keeping it raw for now, agents usually format well.
        return tweets
