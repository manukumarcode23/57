"""End-to-end encryption utilities using RSA public-key cryptography"""
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
import base64
import json
import os
from typing import Dict, Any, Tuple


class EncryptionManager:
    """Manages RSA public-key encryption for secure credential transmission"""
    
    def __init__(self):
        """Initialize encryption manager with RSA key pair"""
        env_private_key = os.environ.get('RSA_PRIVATE_KEY')
        
        if env_private_key:
            self.private_key = serialization.load_pem_private_key(
                env_private_key.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
        else:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
        
        self.public_key = self.private_key.public_key()
    
    def get_public_key_pem(self) -> str:
        """
        Get the public key in PEM format for client-side encryption
        
        Returns:
            Base64-encoded public key in PEM format
        """
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode('utf-8')
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """
        Decrypt data using RSA private key with OAEP padding
        
        Args:
            encrypted_data: Base64-encoded encrypted data
        
        Returns:
            Decrypted plain text data
        
        Raises:
            ValueError: If decryption fails
        """
        try:
            ciphertext = base64.b64decode(encrypted_data)
            
            plaintext = self.private_key.decrypt(
                ciphertext,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            return plaintext.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")
    
    def decrypt_json(self, encrypted_data: str) -> Dict[str, Any]:
        """
        Decrypt and parse JSON data
        
        Args:
            encrypted_data: Base64-encoded encrypted JSON data
        
        Returns:
            Parsed JSON data as dictionary
        """
        decrypted_text = self.decrypt_data(encrypted_data)
        return json.loads(decrypted_text)


# Global encryption manager instance
encryption_manager = EncryptionManager()


def get_public_key() -> str:
    """Get the public key for client-side encryption"""
    return encryption_manager.get_public_key_pem()


def decrypt(encrypted_data: str) -> str:
    """Decrypt data with the server's private key"""
    return encryption_manager.decrypt_data(encrypted_data)


def decrypt_json(encrypted_data: str) -> Dict[str, Any]:
    """Decrypt and parse JSON data"""
    return encryption_manager.decrypt_json(encrypted_data)
