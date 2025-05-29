# app/crypto_utils.py
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii

def encrypt_aes(data: bytes) -> str:
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = pad(data, AES.block_size)
    encrypted = cipher.encrypt(padded)
    return binascii.hexlify(encrypted).decode()