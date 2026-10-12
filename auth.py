import hashlib
import secrets
import streamlit as st
import database

def hash_password(password: str) -> tuple[str, str]:
    """Generates a salt and returns (password_hash_hex, salt_hex)."""
    salt_bytes = secrets.token_bytes(16)
    salt_hex = salt_bytes.hex()
    hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt_bytes,
        100000
    )
    return hash_bytes.hex(), salt_hex

def verify_password(password: str, stored_hash_hex: str, stored_salt_hex: str) -> bool:
    """Verifies a plain text password against stored hash and salt."""
    try:
        salt_bytes = bytes.fromhex(stored_salt_hex)
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt_bytes,
            100000
        )
        return secrets.compare_digest(hash_bytes.hex(), stored_hash_hex)
    except Exception:
        return False

def register_admin(username: str, password: str, confirm_password: str) -> tuple[bool, str]:
    """
    Validates and registers a new administrator account.
    Returns (success: bool, message: str).
    """
    username = username.strip()
    if not username:
        return False, "Username cannot be empty."
    if len(username) < 3:
        return False, "Username must be at least 3 characters long."
    if not password:
        return False, "Password cannot be empty."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if password != confirm_password:
        return False, "Password and Confirm Password do not match."

    # Check if username already exists
    existing = database.get_admin_by_username(username)
    if existing:
        return False, f"Username '{username}' is already taken. Please choose another."

    pwd_hash, salt = hash_password(password)
    try:
        admin_id = database.create_admin(username, pwd_hash, salt)
    except Exception as e:
        return False, f"Failed to create administrator account: {str(e)}"

    if not admin_id:
        existing = database.get_admin_by_username(username)
        if existing:
            admin_id = existing['id']

    if admin_id:
        try:
            # Initialize default settings for this admin
            database.initialize_admin_defaults(admin_id)
        except Exception:
            pass
        return True, f"Administrator account '{username}' created successfully! You can now log in."


def authenticate_admin(username: str, password: str) -> tuple[bool, str, dict | None]:
    """
    Authenticates administrator credentials.
    Returns (success: bool, message: str, admin_dict: dict | None).
    """
    username = username.strip()
    if not username or not password:
        return False, "Username and password are required.", None

    admin = database.get_admin_by_username(username)
    if not admin:
        return False, "Invalid username or password.", None

    if verify_password(password, admin['password_hash'], admin['salt']):
        return True, "Login successful!", admin
    else:
        return False, "Invalid username or password.", None

def login_session(admin_dict: dict):
    """Start a clean session for the authenticated administrator.

    Streamlit session_state survives reruns, so remove all previous user's
    authentication/navigation/temporary state before assigning the new admin.
    """
    # Clear any state left by a previous administrator/session.
    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.session_state['authenticated'] = True
    st.session_state['admin_id'] = int(admin_dict['id'])
    st.session_state['admin_username'] = admin_dict['username']

def logout_session():
    """Completely clear the current Streamlit session on logout.

    This prevents the next administrator using the same browser tab from
    inheriting the previous admin's navigation, generated-run IDs, or other
    temporary session state. Database data remains safely scoped by admin_id.
    """
    for key in list(st.session_state.keys()):
        del st.session_state[key]

def is_authenticated() -> bool:
    """Returns True if an admin session is active."""
    return st.session_state.get('authenticated', False) and st.session_state.get('admin_id') is not None

def get_current_admin_id() -> int | None:
    """Returns the authenticated admin_id or None."""
    if is_authenticated():
        return st.session_state.get('admin_id')
    return None

def get_current_admin_username() -> str:
    """Returns the authenticated admin username or empty string."""
    if is_authenticated():
        return st.session_state.get('admin_username', '')
    return ''
