from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
import os
import jwt
from datetime import datetime, timedelta
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

router = APIRouter()

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-voxis")
ALGORITHM = "HS256"

# Setup OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@router.get("/login")
async def login(request: Request):
    """
    Redirects the user to Google OAuth consent screen.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        # Mock OAuth flow for testing
        return RedirectResponse(url="http://localhost:8000/auth/callback?code=mock_code_123")
    
    redirect_uri = "http://localhost:8000/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/callback")
async def auth_callback(request: Request, code: str = None):
    """
    Handles the Google OAuth callback, verifies the token, and sets a JWT cookie.
    """
    if code == "mock_code_123":
        user_info = {
            "email": "demo@voxis.ai",
            "name": "Voxis Presenter",
            "picture": "https://ui-avatars.com/api/?name=Voxis+Presenter&background=8b5cf6&color=fff"
        }
    else:
        try:
            token = await oauth.google.authorize_access_token(request)
            user_info = token.get('userinfo')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"OAuth Failed: {str(e)}")

    if not user_info:
        raise HTTPException(status_code=400, detail="OAuth Failed: No user info returned")

    # Create JWT Token
    expiration = datetime.utcnow() + timedelta(days=7)
    jwt_payload = {
        "sub": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
        "exp": expiration
    }
    
    token = jwt.encode(jwt_payload, JWT_SECRET, algorithm=ALGORITHM)

    # Redirect back to the React Dashboard with token in URL query params
    # React will pick it up and store it in localStorage
    response = RedirectResponse(url=f"http://localhost:5173/dashboard?token={token}")
    
    return response

@router.get("/me")
async def get_current_user(request: Request):
    """
    Endpoint for React to check if the user is currently logged in via Authorization header.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = auth_header.split(" ")[1]
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
