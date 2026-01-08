import random
import string
from django.core.mail import send_mail
from django.conf import settings

def generate_otp_code(length=6) -> str:
    return ''.join(random.choice(string.digits) for _ in range(length))

def build_otp_html(code: str, purpose: str = "Login") -> str:
    return f"""
    <html>
      <body style="margin:0;padding:0;background-color:#f4f4f5;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f5;padding:24px 0;">
          <tr>
            <td align="center">
              <table width="480" cellpadding="0" cellspacing="0" 
                     style="background:#0f172a;border-radius:12px;padding:24px;color:#e5e7eb;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                <tr>
                  <td align="center" style="padding-bottom:16px;">
                    <div style="font-size:24px;font-weight:600;color:#e5e7eb;">
                      Chrono Assist
                    </div>
                    <div style="font-size:13px;color:#9ca3af;margin-top:4px;">
                      Secure {purpose} verification
                    </div>
                  </td>
                </tr>

                <tr>
                  <td style="font-size:14px;color:#e5e7eb;padding-bottom:16px;">
                    Hi,
                    <br/><br/>
                    Use the one-time code below to complete your {purpose.lower()}.
                  </td>
                </tr>

                <tr>
                  <td align="center" style="padding:16px 0 8px 0;">
                    <div style="
                      display:inline-block;
                      padding:12px 24px;
                      border-radius:999px;
                      background:#020617;
                      border:1px solid #1f2937;
                      letter-spacing:0.35em;
                      font-size:20px;
                      font-weight:600;
                      color:#e5e7eb;
                    ">
                      {code}
                    </div>
                  </td>
                </tr>

                <tr>
                  <td align="center" style="font-size:12px;color:#9ca3af;padding-bottom:8px;">
                    This code will expire in <strong>5 minutes</strong>.
                  </td>
                </tr>

                <tr>
                  <td style="font-size:12px;color:#6b7280;padding-top:16px;border-top:1px solid #1f2937;">
                    If you didn’t request this {purpose.lower()}, you can safely ignore this email.
                  </td>
                </tr>

                <tr>
                  <td style="font-size:11px;color:#4b5563;padding-top:12px;">
                    &copy; {2025} Chrono Assist. All rights reserved.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

def send_otp_email(to_email: str, code: str, purpose: str = "Login"):
    subject = f"{purpose} OTP Code"
    text_message = f"Your {purpose} OTP code is: {code}. It will expire in 5 minutes."
    html_message = build_otp_html(code, purpose)
    from_email = settings.EMAIL_HOST_USER

    send_mail(
        subject,
        text_message,
        from_email,
        [to_email],
        fail_silently=False,
        html_message=html_message,
    )

def get_group_id(user) -> int:
    return user.follow_user_id or user.id