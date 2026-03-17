"""
Secure Solana Wallet Management for Sapphire AI Users
Stores encrypted Solana private keys in Firebase Firestore
"""

import base64
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet
from google.cloud import firestore
from solders.keypair import Keypair

logger = logging.getLogger(__name__)


class SolanaWalletManager:
    """
    Manages Solana wallets for authenticated users.

    Security features:
    - Private keys encrypted with Fernet (AES-128-CBC)
    - Stored in Firebase Firestore with user isolation
    - Never exposed in API responses
    - Auto-generated on first use
    """

    def __init__(self):
        """Initialize wallet manager with Firestore and encryption."""
        self.db = firestore.Client()
        self.collection = "solana_wallets"

        # Get encryption key from environment (must be 32-byte URL-safe base64-encoded)
        encryption_key = os.getenv("WALLET_ENCRYPTION_KEY")
        if not encryption_key:
            # Generate a key for development (DO NOT use in production)
            logger.warning("WALLET_ENCRYPTION_KEY not set, generating temporary key")
            encryption_key = Fernet.generate_key().decode()
            logger.warning(f"Generated key: {encryption_key}")
            logger.warning("Set this as WALLET_ENCRYPTION_KEY environment variable for production")

        self.cipher = Fernet(
            encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
        )

    def create_wallet(self, user_id: str) -> str:
        """
        Create new Solana wallet for user.

        Args:
            user_id: Firebase user ID

        Returns:
            Public key as string
        """
        # Generate new keypair
        keypair = Keypair()

        # Encrypt private key
        private_key_bytes = bytes(keypair)
        encrypted_key = self.cipher.encrypt(private_key_bytes)

        # Store in Firestore
        wallet_doc = {
            "public_key": str(keypair.pubkey()),
            "encrypted_private_key": base64.b64encode(encrypted_key).decode("utf-8"),
            "created_at": firestore.SERVER_TIMESTAMP,
            "chain": "solana",
        }

        self.db.collection(self.collection).document(user_id).set(wallet_doc)

        logger.info(f"Created Solana wallet for user {user_id}: {str(keypair.pubkey())}")

        return str(keypair.pubkey())

    def get_public_key(self, user_id: str) -> Optional[str]:
        """
        Get user's Solana public key.

        Args:
            user_id: Firebase user ID

        Returns:
            Public key as string, or None if wallet doesn't exist
        """
        doc = self.db.collection(self.collection).document(user_id).get()

        if not doc.exists:
            return None

        return doc.to_dict().get("public_key")

    def get_keypair(self, user_id: str) -> Keypair:
        """
        Retrieve user's Solana keypair (SECURE - only use server-side).

        Args:
            user_id: Firebase user ID

        Returns:
            Solders Keypair object

        Raises:
            ValueError: If wallet doesn't exist for user
        """
        doc = self.db.collection(self.collection).document(user_id).get()

        if not doc.exists:
            raise ValueError(f"No Solana wallet found for user {user_id}")

        data = doc.to_dict()
        encrypted_key = base64.b64decode(data["encrypted_private_key"])

        # Decrypt private key
        decrypted_key = self.cipher.decrypt(encrypted_key)

        # Reconstruct keypair
        keypair = Keypair.from_bytes(decrypted_key)

        logger.debug(f"Retrieved Solana keypair for user {user_id}")

        return keypair

    def get_or_create_wallet(self, user_id: str) -> str:
        """
        Get existing wallet or create new one.

        Args:
            user_id: Firebase user ID

        Returns:
            Public key as string
        """
        public_key = self.get_public_key(user_id)

        if public_key:
            return public_key

        return self.create_wallet(user_id)

    def delete_wallet(self, user_id: str) -> bool:
        """
        Delete user's Solana wallet (irreversible).

        Args:
            user_id: Firebase user ID

        Returns:
            True if deleted, False if wallet didn't exist
        """
        doc_ref = self.db.collection(self.collection).document(user_id)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        doc_ref.delete()
        logger.warning(f"Deleted Solana wallet for user {user_id}")

        return True


# Singleton instance
_wallet_manager: Optional[SolanaWalletManager] = None


def get_wallet_manager() -> SolanaWalletManager:
    """Get or create wallet manager singleton."""
    global _wallet_manager
    if _wallet_manager is None:
        _wallet_manager = SolanaWalletManager()
    return _wallet_manager


def get_user_solana_wallet(user_id: str) -> Keypair:
    """
    Convenience function to get user's Solana keypair.

    Args:
        user_id: Firebase user ID

    Returns:
        Solders Keypair for signing transactions
    """
    manager = get_wallet_manager()
    return manager.get_keypair(user_id)


def get_user_solana_address(user_id: str) -> str:
    """
    Get user's Solana public address.

    Args:
        user_id: Firebase user ID

    Returns:
        Public key as base58 string
    """
    manager = get_wallet_manager()
    return manager.get_or_create_wallet(user_id)
