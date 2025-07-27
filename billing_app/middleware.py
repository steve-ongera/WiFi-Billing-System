from django.shortcuts import redirect
from django.urls import reverse, resolve
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from .views import get_client_mac, get_client_ip
from .models import WifiSession
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class CaptivePortalMiddleware(MiddlewareMixin):
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.get_response = get_response
        
        # URLs that should ALWAYS bypass the captive portal
        self.bypass_urls = [
            '/admin/',
            '/static/',
            '/media/',
            '/portal/',
            '/payment/',
            '/process-payment/',
            '/internet-access/',
            '/__debug__/',  # Django debug toolbar
            '/favicon.ico',
        ]
        
        # URL names that should bypass (safer than hardcoded paths)
        self.bypass_url_names = [
            'portal_login',
            'select_plan', 
            'payment_page',
            'process_payment',
            'internet_access',
            'admin:index',
        ]

    def process_request(self, request):
        # Skip in development if explicitly disabled
        if (getattr(settings, 'ENVIRONMENT', 'development') == 'development' and 
            getattr(settings, 'DISABLE_CAPTIVE_PORTAL', False)):
            return None
        
        # Check if current URL should bypass captive portal
        if self.should_bypass(request):
            return None
        
        # Get client information
        client_mac = get_client_mac(request)
        client_ip = get_client_ip(request)
        
        # Log for debugging
        logger.debug(f"Captive portal check - IP: {client_ip}, MAC: {client_mac}, Path: {request.path}")
        
        # In development, create a test MAC if none found
        if not client_mac and getattr(settings, 'ENVIRONMENT', 'development') == 'development':
            client_mac = f"dev:mac:{hash(client_ip or '127.0.0.1') % 1000000:06d}"
            logger.debug(f"Development mode - using test MAC: {client_mac}")
        
        if client_mac:
            try:
                session = WifiSession.objects.get(mac_address=client_mac)
                
                # Check if session is valid and paid
                if (session.is_paid and 
                    session.expires_at and 
                    session.expires_at > timezone.now() and
                    session.is_active):
                    # Valid session - allow access
                    return None
                else:
                    # Invalid/expired session - redirect to portal
                    logger.debug(f"Invalid session for {client_mac} - redirecting to portal")
                    return redirect('portal_login')
                    
            except WifiSession.DoesNotExist:
                # New device - redirect to portal
                logger.debug(f"New device {client_mac} - redirecting to portal")
                return redirect('portal_login')
        else:
            # Can't identify device - redirect to portal (it will handle the error)
            logger.debug("Cannot identify device - redirecting to portal")
            return redirect('portal_login')
        
        return None
    
    def should_bypass(self, request):
        """Check if the current request should bypass captive portal"""
        
        # Check URL paths
        for bypass_url in self.bypass_urls:
            if request.path.startswith(bypass_url):
                return True
        
        # Check URL names (safer method)
        try:
            resolved_url = resolve(request.path_info)
            if resolved_url.url_name in self.bypass_url_names:
                return True
            
            # Check namespaced URLs (like admin:*)
            if resolved_url.namespace:
                full_name = f"{resolved_url.namespace}:{resolved_url.url_name}"
                if full_name in self.bypass_url_names or resolved_url.namespace in ['admin']:
                    return True
                    
        except Exception as e:
            logger.debug(f"Could not resolve URL {request.path}: {e}")
        
        return False

