from allauth.account.adapter import DefaultAccountAdapter

from core import emails

# allauth email template prefix -> core.emails key
ALLAUTH_EMAILS = {
    "account/email/password_reset_key": "password_reset",
    "account/email/unknown_account": "unknown_account",
}


class AccountAdapter(DefaultAccountAdapter):
    """Route allauth's emails through core.emails so every email shares one pipeline."""

    def send_mail(self, template_prefix, email, context):
        key = ALLAUTH_EMAILS.get(template_prefix)
        if key is None:
            return super().send_mail(template_prefix, email, context)
        emails.send(key, [email], context)
