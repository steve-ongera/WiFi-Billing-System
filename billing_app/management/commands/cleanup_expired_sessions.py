from django.core.management.base import BaseCommand
from django.utils import timezone
from billing_app.models import WifiSession
from billing_app.views import block_internet_access

class Command(BaseCommand):
    help = 'Clean up expired WiFi sessions'

    def handle(self, *args, **options):
        expired_sessions = WifiSession.objects.filter(
            expires_at__lt=timezone.now(),
            is_active=True
        )
        
        for session in expired_sessions:
            # Block internet access
            block_internet_access(session.mac_address)
            
            # Deactivate session
            session.is_active = False
            session.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'Expired session for {session.mac_address}')
            )