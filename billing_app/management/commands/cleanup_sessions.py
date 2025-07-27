
# Management command to clean up expired sessions
# management/commands/cleanup_sessions.py
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
            # Block access
            block_internet_access(session.mac_address, session.ip_address)
            
            # Update session
            session.is_active = False
            session.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'Blocked access for {session.mac_address}')
            )