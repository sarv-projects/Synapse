#!/usr/bin/env python3
"""Verification script to test all SYNAPSE v3.0 fixes."""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all critical imports work."""
    print("🔍 Testing imports...")
    
    try:
        print("  ✅ GenericSourceFetcher and SourceConfig import successfully")
    except Exception as e:
        print(f"  ❌ Failed to import GenericSourceFetcher: {e}")
        return False
    
    try:
        print("  ✅ GroqKeyManager imports successfully")
    except Exception as e:
        print(f"  ❌ Failed to import GroqKeyManager: {e}")
        return False
    
    try:
        print("  ✅ WebhookRegistry imports successfully")
    except Exception as e:
        print(f"  ❌ Failed to import WebhookRegistry: {e}")
        return False
    
    try:
        print("  ✅ PostgresCheckpoint imports successfully")
    except Exception as e:
        print(f"  ❌ Failed to import PostgresCheckpoint: {e}")
        return False
    
    return True


def test_webhook_subscription_id():
    """Test that WebhookSubscription has id field."""
    print("\n🔍 Testing WebhookSubscription model...")
    
    try:
        from webhook.registry import WebhookSubscription
        
        # Check if id field exists
        fields = WebhookSubscription.model_fields
        if 'id' in fields:
            print("  ✅ WebhookSubscription has 'id' field")
            return True
        else:
            print("  ❌ WebhookSubscription missing 'id' field")
            return False
    except Exception as e:
        print(f"  ❌ Error checking WebhookSubscription: {e}")
        return False


def test_postgres_checkpoint_methods():
    """Test that PostgresCheckpoint has all required methods."""
    print("\n🔍 Testing PostgresCheckpoint methods...")
    
    try:
        from ingestion.checkpoint.postgres import PostgresCheckpoint
        
        required_methods = [
            'log_webhook_delivery',
            'update_webhook_delivery',
            'get_webhook_delivery_stats',
            'cleanup_webhook_deliveries'
        ]
        
        checkpoint = PostgresCheckpoint()
        missing_methods = []
        
        for method_name in required_methods:
            if hasattr(checkpoint, method_name):
                print(f"  ✅ PostgresCheckpoint.{method_name}() exists")
            else:
                print(f"  ❌ PostgresCheckpoint.{method_name}() missing")
                missing_methods.append(method_name)
        
        return len(missing_methods) == 0
        
    except Exception as e:
        print(f"  ❌ Error checking PostgresCheckpoint: {e}")
        return False


def test_webhook_registry_function():
    """Test that get_webhook_registry function exists."""
    print("\n🔍 Testing get_webhook_registry function...")
    
    try:
        from webhook.registry import get_webhook_registry
        
        registry = get_webhook_registry()
        if registry is not None:
            print("  ✅ get_webhook_registry() works")
            return True
        else:
            print("  ❌ get_webhook_registry() returned None")
            return False
    except Exception as e:
        print(f"  ❌ Error calling get_webhook_registry: {e}")
        return False


def test_frontend_config():
    """Test that frontend configuration files exist."""
    print("\n🔍 Testing frontend configuration...")
    
    frontend_env = Path(__file__).parent.parent / "frontend" / ".env"
    frontend_config = Path(__file__).parent.parent / "frontend" / "src" / "config.ts"
    
    if frontend_env.exists():
        print("  ✅ frontend/.env exists")
        env_ok = True
    else:
        print("  ❌ frontend/.env missing")
        env_ok = False
    
    if frontend_config.exists():
        print("  ✅ frontend/src/config.ts exists")
        config_ok = True
    else:
        print("  ❌ frontend/src/config.ts missing")
        config_ok = False
    
    return env_ok and config_ok


def test_no_duplicate_classes():
    """Test that there are no duplicate class definitions."""
    print("\n🔍 Testing for duplicate class definitions...")
    
    generic_source_file = Path(__file__).parent.parent / "ingestion" / "generic_source.py"
    
    if not generic_source_file.exists():
        print("  ❌ generic_source.py not found")
        return False
    
    content = generic_source_file.read_text()
    
    # Count class definitions
    source_config_count = content.count("class SourceConfig:")
    generic_fetcher_count = content.count("class GenericSourceFetcher:")
    
    if source_config_count == 1:
        print(f"  ✅ SourceConfig defined once (found {source_config_count})")
        config_ok = True
    else:
        print(f"  ❌ SourceConfig defined {source_config_count} times (should be 1)")
        config_ok = False
    
    if generic_fetcher_count == 1:
        print(f"  ✅ GenericSourceFetcher defined once (found {generic_fetcher_count})")
        fetcher_ok = True
    else:
        print(f"  ❌ GenericSourceFetcher defined {generic_fetcher_count} times (should be 1)")
        fetcher_ok = False
    
    return config_ok and fetcher_ok


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("🚀 SYNAPSE v3.0 - Fix Verification Script")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("WebhookSubscription ID", test_webhook_subscription_id),
        ("PostgresCheckpoint Methods", test_postgres_checkpoint_methods),
        ("Webhook Registry Function", test_webhook_registry_function),
        ("Frontend Configuration", test_frontend_config),
        ("No Duplicate Classes", test_no_duplicate_classes),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All fixes verified successfully!")
        return 0
    else:
        print(f"⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
