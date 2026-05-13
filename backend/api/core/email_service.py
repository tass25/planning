"""Email service — sends transactional emails via SMTP."""

from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog
from config.settings import settings

log = structlog.get_logger()


def _build_verification_email(user_name: str, verification_url: str) -> tuple[str, str]:
    """Return (plain_text, html) for the verification email."""
    plain = (
        f"Hi {user_name},\n\n"
        f"Welcome to Codara! Please verify your email address by visiting:\n"
        f"{verification_url}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"If you didn't create this account, you can safely ignore this email.\n\n"
        f"— The Codara Team"
    )

    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#0d0f1a;font-family:'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0d0f1a;">
    <tr><td align="center" style="padding:40px 20px;">
      <table role="presentation" cellpadding="0" cellspacing="0" width="520" style="max-width:520px;width:100%;">

        <!-- Logo -->
        <tr><td align="center" style="padding-bottom:32px;">
          <table role="presentation" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding-right:10px;vertical-align:middle;">
                <div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#1e1446,#2d1b69,#3b2280);display:inline-block;"></div>
              </td>
              <td style="vertical-align:middle;">
                <span style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">cod<span style="color:#f59e0b;">ara</span></span>
              </td>
            </tr>
          </table>
        </td></tr>

        <!-- Card -->
        <tr><td>
          <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
                 style="background-color:#141627;border:1px solid rgba(255,255,255,0.06);border-radius:16px;overflow:hidden;">

            <!-- Gradient header bar -->
            <tr><td style="height:4px;background:linear-gradient(90deg,#f59e0b,#a855f7,#f59e0b);"></td></tr>

            <!-- Content -->
            <tr><td style="padding:40px 40px 32px;">
              <h1 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#ffffff;line-height:1.3;">
                Verify your email
              </h1>
              <p style="margin:0;font-size:15px;color:rgba(255,255,255,0.5);line-height:1.6;">
                Hi {user_name}, welcome to Codara. Confirm your email address to unlock all platform features.
              </p>
            </td></tr>

            <!-- Button -->
            <tr><td align="center" style="padding:0 40px 32px;">
              <a href="{verification_url}"
                 style="display:inline-block;padding:14px 48px;background:linear-gradient(135deg,#f59e0b,#d97706);
                        color:#0d0f1a;font-size:15px;font-weight:700;text-decoration:none;
                        border-radius:10px;letter-spacing:0.3px;
                        box-shadow:0 0 20px rgba(245,158,11,0.25);">
                Verify Email Address
              </a>
            </td></tr>

            <!-- Link fallback -->
            <tr><td style="padding:0 40px 32px;">
              <p style="margin:0;font-size:12px;color:rgba(255,255,255,0.3);line-height:1.6;">
                Or copy this link into your browser:<br>
                <a href="{verification_url}" style="color:#f59e0b;word-break:break-all;text-decoration:none;">{verification_url}</a>
              </p>
            </td></tr>

            <!-- Divider -->
            <tr><td style="padding:0 40px;"><div style="height:1px;background:rgba(255,255,255,0.06);"></div></td></tr>

            <!-- Info -->
            <tr><td style="padding:24px 40px 32px;">
              <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="width:50%;vertical-align:top;">
                    <p style="margin:0 0 4px;font-size:11px;font-weight:600;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:1px;">Expires</p>
                    <p style="margin:0;font-size:14px;color:rgba(255,255,255,0.7);">24 hours</p>
                  </td>
                  <td style="width:50%;vertical-align:top;">
                    <p style="margin:0 0 4px;font-size:11px;font-weight:600;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:1px;">Security</p>
                    <p style="margin:0;font-size:14px;color:rgba(255,255,255,0.7);">One-time use link</p>
                  </td>
                </tr>
              </table>
            </td></tr>

          </table>
        </td></tr>

        <!-- Footer -->
        <tr><td align="center" style="padding:28px 20px 0;">
          <p style="margin:0 0 6px;font-size:12px;color:rgba(255,255,255,0.25);line-height:1.6;">
            This email was sent by Codara because a new account was created with this address.
          </p>
          <p style="margin:0;font-size:11px;color:rgba(255,255,255,0.15);">
            If you didn't request this, you can safely ignore this email.
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return plain, html


def send_verification_email(to_email: str, user_name: str, token: str) -> bool:
    """Send a verification email. Returns True on success, False if SMTP is not configured or fails."""
    if not settings.smtp_host:
        log.warning("smtp_not_configured", msg="SMTP not configured — verification email not sent")
        return False

    verification_url = f"{settings.frontend_url}/verify-email?token={token}"
    plain_body, html_body = _build_verification_email(user_name, verification_url)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your email — Codara"
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if settings.smtp_use_tls:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)

        log.info("verification_email_sent", to=to_email)
        return True
    except Exception as exc:
        log.error("verification_email_failed", to=to_email, error=str(exc))
        return False
