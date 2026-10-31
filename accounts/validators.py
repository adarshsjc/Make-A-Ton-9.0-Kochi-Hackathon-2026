from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

class PasswordComplexityValidator:
    """Challenge requirement: uppercase, lowercase and at least one special character."""
    def validate(self, password, user=None):
        if not any(char.isupper() for char in password):
            raise ValidationError(_("Password must contain at least one uppercase letter."), code="password_no_upper")
        if not any(char.islower() for char in password):
            raise ValidationError(_("Password must contain at least one lowercase letter."), code="password_no_lower")
        if not any(not char.isalnum() for char in password):
            raise ValidationError(_("Password must contain at least one special character."), code="password_no_special")

    def get_help_text(self):
        return _("Your password must contain uppercase, lowercase and special characters.")
