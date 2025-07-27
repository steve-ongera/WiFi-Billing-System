from django.shortcuts import redirect
from django.urls import reverse
from .views import get_client_mac, get_client_ip
from .models import WifiSession
from django.utils import timezone

class CaptivePortalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip middleware for admin and static files
        if (request.path.startswith('/admin/') or 
            request.path.startswith('/static/') or
            request.path.startswith('/portal/') or
            request.path in ['/payment/', '/process-payment/', '/internet-access/']):
            return self.get_response(request)
        
        client_mac = get_client_mac(request)
        if client_mac:
            try:
                session = WifiSession.objects.get(mac_address=client_mac)
                if not (session.is_paid and session.expires_at and 
                       session.expires_at > timezone.now()):
                    # Redirect to captive portal
                    return redirect('portal_login')
            except WifiSession.DoesNotExist:
                # New device, redirect to portal
                return redirect('portal_login')
        
        return self.get_response(request)