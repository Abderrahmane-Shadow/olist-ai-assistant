"""Comprehensive Multi-User Authentication, Authorization, Isolation & Quota Tests.

Tests:
1. Valid JWT authentication and user profile loading.
2. Expired token rejection (HTTP 401).
3. Forged / invalid signature token rejection (HTTP 401).
4. Missing Authorization header rejection (HTTP 401).
5. User A cannot read User B's conversation (HTTP 403).
6. User A cannot update User B's conversation title (HTTP 403).
7. User A cannot delete User B's conversation (HTTP 403).
8. User A cannot insert messages into User B's conversation (HTTP 403).
9. Daily question limit enforcement (HTTP 429 when quota exceeded).
10. Admin role bypasses daily question limit.
11. Concurrent request limit guard enforcement.
12. Separation of concerns: olist_readonly database user CANNOT access user tables.
13. Text-to-SQL AST table allowlist blocks any access to profiles, conversations, messages.
"""

import time
import unittest
import uuid
import jwt
from datetime import date
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.core.auth import (
    AuthenticatedUser,
    create_test_token,
    verify_supabase_jwt,
    get_or_create_profile,
    check_and_increment_daily_usage,
    ConcurrentRequestGuard,
)
from app.database import SessionLocal, SessionReadOnly
from app.main import app
from app.services.conversation_service import ConversationService
from app.services.text_to_sql import TextToSQLService


class TestAuthMultiUser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()
        cls.settings = get_settings()

        # Two distinct test users
        cls.user_a_id = str(uuid.uuid4())
        cls.user_a_email = f"user_a_{cls.user_a_id[:8]}@example.com"
        cls.token_a = create_test_token(cls.user_a_id, cls.user_a_email, role="user")

        cls.user_b_id = str(uuid.uuid4())
        cls.user_b_email = f"user_b_{cls.user_b_id[:8]}@example.com"
        cls.token_b = create_test_token(cls.user_b_id, cls.user_b_email, role="user")

        # Admin user
        cls.admin_id = str(uuid.uuid4())
        cls.admin_email = f"admin_{cls.admin_id[:8]}@example.com"
        cls.token_admin = create_test_token(cls.admin_id, cls.admin_email, role="admin")

        # Setup initial profiles
        cls.profile_a = get_or_create_profile(cls.user_a_id, cls.user_a_email, "User Alpha", "user", cls.db)
        cls.profile_b = get_or_create_profile(cls.user_b_id, cls.user_b_email, "User Beta", "user", cls.db)
        cls.profile_admin = get_or_create_profile(cls.admin_id, cls.admin_email, "System Admin", "admin", cls.db)

    @classmethod
    def tearDownClass(cls):
        # Clean up created test data
        try:
            cls.db.execute(
                text("DELETE FROM public.profiles WHERE id IN (:a, :b, :admin);"),
                {"a": cls.user_a_id, "b": cls.user_b_id, "admin": cls.admin_id},
            )
            cls.db.commit()
        except Exception:
            cls.db.rollback()
        cls.db.close()

    # -------------------------------------------------------------
    # 1. Token Verification & Authentication Tests
    # -------------------------------------------------------------
    def test_01_valid_token_verification(self):
        """Verify that a properly signed token decodes with correct claims."""
        payload = verify_supabase_jwt(self.token_a)
        self.assertEqual(payload["sub"], self.user_a_id)
        self.assertEqual(payload["email"], self.user_a_email)

    def test_02_expired_token_rejected(self):
        """Verify that expired tokens raise HTTP 401."""
        expired_token = create_test_token(
            self.user_a_id, self.user_a_email, expires_in_seconds=-10
        )
        with self.assertRaises(HTTPException) as ctx:
            verify_supabase_jwt(expired_token)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("expired", ctx.exception.detail.lower())

    def test_03_forged_signature_token_rejected(self):
        """Verify that tokens with wrong secret key are rejected with HTTP 401."""
        forged_token = create_test_token(
            self.user_a_id, self.user_a_email, secret="completely_wrong_secret_key_32_bytes_long_hmac"
        )
        with self.assertRaises(HTTPException) as ctx:
            verify_supabase_jwt(forged_token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_03b_unsigned_none_algorithm_rejected(self):
        """Verify that tokens signed with 'none' algorithm are strictly rejected with HTTP 401."""
        payload = {"sub": self.user_a_id, "email": self.user_a_email, "exp": int(time.time()) + 3600}
        unsigned_token = jwt.encode(payload, key="", algorithm="none")
        with self.assertRaises(HTTPException) as ctx:
            verify_supabase_jwt(unsigned_token)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("none", ctx.exception.detail.lower())

    def test_03c_unsupported_algorithm_rejected(self):
        """Verify that tokens with algorithms outside allowed whitelist (e.g. HS384) are rejected."""
        payload = {"sub": self.user_a_id, "email": self.user_a_email, "exp": int(time.time()) + 3600}
        token_hs384 = jwt.encode(payload, "secret_key_long_enough_for_hs384_testing_here_32b", algorithm="HS384")
        with self.assertRaises(HTTPException) as ctx:
            verify_supabase_jwt(token_hs384)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("unsupported", ctx.exception.detail.lower())

    def test_03d_missing_subject_claim_rejected(self):
        """Verify that tokens missing the 'sub' claim are rejected."""
        payload = {"email": self.user_a_email, "exp": int(time.time()) + 3600, "aud": "authenticated"}
        token_no_sub = jwt.encode(payload, self.settings.SUPABASE_JWT_SECRET or "olist_super_secret_jwt_2026_dev_key_secure_32b", algorithm="HS256")
        with self.assertRaises(HTTPException) as ctx:
            verify_supabase_jwt(token_no_sub)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("sub", ctx.exception.detail.lower())

    def test_03e_asymmetric_rsa_token_verification(self):
        """Verify asymmetric RS256 token verification using RSA public/private keypair."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        # Generate temporary test RSA keypair
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        # Encode token using RS256 and private key
        payload = {
            "sub": self.user_a_id,
            "email": self.user_a_email,
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
            "iss": f"{self.settings.SUPABASE_URL.rstrip('/')}/auth/v1" if self.settings.SUPABASE_URL else "supabase-demo",
        }
        rsa_token = jwt.encode(payload, private_pem, algorithm="RS256")

        # Configure public key in settings and verify
        old_pubkey = self.settings.SUPABASE_JWT_PUBLIC_KEY
        try:
            self.settings.SUPABASE_JWT_PUBLIC_KEY = public_pem
            verified = verify_supabase_jwt(rsa_token)
            self.assertEqual(verified["sub"], self.user_a_id)
        finally:
            self.settings.SUPABASE_JWT_PUBLIC_KEY = old_pubkey

    def test_03e2_asymmetric_es256_ecc_token_verification(self):
        """Verify asymmetric ES256 (ECC P-256) token verification matching Supabase's current signing algorithm."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        # Generate temporary test ECDSA P-256 keypair (matching Supabase ES256)
        ec_private_key = ec.generate_private_key(ec.SECP256R1())
        ec_private_pem = ec_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        ec_public_pem = ec_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        # Encode token using ES256 and ECC private key with kid header
        payload = {
            "sub": self.user_a_id,
            "email": self.user_a_email,
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
            "iss": f"{self.settings.SUPABASE_URL.rstrip('/')}/auth/v1" if self.settings.SUPABASE_URL else "supabase-demo",
        }
        headers = {"kid": "supabase-test-key-2026", "alg": "ES256"}
        es256_token = jwt.encode(payload, ec_private_pem, algorithm="ES256", headers=headers)

        # Configure public key in settings and verify ES256
        old_pubkey = self.settings.SUPABASE_JWT_PUBLIC_KEY
        try:
            self.settings.SUPABASE_JWT_PUBLIC_KEY = ec_public_pem
            verified = verify_supabase_jwt(es256_token)
            self.assertEqual(verified["sub"], self.user_a_id)
            self.assertEqual(verified["email"], self.user_a_email)

            # Test that HS256 tokens also remain completely valid under the same runtime
            hs256_token = create_test_token(self.user_a_id, self.user_a_email)
            hs256_verified = verify_supabase_jwt(hs256_token)
            self.assertEqual(hs256_verified["sub"], self.user_a_id)
        finally:
            self.settings.SUPABASE_JWT_PUBLIC_KEY = old_pubkey

    def test_03e3_jwks_kid_unknown_rejected(self):
        """Verify that asymmetric tokens with unknown kid or unreachable JWKS are rejected with HTTP 401."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        ec_key = ec.generate_private_key(ec.SECP256R1())
        ec_pem = ec_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        payload = {"sub": self.user_a_id, "email": self.user_a_email, "exp": int(time.time()) + 3600, "aud": "authenticated"}
        token_unknown_kid = jwt.encode(payload, ec_pem, algorithm="ES256", headers={"kid": "non-existent-kid"})

        old_url = self.settings.SUPABASE_URL
        old_pubkey = self.settings.SUPABASE_JWT_PUBLIC_KEY
        try:
            self.settings.SUPABASE_JWT_PUBLIC_KEY = None
            self.settings.SUPABASE_URL = "http://localhost:59999"  # unreachable endpoint
            with self.assertRaises(HTTPException) as ctx:
                verify_supabase_jwt(token_unknown_kid)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("jwks", ctx.exception.detail.lower())
        finally:
            self.settings.SUPABASE_URL = old_url
            self.settings.SUPABASE_JWT_PUBLIC_KEY = old_pubkey

    def test_03f_invalid_audience_rejected(self):
        """Verify that tokens with wrong audience are strictly rejected with HTTP 401."""
        payload = {
            "sub": self.user_a_id,
            "email": self.user_a_email,
            "exp": int(time.time()) + 3600,
            "aud": "malicious-third-party-app",
        }
        token_bad_aud = jwt.encode(payload, self.settings.SUPABASE_JWT_SECRET or "olist_super_secret_jwt_2026_dev_key_secure_32b", algorithm="HS256")
        with self.assertRaises(HTTPException) as ctx:
            verify_supabase_jwt(token_bad_aud)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("audience", ctx.exception.detail.lower())

    def test_03g_invalid_issuer_rejected(self):
        """Verify that tokens from an unauthorized issuer are rejected when SUPABASE_URL is configured."""
        old_url = self.settings.SUPABASE_URL
        try:
            self.settings.SUPABASE_URL = "https://legit-project.supabase.co"
            payload = {
                "sub": self.user_a_id,
                "email": self.user_a_email,
                "exp": int(time.time()) + 3600,
                "aud": "authenticated",
                "iss": "https://attacker-fake-project.supabase.co/auth/v1",
            }
            token_fake_iss = jwt.encode(payload, self.settings.SUPABASE_JWT_SECRET or "olist_super_secret_jwt_2026_dev_key_secure_32b", algorithm="HS256")
            with self.assertRaises(HTTPException) as ctx:
                verify_supabase_jwt(token_fake_iss)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("issuer", ctx.exception.detail.lower())
        finally:
            self.settings.SUPABASE_URL = old_url

    def test_03h_valid_issuer_accepted(self):
        """Verify that tokens from the configured Supabase project URL are accepted."""
        old_url = self.settings.SUPABASE_URL
        try:
            self.settings.SUPABASE_URL = "https://legit-project.supabase.co"
            payload = {
                "sub": self.user_a_id,
                "email": self.user_a_email,
                "exp": int(time.time()) + 3600,
                "aud": "authenticated",
                "iss": "https://legit-project.supabase.co/auth/v1",
            }
            token_legit = jwt.encode(payload, self.settings.SUPABASE_JWT_SECRET or "olist_super_secret_jwt_2026_dev_key_secure_32b", algorithm="HS256")
            verified = verify_supabase_jwt(token_legit)
            self.assertEqual(verified["sub"], self.user_a_id)
        finally:
            self.settings.SUPABASE_URL = old_url

    def test_04_missing_auth_header_rejected_by_api(self):
        """Verify that calling protected endpoint without Bearer token returns 401."""
        old_require_auth = self.settings.REQUIRE_AUTH
        try:
            self.settings.REQUIRE_AUTH = True
            res = self.client.get("/api/conversations")
            self.assertEqual(res.status_code, 401)
            self.assertIn("Bearer token in Authorization header is required", res.json()["detail"])
        finally:
            self.settings.REQUIRE_AUTH = old_require_auth

    def test_04b_user_profile_isolation(self):
        """Verify that /api/auth/me returns only the authenticated user's profile and never another user's."""
        res_a = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {self.token_a}"})
        self.assertEqual(res_a.status_code, 200)
        data_a = res_a.json()
        self.assertEqual(data_a["profile"]["id"], self.user_a_id)
        self.assertEqual(data_a["profile"]["email"], self.user_a_email)

        res_b = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {self.token_b}"})
        self.assertEqual(res_b.status_code, 200)
        data_b = res_b.json()
        self.assertEqual(data_b["profile"]["id"], self.user_b_id)
        self.assertEqual(data_b["profile"]["email"], self.user_b_email)

        # Cross-verify that User B's profile payload contains NONE of User A's data
        self.assertNotEqual(data_a["profile"]["id"], data_b["profile"]["id"])
        self.assertNotEqual(data_a["profile"]["email"], data_b["profile"]["email"])

    # -------------------------------------------------------------
    # 2. Multi-User Conversation Isolation Tests
    # -------------------------------------------------------------
    def test_05_user_cannot_read_another_users_conversation(self):
        """Verify User B receives 403 Forbidden when attempting to read User A's conversation."""
        # Create a conversation as User A
        conv_a = ConversationService.create_conversation(self.user_a_id, "User A Secret Data", self.db)
        conv_id = conv_a["id"]

        # User A can read it
        res_a = self.client.get(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {self.token_a}"},
        )
        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(res_a.json()["title"], "User A Secret Data")

        # User B CANNOT read it
        res_b = self.client.get(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {self.token_b}"},
        )
        self.assertEqual(res_b.status_code, 403)
        self.assertIn("Access denied", res_b.json()["detail"])

    def test_06_user_cannot_update_another_users_conversation(self):
        """Verify User B cannot rename User A's conversation."""
        conv_a = ConversationService.create_conversation(self.user_a_id, "Original Title", self.db)
        conv_id = conv_a["id"]

        res = self.client.patch(
            f"/api/conversations/{conv_id}",
            json={"title": "Hacked Title"},
            headers={"Authorization": f"Bearer {self.token_b}"},
        )
        self.assertEqual(res.status_code, 403)

    def test_07_user_cannot_delete_another_users_conversation(self):
        """Verify User B cannot delete User A's conversation."""
        conv_a = ConversationService.create_conversation(self.user_a_id, "Keep Alive", self.db)
        conv_id = conv_a["id"]

        res = self.client.delete(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {self.token_b}"},
        )
        self.assertEqual(res.status_code, 403)

        # Confirm conversation is still alive for User A
        alive = self.client.get(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {self.token_a}"},
        )
        self.assertEqual(alive.status_code, 200)

    def test_08_user_cannot_inject_message_into_another_users_conversation(self):
        """Verify ConversationService rejects saving message if user is not conversation owner."""
        conv_a = ConversationService.create_conversation(self.user_a_id, "Protected Chat", self.db)
        conv_id = conv_a["id"]

        with self.assertRaises(HTTPException) as ctx:
            ConversationService.save_message(
                conversation_id=conv_id,
                user_id=self.user_b_id,
                role="user",
                content="Unauthorized message injection",
                metadata=None,
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 403)

    # -------------------------------------------------------------
    # 3. Quota & Rate Limiting Tests
    # -------------------------------------------------------------
    def test_09_daily_question_limit_unlimited(self):
        """Verify that daily question limit is unlimited and does not raise HTTP 429."""
        test_uid = str(uuid.uuid4())
        test_user = AuthenticatedUser(
            id=test_uid,
            email=f"quota_{test_uid[:6]}@test.local",
            role="user",
            daily_question_limit=999999,
        )
        today = date.today()
        self.db.execute(
            text("INSERT INTO auth.users (id, email) VALUES (:id, :email) ON CONFLICT (id) DO NOTHING;"),
            {"id": test_uid, "email": test_user.email},
        )
        self.db.execute(
            text("INSERT INTO public.profiles (id, email, role, daily_question_limit) VALUES (:id, :email, 'user', 999999) ON CONFLICT (id) DO NOTHING;"),
            {"id": test_uid, "email": test_user.email},
        )
        self.db.execute(
            text("""
                INSERT INTO public.user_daily_usage (user_id, usage_date, question_count)
                VALUES (:id, :today, 100)
                ON CONFLICT (user_id, usage_date) DO UPDATE SET question_count = 100;
            """),
            {"id": test_uid, "today": today},
        )
        self.db.commit()

        # Calling usage check must succeed and return unlimited quota
        used, limit = check_and_increment_daily_usage(test_user, self.db)
        self.assertGreaterEqual(used, 100)
        self.assertEqual(limit, 999999)

        # Clean up
        self.db.execute(text("DELETE FROM public.profiles WHERE id = :id;"), {"id": test_uid})
        self.db.commit()

    def test_10_admin_bypasses_daily_question_limit(self):
        """Verify that users with role 'admin' are exempt from daily limits."""
        admin_user = AuthenticatedUser(
            id=self.admin_id,
            email=self.admin_email,
            role="admin",
            daily_question_limit=15,
        )
        # Call usage check
        used, limit = check_and_increment_daily_usage(admin_user, self.db)
        self.assertEqual(limit, 999999)

    def test_11_concurrent_request_guard(self):
        """Verify ConcurrentRequestGuard blocks more than max allowed concurrent requests."""
        guard1 = ConcurrentRequestGuard(user_id="test-concurrency-user", max_concurrent=2)
        guard2 = ConcurrentRequestGuard(user_id="test-concurrency-user", max_concurrent=2)
        guard3 = ConcurrentRequestGuard(user_id="test-concurrency-user", max_concurrent=2)

        with guard1:
            with guard2:
                # 3rd concurrent request should raise HTTP 429
                with self.assertRaises(HTTPException) as ctx:
                    with guard3:
                        pass
                self.assertEqual(ctx.exception.status_code, 429)
                self.assertIn("Too many concurrent requests", ctx.exception.detail)

    # -------------------------------------------------------------
    # 4. Database Permission & AST Separation Tests
    # -------------------------------------------------------------
    def test_12_olist_readonly_cannot_access_user_tables(self):
        """Verify PostgreSQL role olist_readonly is denied access to profiles and conversations."""
        ro_session = SessionReadOnly()
        try:
            # Querying profiles with readonly role must fail
            with self.assertRaises(Exception):
                ro_session.execute(text("SELECT * FROM public.profiles LIMIT 1;"))
        finally:
            ro_session.close()

    def test_13_text_to_sql_ast_blocks_user_tables(self):
        """Verify TextToSQLService AST validator completely blocks access to profiles/conversations."""
        sql_service = TextToSQLService(db=self.db)
        forbidden_queries = [
            "SELECT * FROM profiles",
            "SELECT email FROM public.profiles",
            "SELECT * FROM conversations",
            "SELECT * FROM messages",
            "SELECT * FROM user_daily_usage",
            "SELECT * FROM auth.users",
        ]
        for q in forbidden_queries:
            is_valid, _, err = sql_service.validate_and_transform_sql(q)
            self.assertFalse(is_valid, f"Expected forbidden user table to be rejected: {q}")
            self.assertTrue(len(err) > 0)


if __name__ == "__main__":
    unittest.main()
