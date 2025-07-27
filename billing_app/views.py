from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta
import json
import subprocess
import re
from .models import WifiSession, PaymentPlan
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import json
import subprocess
import re
import requests
import platform
from .models import WifiSession, PaymentPlan


def get_client_mac(request):
    """Get MAC address from ARP table using IP - works in both environments"""
    client_ip = get_client_ip(request)
    
    # Development fallback - use a mock MAC for testing
    if settings.ENVIRONMENT == 'development' and client_ip in ['127.0.0.1', '::1']:
        return f"dev:mac:{client_ip.replace('.', ':')[:17]}"
    
    try:
        # Try different ARP commands based on OS
        if platform.system() == 'Darwin':  # macOS
            arp_output = subprocess.check_output(['arp', '-n', client_ip]).decode('utf-8')
        else:  # Linux
            arp_output = subprocess.check_output(['arp', '-n', client_ip]).decode('utf-8')
        
        mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', arp_output)
        if mac_match:
            return mac_match.group(0).lower()
    except subprocess.CalledProcessError:
        # Fallback: try alternative methods
        try:
            # Try ip neighbor (newer Linux systems)
            ip_output = subprocess.check_output(['ip', 'neighbor', 'show', client_ip]).decode('utf-8')
            mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', ip_output)
            if mac_match:
                return mac_match.group(0).lower()
        except:
            pass
    except Exception as e:
        print(f"Error getting MAC address: {e}")
    
    return None


def get_client_ip(request):
    """Get client IP address with better detection"""
    # Check for forwarded IP (when behind proxy/router)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    # Additional headers to check
    if not ip or ip == '127.0.0.1':
        ip = (request.META.get('HTTP_X_REAL_IP') or 
              request.META.get('HTTP_CF_CONNECTING_IP') or
              request.META.get('REMOTE_ADDR'))
    
    return ip


def portal_login(request):
    """Main captive portal page with environment awareness"""
    client_ip = get_client_ip(request)
    client_mac = get_client_mac(request)
    
    # Development mode - allow simulation
    if settings.ENVIRONMENT == 'development' and not client_mac:
        client_mac = f"dev:mac:{hash(client_ip) % 1000000:06d}"
    
    if not client_mac:
        return render(request, 'error.html', {
            'error': 'Unable to identify device',
            'debug_info': {
                'ip': client_ip,
                'environment': settings.ENVIRONMENT
            } if settings.DEBUG else None
        })
    
    # Check if session exists and is paid
    try:
        session = WifiSession.objects.get(mac_address=client_mac)
        if session.is_paid and session.expires_at and session.expires_at > timezone.now():
            return redirect('internet_access')
    except WifiSession.DoesNotExist:
        session = WifiSession.objects.create(
            mac_address=client_mac,
            ip_address=client_ip
        )
    
    plans = PaymentPlan.objects.filter(is_active=True)
    
    return render(request, 'login.html', {
        'session': session,
        'plans': plans,
        'client_ip': client_ip,
        'client_mac': client_mac,
        'environment': settings.ENVIRONMENT
    })


def allow_internet_access(mac_address, ip_address):
    """Allow internet access with multiple methods"""
    method = getattr(settings, 'TRAFFIC_CONTROL_METHOD', 'simulation')
    
    if method == 'iptables':
        return allow_access_iptables(mac_address, ip_address)
    elif method == 'router_api':
        return allow_access_router_api(mac_address, ip_address)
    else:
        # Simulation mode for development
        print(f"SIMULATION: Allowing access for MAC: {mac_address}, IP: {ip_address}")
        return True


def allow_access_iptables(mac_address, ip_address):
    """Allow access using iptables (Linux systems)"""
    try:
        # Create custom chain if it doesn't exist
        subprocess.run([
            'sudo', 'iptables', '-N', 'CAPTIVE_PORTAL'
        ], check=False)  # Don't fail if chain exists
        
        # Add rule to allow this MAC
        subprocess.run([
            'sudo', 'iptables', '-I', 'CAPTIVE_PORTAL',
            '-m', 'mac', '--mac-source', mac_address,
            '-j', 'ACCEPT'
        ], check=True)
        
        # Also allow by IP as backup
        subprocess.run([
            'sudo', 'iptables', '-I', 'CAPTIVE_PORTAL',
            '-s', ip_address,
            '-j', 'ACCEPT'
        ], check=True)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to allow access via iptables for {mac_address}: {e}")
        return False


def allow_access_router_api(mac_address, ip_address):
    """Allow access via router API (for mobile hotspot)"""
    try:
        # This depends on your router's API
        # Example for common router APIs:
        
        # Option 1: Add to allowed MAC list
        api_url = f"http://{settings.ROUTER_IP}/api/whitelist/add"
        payload = {
            'mac': mac_address,
            'description': f'Paid user {mac_address}'
        }
        
        response = requests.post(
            api_url,
            json=payload,
            auth=(settings.ROUTER_USERNAME, settings.ROUTER_PASSWORD),
            timeout=5
        )
        
        if response.status_code == 200:
            return True
            
        # Option 2: Disable firewall for this device
        # api_url = f"http://{settings.ROUTER_IP}/api/firewall/allow"
        # ... similar implementation
        
        return False
        
    except requests.RequestException as e:
        print(f"Failed to allow access via router API for {mac_address}: {e}")
        return False


def block_internet_access(mac_address, ip_address=None):
    """Block internet access"""
    method = getattr(settings, 'TRAFFIC_CONTROL_METHOD', 'simulation')
    
    if method == 'iptables':
        return block_access_iptables(mac_address, ip_address)
    elif method == 'router_api':
        return block_access_router_api(mac_address)
    else:
        print(f"SIMULATION: Blocking access for MAC: {mac_address}")
        return True


def block_access_iptables(mac_address, ip_address):
    """Block access using iptables"""
    try:
        subprocess.run([
            'sudo', 'iptables', '-D', 'CAPTIVE_PORTAL',
            '-m', 'mac', '--mac-source', mac_address,
            '-j', 'ACCEPT'
        ], check=True)
        
        if ip_address:
            subprocess.run([
                'sudo', 'iptables', '-D', 'CAPTIVE_PORTAL',
                '-s', ip_address,
                '-j', 'ACCEPT'
            ], check=True)
        
        return True
    except subprocess.CalledProcessError:
        return False


def block_access_router_api(mac_address):
    """Block access via router API"""
    try:
        api_url = f"http://{settings.ROUTER_IP}/api/whitelist/remove"
        payload = {'mac': mac_address}
        
        response = requests.post(
            api_url,
            json=payload,
            auth=(settings.ROUTER_USERNAME, settings.ROUTER_PASSWORD),
            timeout=5
        )
        
        return response.status_code == 200
    except requests.RequestException:
        return False



def select_plan(request, plan_id):
    """Handle plan selection and redirect to payment"""
    client_mac = get_client_mac(request)
    if not client_mac:
        return JsonResponse({'error': 'Unable to identify device'}, status=400)
    
    plan = get_object_or_404(PaymentPlan, id=plan_id)
    session = WifiSession.objects.get(mac_address=client_mac)
    
    # Store selected plan in session
    request.session['selected_plan_id'] = plan.id
    request.session['wifi_session_id'] = str(session.session_id)
    
    return redirect('payment_page')

def payment_page(request):
    """Payment processing page"""
    plan_id = request.session.get('selected_plan_id')
    if not plan_id:
        return redirect('portal_login')
    
    plan = get_object_or_404(PaymentPlan, id=plan_id)
    
    return render(request, 'payment.html', {
        'plan': plan,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY
    })

@csrf_exempt
def process_payment(request):
    """Process payment (simplified version - integrate with your payment gateway)"""
    if request.method == 'POST':
        data = json.loads(request.body)
        
        # In a real implementation, you would process the payment with Stripe/PayPal
        # For demo purposes, we'll simulate successful payment
        payment_successful = True  # Replace with actual payment processing
        
        if payment_successful:
            client_mac = get_client_mac(request)
            plan_id = request.session.get('selected_plan_id')
            
            if client_mac and plan_id:
                plan = PaymentPlan.objects.get(id=plan_id)
                session = WifiSession.objects.get(mac_address=client_mac)
                
                # Update session with payment info
                session.is_paid = True
                session.payment_amount = plan.price
                session.payment_id = f"pay_{session.session_id}"
                session.expires_at = timezone.now() + timedelta(hours=plan.duration_hours)
                session.is_active = True
                session.save()
                
                # Allow internet access
                allow_internet_access(client_mac, session.ip_address)
                
                return JsonResponse({'success': True, 'redirect': '/internet-access/'})
        
        return JsonResponse({'success': False, 'error': 'Payment failed'})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

def internet_access(request):
    """Success page after payment"""
    client_mac = get_client_mac(request)
    try:
        session = WifiSession.objects.get(mac_address=client_mac, is_paid=True)
        return render(request, 'success.html', {
            'session': session,
            'expires_at': session.expires_at
        })
    except WifiSession.DoesNotExist:
        return redirect('portal_login')

def allow_internet_access(mac_address, ip_address):
    """Add firewall rule to allow internet access"""
    try:
        # Example iptables command - adjust based on your setup
        subprocess.run([
            'sudo', 'iptables', '-I', 'FORWARD', 
            '-m', 'mac', '--mac-source', mac_address,
            '-j', 'ACCEPT'
        ], check=True)
        
        # Alternative: Add to router's allowed MAC list
        # This would depend on your router's API
        
    except subprocess.CalledProcessError:
        print(f"Failed to allow access for {mac_address}")

def block_internet_access(mac_address):
    """Remove firewall rule to block internet access"""
    try:
        subprocess.run([
            'sudo', 'iptables', '-D', 'FORWARD',
            '-m', 'mac', '--mac-source', mac_address,
            '-j', 'ACCEPT'
        ], check=True)
    except subprocess.CalledProcessError:
        print(f"Failed to block access for {mac_address}")