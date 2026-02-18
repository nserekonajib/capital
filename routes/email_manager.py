import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_class_invite_html(
        sender_email,
        sender_password,
        recipient_email,
        student_name,
        class_link,
        subject="NexusSchool Pro – Live Class Invitation",
        smtp_server="smtp.gmail.com",
        smtp_port=587):
    """
    Sends a professional NexusSchool Pro class invitation email (HTML only).
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"NexusSchool Pro <{sender_email}>"
        msg["To"] = recipient_email
        msg["Subject"] = subject

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color:#2d2d2d; line-height:1.6;">
            <h2 style="color:#0055A4;">NexusSchool Pro – Live Class Invitation</h2>

            <p>Dear {student_name},</p>

            <p>You are invited to attend your scheduled <b>live class session</b> on 
               <span style="color:#008037;">NexusSchool Pro</span>.</p>

            <div style="margin:25px 0; text-align:center;">
                <a href="{class_link}"
                   style="background-color:#0055A4; color:#ffffff; padding:12px 26px;
                          text-decoration:none; border-radius:6px; font-size:16px;
                          font-weight:bold;">
                    Join Live Class
                </a>
            </div>

            <p>If the button does not work, open this link in your browser:</p>
            <p><a href="{class_link}" style="color:#0055A4;">{class_link}</a></p>

            <br>
            <p>Regards,<br>
               <b>NexusSchool Pro Team</b><br>
               <small><i>Smart Learning. Smart Future.</i></small></p>
        </body>
        </html>
        """

        msg.attach(MIMEText(html, "html"))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()

        print(f"✅ Class invitation sent to {recipient_email}")
        return True

    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False



def generate_otp(length=6):
    """Generate a numeric OTP."""
    return ''.join(random.choices(string.digits, k=length))



def send_otp_email(
        sender_email,
        sender_password,
        recipient_email,
        otp,
        student_name=None,
        subject="NexusSchool Pro – OTP Verification"):
    """
    Sends OTP verification email for NexusSchool Pro accounts.
    Attempts TLS (587), falls back to SSL (465).
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"NexusSchool Pro <{sender_email}>"
        msg["To"] = recipient_email
        msg["Subject"] = subject

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color:#2d2d2d; line-height:1.6;">
            <h2 style="color:#0055A4;">NexusSchool Pro – OTP Verification</h2>

            <p>Hello {student_name or 'User'},</p>
            <p>Your one-time verification code is:</p>

            <div style="font-size:32px; font-weight:bold; color:#008037; margin:25px 0;">
                {otp}
            </div>

            <p>This code is valid for <b>10 minutes</b>.  
               Please do not share it with anyone.</p>

            <br>
            <p>Security Department,<br>
               <b>NexusSchool Pro</b></p>
        </body>
        </html>
        """

        msg.attach(MIMEText(html, "html"))

        # Attempt TLS
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
            server.quit()

            print(f"✅ OTP email sent via TLS to {recipient_email}")
            return True

        except Exception as e1:
            print(f"⚠️ TLS failed: {e1}. Trying SSL...")

            server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
            server.quit()

            print(f"✅ OTP email sent via SSL to {recipient_email}")
            return True

    except Exception as e2:
        print(f"❌ OTP sending failed: {e2}")
        return False
