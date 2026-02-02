#!/usr/bin/env python3
"""
CLI tool for managing API keys.
Usage: python -m app.cli_tools generate_key [--name NAME] [--rate-limit LIMIT]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_db, engine, Base
from app.auth import create_api_key, deactivate_api_key
from app.models import ApiKey


def generate_key(name: str = None, rate_limit: int = 1000):
    """Generate a new API key and print it."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    try:
        key, api_key = create_api_key(db, name=name, rate_limit=rate_limit)
        print("\n" + "=" * 60)
        print("API KEY GENERATED SUCCESSFULLY")
        print("=" * 60)
        print(f"\nKey:        {key}")
        print(f"Name:       {api_key.name or '(unnamed)'}")
        print(f"Rate Limit: {api_key.rate_limit} requests/hour")
        print(f"Created:    {api_key.created_at}")
        print("\n" + "=" * 60)
        print("IMPORTANT: Save this key securely. It cannot be retrieved later!")
        print("=" * 60 + "\n")
        return key
    finally:
        db.close()


def list_keys():
    """List all API keys."""
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    try:
        keys = db.query(ApiKey).all()
        if not keys:
            print("No API keys found.")
            return
        
        print("\nAPI Keys:")
        print("-" * 80)
        print(f"{'ID':<6} {'Name':<30} {'Rate Limit':<15} {'Active':<8} {'Last Used'}")
        print("-" * 80)
        for key in keys:
            last_used = key.last_used_at.strftime("%Y-%m-%d %H:%M") if key.last_used_at else "Never"
            print(f"{key.id:<6} {(key.name or '(unnamed)'):<30} {key.rate_limit:<15} {str(key.is_active):<8} {last_used}")
        print("-" * 80)
    finally:
        db.close()


def deactivate_key(key_id: int):
    """Deactivate an API key by ID."""
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    try:
        success = deactivate_api_key(db, key_id)
        if success:
            print(f"API key {key_id} deactivated successfully.")
        else:
            print(f"API key {key_id} not found.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="API Key Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Generate key command
    gen_parser = subparsers.add_parser("generate", help="Generate a new API key")
    gen_parser.add_argument("--name", "-n", help="Optional name for the key")
    gen_parser.add_argument("--rate-limit", "-r", type=int, default=1000, help="Rate limit (requests/hour)")
    
    # List keys command
    subparsers.add_parser("list", help="List all API keys")
    
    # Deactivate key command
    deact_parser = subparsers.add_parser("deactivate", help="Deactivate an API key")
    deact_parser.add_argument("id", type=int, help="ID of the key to deactivate")
    
    args = parser.parse_args()
    
    if args.command == "generate":
        generate_key(name=args.name, rate_limit=args.rate_limit)
    elif args.command == "list":
        list_keys()
    elif args.command == "deactivate":
        deactivate_key(args.id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
