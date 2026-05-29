#!/usr/bin/env python3
"""
Interactive environment setup for SYNAPSE v3.0
Helps configure all required API keys and services.
"""

import os
import sys
from pathlib import Path

def setup_environment():
    """Interactive setup for SYNAPSE environment variables."""
    
    print("🚀 SYNAPSE v3.0 Environment Setup")
    print("=" * 50)
    print("This script helps you configure all required services for SYNAPSE v3.0\n")
    
    env_file = Path(".env")
    
    # Load existing .env if it exists
    existing_env = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    existing_env[key.strip()] = value.strip()
    
    print("📋 Current configuration:")
    for key, value in existing_env.items():
        masked_value = mask_sensitive_value(key, value)
        print(f"  {key}={masked_value}")
    
    print("\n🔧 Configure the following services:")
    
    # Neo4j Aura
    print("\n1️⃣ Neo4j Aura (Free Tier)")
    print("   Get your free instance at: https://neo4j.com/cloud/aura-free")
    neo4j_uri = input("   Neo4j URI (neo4j+s://...): ").strip()
    neo4j_username = input("   Username (default: neo4j): ").strip() or "neo4j"
    neo4j_password = input("   Password: ").strip()
    
    # Groq API
    print("\n2️⃣ Groq API (Required)")
    print("   Get your API key at: https://console.groq.com/")
    groq_key = input("   Groq API Key: ").strip()
    
    # Gemini API (Optional)
    print("\n3️⃣ Gemini API (Optional)")
    print("   Get your API key at: https://aistudio.google.com/app/apikey")
    gemini_key = input("   Gemini API Key (press Enter to skip): ").strip()
    
    # GitHub Token (Recommended)
    print("\n4️⃣ GitHub Token (Recommended)")
    print("   Create at: https://github.com/settings/tokens")
    github_token = input("   GitHub Token (press Enter to skip): ").strip()
    
    # PostgreSQL (Neon.dev)
    print("\n5️⃣ PostgreSQL - Neon.dev (Free Tier)")
    print("   Get connection string at: https://neon.tech/")
    postgres_url = input("   PostgreSQL URL: ").strip()
    
    # Google Cloud Project (Firestore)
    print("\n6️⃣ Google Cloud Project (Firestore checkpointing — free tier)")
    print("   Create at: https://console.cloud.google.com/")
    gcp_project = input("   GCP Project ID: ").strip()

    # SYNAPSE Admin Key
    print("\n7️⃣ SYNAPSE Admin Key")
    synapse_key = input("   Admin Key (generate a strong one): ").strip()
    
    # Confirmation
    print("\n✅ Configuration Summary:")
    print(f"   Neo4j: {neo4j_uri}")
    print(f"   Groq: {'✅ Configured' if groq_key else '❌ Missing'}")
    print(f"   Gemini: {'✅ Configured' if gemini_key else '⚠️ Skipped'}")
    print(f"   GitHub: {'✅ Configured' if github_token else '⚠️ Skipped'}")
    print(f"   PostgreSQL: {'✅ Configured' if postgres_url else '❌ Missing'}")
    print(f"   GCP Project: {'✅ Configured' if gcp_project else '⚠️ Skipped'}")
    
    confirm = input("\n❓ Save this configuration to .env? (y/N): ").strip().lower()
    
    if confirm in ['y', 'yes']:
        save_environment_file(env_file, {
            'NEO4J_URI': neo4j_uri,
            'NEO4J_USERNAME': neo4j_username,
            'NEO4J_PASSWORD': neo4j_password,
            'GROQ_API_KEY': groq_key,
            'GEMINI_API_KEY': gemini_key,
            'GITHUB_TOKEN': github_token,
            'POSTGRES_URL': postgres_url,
            'GOOGLE_CLOUD_PROJECT': gcp_project,
            'GCP_PROJECT': gcp_project,
            'SYNAPSE_ADMIN_KEY': synapse_key,
            'API_VERSION': 'v1',
            'CORS_ORIGINS': 'http://localhost:5173,https://synapse.yourdomain.com',
            'LOG_LEVEL': 'INFO',
            'DEFAULT_DOMAIN': 'ai',
            'QUERY_CACHE_TTL_SECONDS': '3600',
            'MAX_QUERY_RESULTS': '50',
            'MAX_TRAVERSAL_DEPTH': '3',
        })
        
        print("\n✅ Environment saved to .env")
        print("\n🚀 Next steps:")
        print("1. Review the .env file")
        print("2. Test the configuration: python -c 'from schema.config import get_settings; print(get_settings())'")
        print("3. Start the backend: uvicorn api.main:app --reload")
        print("4. Start the frontend: cd frontend && npm run dev")
        
    else:
        print("\n❌ Configuration not saved")

def mask_sensitive_value(key: str, value: str) -> str:
    """Mask sensitive values for display."""
    if not value:
        return "❌ Not set"
    
    sensitive_keys = ['PASSWORD', 'KEY', 'TOKEN', 'URI', 'URL']
    if any(sensitive in key.upper() for sensitive in sensitive_keys):
        if len(value) > 8:
            return value[:4] + "..." + value[-4:]
        else:
            return "***"
    
    return value

def save_environment_file(env_file: Path, config: dict):
    """Save configuration to .env file."""
    with open(env_file, 'w') as f:
        f.write("# SYNAPSE v3.0 Environment Configuration\n")
        f.write("# Generated by setup_env.py\n\n")
        
        for key, value in config.items():
            if value:
                f.write(f"{key}={value}\n")
            else:
                f.write(f"{key}=\n")

if __name__ == "__main__":
    try:
        setup_environment()
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error during setup: {e}")
        sys.exit(1)
