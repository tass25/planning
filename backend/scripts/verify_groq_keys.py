"""Quick script to verify which Groq API keys are valid.

Usage:
    python scripts/verify_groq_keys.py

Reads keys from the .env file and tests each one by making a minimal
chat completion call. Reports VALID / INVALID for each key.
"""

import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


def test_groq_key(key_name: str, api_key: str) -> bool:
    """Test a single Groq API key by making a minimal API call."""
    import httpx

    if not api_key:
        print(f"  {key_name}: [EMPTY] EMPTY (not set)")
        return False

    # Mask the key for display
    masked = api_key[:8] + "..." + api_key[-4:]

    try:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": "Say 'ok'"}],
                "max_tokens": 5,
            },
            timeout=15.0,
        )

        if resp.status_code == 200:
            print(f"  {key_name}: [OK] VALID  ({masked})")
            return True
        elif resp.status_code == 401:
            print(f"  {key_name}: [FAIL] INVALID (401 Unauthorized)  ({masked})")
            return False
        elif resp.status_code == 429:
            # Rate limited but key is valid
            print(f"  {key_name}: [OK] VALID (rate-limited)  ({masked})")
            return True
        else:
            body = resp.text[:200]
            print(f"  {key_name}: [EMPTY] HTTP {resp.status_code}  ({masked})  {body}")
            return False

    except Exception as exc:
        print(f"  {key_name}: [EMPTY] ERROR  ({masked})  {exc}")
        return False


def main():
    print("=" * 60)
    print("  Groq API Key Verification")
    print("=" * 60)
    print()

    keys = {
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY", ""),
        "GROQ_API_KEY_2": os.getenv("GROQ_API_KEY_2", ""),
        "GROQ_API_KEY_3": os.getenv("GROQ_API_KEY_3", ""),
    }

    valid_count = 0
    for name, key in keys.items():
        if test_groq_key(name, key):
            valid_count += 1

    print()
    print(f"  Result: {valid_count}/{len(keys)} keys valid")

    # Also check if Key Vault is configured
    kv_url = os.getenv("AZURE_KEYVAULT_URL", "")
    if kv_url:
        print(f"\n  Key Vault URL: {kv_url}")
        print("  Attempting to read Groq keys from Key Vault...")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            client = SecretClient(vault_url=kv_url, credential=DefaultAzureCredential())
            kv_keys = ["GROQ-API-KEY", "GROQ-API-KEY-2", "GROQ-API-KEY-3"]
            for kv_name in kv_keys:
                try:
                    secret = client.get_secret(kv_name)
                    kv_key = secret.value
                    test_groq_key(f"KV:{kv_name}", kv_key)
                except Exception as exc:
                    print(f"  KV:{kv_name}: [EMPTY] Not found in vault ({exc.__class__.__name__})")
        except ImportError:
            print(
                "  [EMPTY] azure-identity / azure-keyvault-secrets not installed — skipping KV check"
            )
        except Exception as exc:
            print(f"  [EMPTY] Key Vault connection failed: {exc}")

    print()
    print("=" * 60)
    return 0 if valid_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
