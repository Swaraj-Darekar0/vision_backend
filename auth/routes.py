from flask import Blueprint, request, jsonify
from supabase import create_client, Client
import config
import logging
from typing import Optional

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
logger = logging.getLogger(__name__)

# Initialize Supabase client for Auth
_db: Optional[Client] = None
if config.SUPABASE_URL and config.SUPABASE_KEY:
    try:
        _db = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        logger.info("Auth: Supabase client initialized.")
    except Exception as e:
        logger.error(f"Auth: Failed to initialize Supabase client: {e}")
else:
    logger.warning("Auth: Supabase credentials missing in config.")

@auth_bp.route("/signup", methods=["POST"])
def signup():
    """
    POST /auth/signup
    Body: { "email": "...", "password": "..." }
    """
    if not _db:
        return jsonify({"error": "Supabase client not initialized"}), 500

    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Missing email or password"}), 400

    try:
        # Sign up user via Supabase Auth
        # Note: res.user will be None if email confirmation is enabled in Supabase settings
        res = _db.auth.sign_up({
            "email": email,
            "password": password,
        })
        
        # res is an AuthResponse object
        # Insert into user_profiles if user was created
        if res.user:
            try:
                _db.table("user_profiles").insert({
                    "id": res.user.id,
                    "email": email
                }).execute()
                logger.info(f"Auth: User profile created for {email}")
            except Exception as profile_e:
                logger.error(f"Auth: Failed to create user profile: {profile_e}")
                # Continue anyway, as auth succeeded
        
        response = {
            "message": "User signed up successfully. Check your email for confirmation (if enabled).",
            "user_id": res.user.id if res.user else None
        }
        
        # Include tokens if session is available (email confirmation disabled)
        if res.session:
            response["access_token"] = res.session.access_token
            response["refresh_token"] = res.session.refresh_token
        
        return jsonify(response), 201
    except Exception as e:
        logger.error(f"Auth: Signup failed: {e}")
        return jsonify({"error": str(e)}), 400

@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /auth/login
    Body: { "email": "...", "password": "..." }
    """
    if not _db:
        return jsonify({"error": "Supabase client not initialized"}), 500

    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Missing email or password"}), 400

    try:
        # Sign in user via Supabase Auth
        res = _db.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        
        # Access session and user data
        return jsonify({
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
            "user_id": res.user.id
        }), 200
    except Exception as e:
        logger.error(f"Auth: Login failed: {e}")
        return jsonify({"error": "Invalid login credentials"}), 401
