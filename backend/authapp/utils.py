# ===============================================================
#  authapp/utils.py
#  Utility functions for OTP generation, email sending, and group resolution
#  These are pure helper functions — no Django views or models defined here
# ===============================================================


# ---------------- Step 0: Imports ----------------
import random
import string
from datetime import datetime
from django.core.mail import send_mail  # Django's built-in email sender (uses EMAIL_* settings)
from django.conf import settings


# ================================================================
#  Utility 1: generate_otp_code
#  Generates a random N-digit numeric string
#  Default length is 6 (e.g., "482910")
# ================================================================
def generate_otp_code(length=6) -> str:
    # string.digits = "0123456789" — picks random digits to build the OTP
    return ''.join(random.choice(string.digits) for _ in range(length))


# ================================================================
#  Utility 2: build_otp_html
#  Builds a styled HTML email body showing the OTP as individual digit boxes
#  Pure string-building — no DB or Django logic here
# ================================================================
def build_otp_html(code: str, purpose: str = "Login") -> str:
    year = datetime.now().year
    digits = list(code)  # Split "482910" → ["4","8","2","9","1","0"]

    # ---------------- Step 2a: Build Individual Digit Boxes ----------------
    # Each digit gets its own styled <span> box for a clean visual layout in the email
    digit_boxes = "".join([
        f"""<span style="
            display:inline-block;
            width:42px;
            height:50px;
            line-height:50px;
            text-align:center;
            font-size:24px;
            font-weight:600;
            color:#111827;
            background:#ffffff;
            border:1px solid #e5e7eb;
            border-radius:10px;
            margin:0 4px;
            box-shadow:0 1px 2px rgba(0,0,0,0.05);
        ">{d}</span>"""
        for d in digits
    ])

    # ---------------- Step 2b: Return Full HTML Email ----------------
    # Inline styles are used throughout because many email clients strip <style> tags
    return f"""
   <html>
      <body style="margin:0;padding:0;background-color:#f9fafb;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background-color:#f9fafb;padding:40px 0;">
          <tr>
            <td align="center">
              <table width="520" cellpadding="0" cellspacing="0"
                     style="background:#ffffff;
                            border-radius:16px;
                            border:1px solid #e5e7eb;
                            padding:40px 36px;
                            font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">

                <!-- LOGO -->
                <tr>
                  <td align="center" style="padding-bottom:28px;">
                    <div style="
                      display:inline-flex;
                      align-items:center;
                      gap:8px;
                      background:#111827;
                      border-radius:10px;
                      padding:10px 18px;
                      margin-bottom:12px;
                    ">
                      <span style="font-size:16px;font-weight:700;
                                   color:#ffffff;letter-spacing:0.02em;">
                        Chrono Assist
                      </span>
                    </div>
                    <div style="font-size:13px;color:#6b7280;margin-top:4px;">
                      {purpose} Verification
                    </div>
                  </td>
                </tr>

                <!-- DIVIDER -->
                <tr>
                  <td style="border-top:1px solid #f3f4f6;padding-bottom:28px;"></td>
                </tr>

                <!-- GREETING -->
                <tr>
                  <td style="font-size:15px;font-weight:600;color:#111827;padding-bottom:8px;">
                    Hi there,
                  </td>
                </tr>
                <tr>
                  <td style="font-size:14px;color:#6b7280;padding-bottom:28px;line-height:1.75;">
                    We received a <span style="color:#111827;font-weight:500;">{purpose.lower()}</span>
                    request for your Chrono Assist account. Use the
                    verification code below to continue. This code is valid for
                    <span style="color:#111827;font-weight:500;">5 minutes</span> only.
                  </td>
                </tr>

                <!-- OTP DIGIT BOXES -->
                <tr>
                  <td align="center" style="padding:8px 0 28px 0;">
                    <div style="
                      background:#f9fafb;
                      border:1px solid #e5e7eb;
                      border-radius:12px;
                      padding:20px 16px;
                      display:inline-block;
                    ">
                      {digit_boxes}
                    </div>
                  </td>
                </tr>

                <!-- EXPIRY BADGE -->
                <tr>
                  <td align="center" style="padding-bottom:28px;">
                    <span style="
                      display:inline-block;
                      background:#f3f4f6;
                      color:#6b7280;
                      font-size:12px;
                      padding:6px 16px;
                      border-radius:999px;
                      border:1px solid #e5e7eb;
                    ">
                      Expires in 5 minutes
                    </span>
                  </td>
                </tr>

                <!-- DIVIDER -->
                <tr>
                  <td style="border-top:1px solid #f3f4f6;padding-bottom:20px;"></td>
                </tr>

                <!-- SECURITY NOTE -->
                <tr>
                  <td style="font-size:12px;color:#9ca3af;line-height:1.7;padding-bottom:20px;">
                    If you did not request this {purpose.lower()}, you can safely
                    ignore this email. Do not share this code with anyone.
                  </td>
                </tr>

                <!-- FOOTER -->
                <tr>
                  <td align="center"
                      style="font-size:11px;color:#d1d5db;
                             padding-top:4px;border-top:1px solid #f3f4f6;">
                    &copy; {year} Chrono Assist &nbsp;&middot;&nbsp; All rights reserved
                  </td>
                </tr>

              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


# ================================================================
#  Utility 3: send_otp_email
#  Sends the OTP email to the user via Django's email backend
#  Returns True on success, False on failure (never raises to caller)
# ================================================================
def send_otp_email(to_email: str, code: str, purpose: str = "Login") -> bool:
    try:
        # ---------------- Step 3a: Build Email Content ----------------
        subject = f"Your {purpose} OTP Code — Chrono Assist"
        # Plain-text fallback for email clients that don't render HTML
        text_message = (
            f"Your {purpose} OTP code is: {code}\n"
            f"It will expire in 5 minutes.\n\n"
            f"If you didn't request this, ignore this email."
        )
        html_message = build_otp_html(code, purpose)  # Rich HTML version
        from_email = getattr(settings, 'EMAIL_HOST_USER', 'noreply@chronoassist.com')

        # ---------------- Step 3b: Send via Django Mail ----------------
        # Django routes this through whatever EMAIL_BACKEND is set in settings.py
        # fail_silently=False → raises exception if sending fails (caught below)
        send_mail(
            subject,
            text_message,
            from_email,
            [to_email],
            fail_silently=False,
            html_message=html_message,
        )
        return True

    except Exception as e:
        # Log the error but don't crash the view that called this
        print(f"[OTP EMAIL ERROR] Failed to send to {to_email}: {e}")
        return False


# ================================================================
#  Utility 4: get_group_id
#  Resolves which "company group" a user belongs to
#  MAIN user  → their own ID is the group_id (they ARE the root)
#  SUB user   → their MAIN user's ID is the group_id
#  This is used to scope DB queries so users can't see other companies' data
# ================================================================
def get_group_id(user) -> int:
    return user.follow_user_id or user.id