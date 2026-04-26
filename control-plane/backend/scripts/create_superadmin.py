"""
Generate the bcrypt hash for SUPERADMIN_PASSWORD in .env

Usage:
    python scripts/create_superadmin.py
    # Enter password when prompted → copy the hash to .env
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.auth import hash_password

password = input("Enter superadmin password: ").strip()
if not password:
    print("Password cannot be empty")
    sys.exit(1)

hashed = hash_password(password)
print(f"\nAdd this to your .env:\n")
print(f'SUPERADMIN_PASSWORD="{hashed}"')
