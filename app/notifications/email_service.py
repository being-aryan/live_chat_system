from email.message import EmailMessage
from email.utils import formataddr
from html import escape

import aiosmtplib

from app.config import settings


class EmailService:
    @staticmethod
    def _validate_smtp_settings() -> tuple[str, str, str]:
        username = settings.SMTP_USERNAME.strip()
        password = settings.SMTP_PASSWORD
        sender = settings.SMTP_FROM_EMAIL.strip() or username
        if not settings.SMTP_HOST or not username or not password or not sender:
            raise RuntimeError("SMTP configuration is incomplete")
        if not settings.SMTP_USE_TLS:
            raise RuntimeError("SMTP STARTTLS must be enabled for credential security")
        return username, password, sender

    async def send_email(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> None:
        username, password, sender = self._validate_smtp_settings()
        message = EmailMessage()
        message["From"] = formataddr((settings.SMTP_FROM_NAME, sender))
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=username,
            password=password,
            start_tls=settings.SMTP_USE_TLS,
            timeout=settings.SMTP_TIMEOUT,
        )

    async def send_verification_otp(
        self,
        recipient: str,
        username: str,
        otp: str,
    ) -> None:
        safe_username = escape(username)
        subject = "Verify your Live Chat account"
        text_body = (
            f"Hi {username},\n\n"
            f"Your email verification code is {otp}.\n"
            f"It expires in {settings.OTP_TTL_SECONDS // 60} minutes.\n\n"
            "If you did not create this account, you can ignore this email."
        )
        html_body = f"""\
        <!doctype html>
        <html lang="en">
          <body style="font-family:Arial,sans-serif;color:#222;line-height:1.5">
            <h2>Verify your email address</h2>
            <p>Hi {safe_username},</p>
            <p>Use the verification code below to verify your Live Chat account:</p>
            <p style="font-size:30px;font-weight:700;letter-spacing:8px">{otp}</p>
            <p>This code expires in {settings.OTP_TTL_SECONDS // 60} minutes.</p>
            <p>If you did not create this account, you can ignore this email.</p>
          </body>
        </html>
        """
        await self.send_email(
            recipient=recipient,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )


email_service = EmailService()
