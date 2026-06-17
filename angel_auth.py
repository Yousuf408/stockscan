# angel_auth.py
from SmartApi import SmartConnect
import pyotp
from logzero import logger

# ─── APNE CREDENTIALS YAHAN BHARО ───────────────────────────
API_KEY      = "QFectj5C"
CLIENT_ID    = "IIRA29771"
PASSWORD     = "1993"
TOTP_SECRET  = "JFTG3DYADWLYSW6FC6RVV4THWM"
# ─────────────────────────────────────────────────────────────

def angel_login():
    try:
        smart_api = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = smart_api.generateSession(CLIENT_ID, PASSWORD, totp)

        if not data or data.get('status') == False:
            logger.error(f"Login Failed: {data}")
            return None

        jwt_token     = data['data']['jwtToken']
        refresh_token = data['data']['refreshToken']
        feed_token    = smart_api.getfeedToken()

        logger.info("Angel One Login Successful!")

        return {
            "jwt_token"     : jwt_token,
            "refresh_token" : refresh_token,
            "feed_token"    : feed_token,
            "api_key"       : API_KEY,
            "client_id"     : CLIENT_ID
        }

    except Exception as e:
        logger.exception(f"Login Error: {e}")
        return None
