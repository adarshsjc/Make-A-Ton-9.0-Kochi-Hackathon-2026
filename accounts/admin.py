from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .forms import BrightloopUserCreationForm, BrightloopUserChangeForm
from .models import User, CustomerProfile

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = BrightloopUserChangeForm
    add_form = BrightloopUserCreationForm
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone", "role")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "role", "password1", "password2")}),)
    filter_horizontal = ("groups", "user_permissions")
    readonly_fields = ("date_joined", "last_login")

admin.site.register(CustomerProfile)
admin.site.site_header = "Brightloop Administration"
admin.site.site_title = "Brightloop Admin"
admin.site.index_title = "Subscription Management"
