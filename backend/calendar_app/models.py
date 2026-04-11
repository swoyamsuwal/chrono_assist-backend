# ===============================================================
#  calendar_app/models.py
#  Single model: GoogleCredentials
#  Stores the OAuth2 token JSON returned by Google after the user
#  connects their Google Calendar account
#
#  NOTE: This is a global/shared credentials store (not per-user).
#  The system keeps only ONE row — the latest — and reuses it for
#  all calendar API calls. In production, this should be tied to
#  a User FK and tokens should be encrypted at rest.
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.db import models
from django.utils import timezone
import jsonfield  # Optional — plain TextField is used instead (more portable)


# ================================================================
#  Model: GoogleCredentials
#  Stores Google OAuth2 credentials as a JSON blob
#
#  Lifecycle:
#   1. User hits /google/login/ → redirected to Google consent screen
#   2. Google redirects to /google/callback/ with an auth code
#   3. Callback exchanges code → credentials → stored here as JSON
#   4. load_credentials() reads this row and refreshes if expired
# ================================================================
class GoogleCredentials(models.Model):

    # ---------------- Step 1: Timestamps ----------------
    created_at = models.DateTimeField(auto_now_add=True)  # When this token was first saved
    updated_at = models.DateTimeField(auto_now=True)       # Updated every time token is refreshed

    # ---------------- Step 2: Credentials Storage ----------------
    # Stores the full Google OAuth2 token as a JSON string, including:
    #   token, refresh_token, token_uri, client_id, client_secret, scopes, expiry
    # TextField is used (not JSONField) so the raw string is stored without Django transformation
    credentials_json = models.TextField(blank=True, default="")

    def __str__(self):
        return f"GoogleCredentials({self.id})"