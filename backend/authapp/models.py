import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

class OtpCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=50)  # e.g. "login", "register"
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_for_user(cls, user, purpose="login", ttl_minutes=5):
        from .utils import generate_otp_code
        code = generate_otp_code()
        return cls.objects.create(
            user=user,
            email=user.email,
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        )

    def is_valid(self, code: str) -> bool:
        if self.is_used:
            return False
        if timezone.now() > self.expires_at:
            return False
        return self.code == code
