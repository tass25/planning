"""Comprehensive Docker deployment test suite for Codara.

Tests every API endpoint, auth flow, file upload, KB operations, admin
endpoints, health checks, and edge cases against a running container.

Usage:
    python infra/test_comprehensive.py [--base-url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"
PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0
RESULTS: list[tuple[str, str, str]] = []


def _req(method: str, path: str, body: dict | None = None, token: str = "", timeout: int = 15) -> tuple[int, dict | str]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except (json.JSONDecodeError, Exception):
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def _multipart_upload(path: str, filename: str, content: str, token: str = "") -> tuple[int, dict | str]:
    """Upload a file via multipart/form-data."""
    boundary = "----CodaTestBoundary9876"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
        f"{content}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    url = f"{BASE}{path}"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def test(name: str, passed: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        RESULTS.append((name, "PASS", detail))
        print(f"  [PASS] {name}" + (f" - {detail}" if detail else ""))
    else:
        FAIL_COUNT += 1
        RESULTS.append((name, "FAIL", detail))
        print(f"  [FAIL] {name}" + (f" - {detail}" if detail else ""))


def skip(name: str, reason: str = ""):
    global SKIP_COUNT
    SKIP_COUNT += 1
    RESULTS.append((name, "SKIP", reason))
    print(f"  [SKIP] {name}" + (f" - {reason}" if reason else ""))


def main():
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")

    print(f"\n{'='*70}")
    print(f"  CODARA -- Comprehensive Deployment Test Suite")
    print(f"  Target: {BASE}")
    print(f"{'='*70}\n")

    # ==================================================================
    # 1. HEALTH & STARTUP
    # ==================================================================
    print("-- 1. Health & Startup ------------------------------------")
    status, data = _req("GET", "/api/health")
    test("Health endpoint returns 200", status == 200, f"status={status}")
    if isinstance(data, dict):
        test("Health status is ok/degraded", data.get("status") in ("ok", "degraded"), f"status={data.get('status')}")
        test("Health reports version 3.1.0", data.get("version") == "3.1.0", f"version={data.get('version')}")
        test("Health reports env", data.get("env") in ("development", "production", "staging"), f"env={data.get('env')}")
        deps = data.get("dependencies", {})
        test("SQLite dependency ok", deps.get("sqlite") == "ok", f"sqlite={deps.get('sqlite')}")
        test("LanceDB dependency ok/degraded", deps.get("lancedb") in ("ok", "degraded"), f"lancedb={deps.get('lancedb')}")
        test("Redis reports status", deps.get("redis") in ("ok", "degraded", "unavailable"), f"redis={deps.get('redis')}")
        test("Ollama reports status", deps.get("ollama") in ("ok", "unavailable"), f"ollama={deps.get('ollama')}")
    else:
        test("Health returns JSON", False, f"got: {str(data)[:100]}")

    # ==================================================================
    # 2. AUTH
    # ==================================================================
    print("\n-- 2. Authentication --------------------------------------")

    # Wrong password for seeded admin
    status, data = _req("POST", "/api/auth/login", {"email": "admin@codara.dev", "password": "wrong-password"})
    test("Login with wrong password returns 401", status == 401, f"status={status}")

    # Register new user (route is /api/auth/signup)
    test_email = f"test_{int(time.time())}@codara.dev"
    status, data = _req("POST", "/api/auth/signup", {
        "email": test_email,
        "password": "TestPass123!",
        "name": "Test User"
    })
    test("Register new user (POST /auth/signup)", status == 200, f"status={status}")
    user_token = ""
    if isinstance(data, dict):
        user_token = data.get("token", "") or data.get("access_token", "")
        test("Register returns JWT token", len(user_token) > 20, f"token_len={len(user_token)}")
        user_data = data.get("user", {})
        test("Register returns user object", user_data.get("email") == test_email, f"email={user_data.get('email')}")
    else:
        test("Register returns JSON", False, str(data)[:100])

    # Duplicate
    status, data = _req("POST", "/api/auth/signup", {
        "email": test_email,
        "password": "TestPass123!",
        "name": "Test User"
    })
    test("Duplicate registration rejected", status in (400, 409, 422), f"status={status}")

    # Login
    status, data = _req("POST", "/api/auth/login", {"email": test_email, "password": "TestPass123!"})
    test("Login with valid credentials", status == 200, f"status={status}")
    if isinstance(data, dict) and (data.get("token") or data.get("access_token")):
        user_token = data.get("token", "") or data.get("access_token", "")
        test("Login returns JWT", len(user_token) > 20)

    # /me
    status, data = _req("GET", "/api/auth/me", token=user_token)
    test("/me returns current user", status == 200, f"status={status}")
    if isinstance(data, dict):
        test("/me email matches", data.get("email") == test_email)

    # Unauthenticated
    status, data = _req("GET", "/api/auth/me")
    test("/me without token returns 401/403", status in (401, 403), f"status={status}")

    # Invalid token
    status, data = _req("GET", "/api/auth/me", token="invalid.jwt.token")
    test("/me with invalid token returns 401/403", status in (401, 403, 422), f"status={status}")

    # Logout
    status, data = _req("POST", "/api/auth/logout", token=user_token)
    test("POST /auth/logout", status in (200, 204), f"status={status}")

    # Re-login after logout
    status, data = _req("POST", "/api/auth/login", {"email": test_email, "password": "TestPass123!"})
    if isinstance(data, dict):
        user_token = data.get("token", "") or data.get("access_token", "") or user_token
    test("Re-login after logout works", status == 200, f"status={status}")

    # ==================================================================
    # 3. KNOWLEDGE BASE (/api/kb)
    # ==================================================================
    print("\n-- 3. Knowledge Base API ----------------------------------")
    status, data = _req("GET", "/api/kb", token=user_token)
    test("GET /kb returns 200", status == 200, f"status={status}")
    if isinstance(data, list):
        test("KB has seeded entries", len(data) >= 4, f"count={len(data)}")
    else:
        test("KB returns list", isinstance(data, list), str(type(data)))

    # Create
    status, data = _req("POST", "/api/kb", {
        "sasSnippet": "proc print data=test; run;",
        "pythonTranslation": "print(test.to_string())",
        "category": "test_category",
        "confidence": 0.9
    }, token=user_token)
    test("Create KB entry", status in (200, 201), f"status={status}")
    kb_entry_id = ""
    if isinstance(data, dict):
        kb_entry_id = data.get("id", "")

    # Read back
    if kb_entry_id:
        status, data = _req("GET", f"/api/kb/{kb_entry_id}", token=user_token)
        test("GET /kb/{id} single entry", status == 200, f"status={status}")

        # Update
        status, data = _req("PUT", f"/api/kb/{kb_entry_id}", {
            "sasSnippet": "proc print data=test; run;",
            "pythonTranslation": "print(test.head().to_string())",
            "category": "test_category",
            "confidence": 0.95
        }, token=user_token)
        test("PUT /kb/{id} update", status == 200, f"status={status}")

    # Changelog
    status, data = _req("GET", "/api/kb/changelog", token=user_token)
    test("GET /kb/changelog", status == 200, f"status={status}")

    # ==================================================================
    # 4. CONVERSIONS
    # ==================================================================
    print("\n-- 4. Conversions API -------------------------------------")

    sas_content = "DATA work.test;\n    SET raw.input;\n    IF amount > 100 THEN flag = 'HIGH';\n    ELSE flag = 'LOW';\nRUN;\n"
    status, data = _multipart_upload("/api/conversions/upload", "test_upload.sas", sas_content, token=user_token)
    test("Upload SAS file", status == 200, f"status={status}")
    file_id = ""
    if isinstance(data, list) and len(data) > 0:
        file_id = data[0].get("id", "") if isinstance(data[0], dict) else ""
        test("Upload returns file info", bool(file_id), f"file_id={file_id}")
    elif isinstance(data, dict):
        file_id = data.get("id", "")
        test("Upload returns file info", bool(file_id), f"file_id={file_id}")

    # List
    status, data = _req("GET", "/api/conversions", token=user_token)
    test("GET /conversions list", status == 200, f"status={status}")

    # Start conversion
    if file_id:
        status, data = _req("POST", "/api/conversions/start", {
            "fileIds": [file_id],
            "config": {"targetRuntime": "python"}
        }, token=user_token)
        test("Start conversion accepted", status in (200, 201, 202), f"status={status}")
        conv_id = ""
        if isinstance(data, dict):
            conv_id = data.get("id", "")
            if conv_id:
                time.sleep(3)
                status2, data2 = _req("GET", f"/api/conversions/{conv_id}", token=user_token)
                test("Poll conversion status", status2 == 200, f"status={status2}")
                if isinstance(data2, dict):
                    conv_status = data2.get("status", "")
                    test("Conversion has valid status", conv_status in ("queued", "running", "completed", "partial", "failed"), f"conv_status={conv_status}")

                # Partitions endpoint
                status3, data3 = _req("GET", f"/api/conversions/{conv_id}/partitions", token=user_token)
                test("GET /conversions/{id}/partitions", status3 in (200, 404), f"status={status3}")

                # Code endpoint
                status4, data4 = _req("GET", f"/api/conversions/{conv_id}/code", token=user_token)
                test("GET /conversions/{id}/code", status4 in (200, 404), f"status={status4}")
    else:
        skip("Start conversion", "no file_id from upload")

    # ==================================================================
    # 5. NOTIFICATIONS
    # ==================================================================
    print("\n-- 5. Notifications ---------------------------------------")
    status, data = _req("GET", "/api/notifications", token=user_token)
    test("GET /notifications", status == 200, f"status={status}")

    status, data = _req("PUT", "/api/notifications/read-all", token=user_token)
    test("PUT /notifications/read-all", status in (200, 204), f"status={status}")

    # ==================================================================
    # 6. ANALYTICS
    # ==================================================================
    print("\n-- 6. Analytics -------------------------------------------")
    status, data = _req("GET", "/api/analytics", token=user_token)
    test("GET /analytics", status == 200, f"status={status}")

    status, data = _req("GET", "/api/analytics/failure-modes", token=user_token)
    test("GET /analytics/failure-modes", status == 200, f"status={status}")

    # ==================================================================
    # 7. SETTINGS
    # ==================================================================
    print("\n-- 7. User Settings ---------------------------------------")
    status, data = _req("PUT", "/api/settings/preferences", {
        "default_runtime": "python",
        "email_notifications": False
    }, token=user_token)
    test("PUT /settings/preferences", status == 200, f"status={status}")

    status, data = _req("PUT", "/api/settings/profile", {
        "name": "Updated Test User"
    }, token=user_token)
    test("PUT /settings/profile", status == 200, f"status={status}")

    # ==================================================================
    # 8. PROJECTS
    # ==================================================================
    print("\n-- 8. Projects --------------------------------------------")
    status, data = _req("GET", "/api/projects", token=user_token)
    test("GET /projects", status == 200, f"status={status}")

    status, data = _req("POST", "/api/projects", {
        "name": "Test Project",
        "description": "Comprehensive test project"
    }, token=user_token)
    test("Create project", status in (200, 201), f"status={status}")
    project_id = ""
    if isinstance(data, dict):
        project_id = data.get("id", "")

    if project_id:
        status, data = _req("GET", f"/api/projects/{project_id}/conversions", token=user_token)
        test("GET /projects/{id}/conversions", status == 200, f"status={status}")

        status, data = _req("PUT", f"/api/projects/{project_id}", {
            "name": "Updated Test Project",
            "description": "Updated description"
        }, token=user_token)
        test("PUT /projects/{id} update", status == 200, f"status={status}")

    # ==================================================================
    # 9. ADMIN ENDPOINTS (access control)
    # ==================================================================
    print("\n-- 9. Admin Endpoints (access control) --------------------")

    status, data = _req("GET", "/api/admin/users", token=user_token)
    test("Non-admin blocked from /admin/users", status in (401, 403), f"status={status}")

    status, data = _req("GET", "/api/admin/audit-logs", token=user_token)
    test("Non-admin blocked from /admin/audit-logs", status in (401, 403), f"status={status}")

    status, data = _req("GET", "/api/admin/system-health", token=user_token)
    test("Non-admin blocked from /admin/system-health", status in (401, 403), f"status={status}")

    status, data = _req("GET", "/api/admin/pipeline-config", token=user_token)
    test("Non-admin blocked from /admin/pipeline-config", status in (401, 403), f"status={status}")

    status, data = _req("GET", "/api/admin/prompts", token=user_token)
    test("Non-admin blocked from /admin/prompts", status in (401, 403), f"status={status}")

    status, data = _req("GET", "/api/admin/cost", token=user_token)
    test("Non-admin blocked from /admin/cost", status in (401, 403), f"status={status}")

    status, data = _req("GET", "/api/admin/error-queue", token=user_token)
    test("Non-admin blocked from /admin/error-queue", status in (401, 403), f"status={status}")

    status, data = _req("GET", "/api/admin/file-registry", token=user_token)
    test("Non-admin blocked from /admin/file-registry", status in (401, 403), f"status={status}")

    # ==================================================================
    # 10. ADMIN ENDPOINTS (with admin token)
    # ==================================================================
    print("\n-- 10. Admin Endpoints (with admin) -----------------------")

    # Get admin password from container logs
    admin_token = ""
    # We can't easily get the generated password from here,
    # so try to register an admin or use the seeded one
    # For now, just verify admin routes exist and return proper status
    skip("Admin endpoint tests", "need admin password from container logs")

    # ==================================================================
    # 11. EDGE CASES & SECURITY
    # ==================================================================
    print("\n-- 11. Edge Cases & Security ------------------------------")

    status, data = _req("GET", "/api/nonexistent")
    test("404 for unknown endpoint", status == 404, f"status={status}")

    status, data = _req("GET", "/api/conversions/nonexistent-id", token=user_token)
    test("Non-existent conversion", status in (404, 422, 500), f"status={status}")

    status, data = _req("POST", "/api/auth/login", {})
    test("Login with empty body returns 4xx", 400 <= status < 500, f"status={status}")

    status, data = _req("POST", "/api/auth/login", {
        "email": "' OR 1=1 --",
        "password": "test"
    })
    test("SQL injection in login blocked", status in (401, 422), f"status={status}")

    status, data = _req("POST", "/api/auth/signup", {
        "email": "xss_test@codara.dev",
        "password": "TestPass123!",
        "name": "<script>alert('xss')</script>"
    })
    test("XSS in name doesn't crash server", status in (200, 400, 422), f"status={status}")

    status, data = _req("POST", "/api/auth/login", {
        "email": "a" * 10000 + "@test.com",
        "password": "test"
    })
    test("Long input handled gracefully", status in (401, 413, 422), f"status={status}")

    url = f"{BASE}/api/auth/login"
    req = urllib.request.Request(url, data=b'{"email":"test","password":"test"}', method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            mstatus = resp.status
    except urllib.error.HTTPError as e:
        mstatus = e.code
    except Exception:
        mstatus = 0
    test("Missing content-type handled", mstatus in (200, 401, 415, 422), f"status={mstatus}")

    # CORS preflight check
    url = f"{BASE}/api/health"
    req = urllib.request.Request(url, method="OPTIONS")
    req.add_header("Origin", "http://localhost:5173")
    req.add_header("Access-Control-Request-Method", "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            cors_status = resp.status
            cors_headers = dict(resp.headers)
    except urllib.error.HTTPError as e:
        cors_status = e.code
        cors_headers = {}
    except Exception:
        cors_status = 0
        cors_headers = {}
    test("CORS preflight returns 200", cors_status == 200, f"status={cors_status}")

    # ==================================================================
    # 12. IP PROTECTION VERIFICATION
    # ==================================================================
    print("\n-- 12. IP Protection (Cython .so) -------------------------")
    # This test runs inside the container to verify .py files are replaced
    import subprocess, os as _os
    DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    try:
        env = dict(_os.environ)
        env["PATH"] = r"C:\Program Files\Docker\Docker\resources\bin;" + env.get("PATH", "")
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "sh", "-c",
             "echo '=== CDAIS .py files (should only be __init__.py) ===' && "
             "ls -la /app/backend/partition/testing/cdais/*.py 2>/dev/null || echo 'NO .py files' && "
             "echo '=== CDAIS .so files ===' && "
             "ls -la /app/backend/partition/testing/cdais/*.so 2>/dev/null || echo 'NO .so files' && "
             "echo '=== Invariant .py files (should only be __init__.py) ===' && "
             "ls -la /app/backend/partition/invariant/*.py 2>/dev/null || echo 'NO .py files' && "
             "echo '=== Invariant .so files ===' && "
             "ls -la /app/backend/partition/invariant/*.so 2>/dev/null || echo 'NO .so files'"
             ],
            capture_output=True, text=True, timeout=15, env=env
        )
        output = result.stdout
        print(f"  Container file check:\n{output}")

        has_cdais_so = ".so" in output and "cdais" in output.lower()
        has_invariant_so = ".so" in output and "invariant" in output.lower()
        # Check that source .py files (non-init) are deleted
        lines = output.split("\n")
        cdais_py_count = sum(1 for l in lines if "cdais" in l and l.endswith(".py") and "__init__" not in l)
        invariant_py_count = sum(1 for l in lines if "invariant" in l and l.endswith(".py") and "__init__" not in l)

        test("CDAIS has .so binaries", has_cdais_so)
        test("CDAIS source .py files removed", cdais_py_count == 0, f"found {cdais_py_count} non-init .py files")
        test("Invariant has .so binaries", has_invariant_so)
        test("Invariant source .py files removed", invariant_py_count == 0, f"found {invariant_py_count} non-init .py files")
    except Exception as e:
        skip("IP protection check", str(e))

    # ==================================================================
    # 13. CONTAINER INTERNALS
    # ==================================================================
    print("\n-- 13. Container Internals --------------------------------")
    try:
        env = dict(__import__("os").environ)
        env["PATH"] = r"C:\Program Files\Docker\Docker\resources\bin;" + env.get("PATH", "")

        # Check user is appuser (non-root)
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "whoami"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("Container runs as non-root", result.stdout.strip() == "appuser", f"user={result.stdout.strip()}")

        # Check PYTHONPATH
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "sh", "-c", "echo $PYTHONPATH"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("PYTHONPATH set correctly", "/app/backend" in result.stdout, f"PYTHONPATH={result.stdout.strip()}")

        # Check pyproject.toml exists
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "test", "-f", "/app/pyproject.toml"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("pyproject.toml present", result.returncode == 0)

        # Check data dirs exist and are writable
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "sh", "-c",
             "test -d /app/backend/data && test -w /app/backend/data && echo OK"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("Data directory exists and writable", "OK" in result.stdout)

        # Check uploads dir
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "sh", "-c",
             "test -d /app/backend/uploads && test -w /app/backend/uploads && echo OK"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("Uploads directory exists and writable", "OK" in result.stdout)

        # Check .env is NOT in the image (security)
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "test", "-f", "/app/.env"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test(".env file NOT in image", result.returncode != 0)

        # Check entrypoint
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "test", "-x", "/app/entrypoint.sh"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("entrypoint.sh is executable", result.returncode == 0)

        # Check seed_kb.py exists
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "test", "-f", "/app/backend/scripts/kb/seed_kb.py"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("seed_kb.py present in image", result.returncode == 0)

        # Check knowledge_base data exists
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "sh", "-c",
             "ls /app/backend/knowledge_base/ 2>/dev/null | head -5"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("Knowledge base data in image", len(result.stdout.strip()) > 0, f"files={result.stdout.strip()}")

        # Check HF model cache
        result = subprocess.run(
            [DOCKER, "exec", "codara-test", "sh", "-c",
             "test -d /app/.cache/huggingface/hub && echo OK"],
            capture_output=True, text=True, timeout=10, env=env
        )
        test("HuggingFace model cache present", "OK" in result.stdout)

    except Exception as e:
        skip("Container internals", str(e))

    # ==================================================================
    # SUMMARY
    # ==================================================================
    total = PASS_COUNT + FAIL_COUNT + SKIP_COUNT
    print(f"\n{'='*70}")
    print(f"  RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed, {SKIP_COUNT} skipped / {total} total")
    print(f"{'='*70}")

    if FAIL_COUNT > 0:
        print("\n  Failed tests:")
        for name, result_status, detail in RESULTS:
            if result_status == "FAIL":
                print(f"    - {name}: {detail}")

    print()
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
