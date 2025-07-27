from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta
import json
import subprocess
import re
from .models import WifiSession, PaymentPlan


def get_client_mac(request):
    """Get MAC address from ARP table using IP"""
    client_ip = get_client_ip(request)
    try:
        # Get MAC address from ARP table
        arp_output = subprocess.check_output(['arp', '-n', client_ip]).decode('utf-8')
        mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', arp_output)
        if mac_match:
            return mac_match.group(0).lower()
    except:
        pass
    return None

def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def portal_login(request):
    """Main captive portal page"""
    client_ip = get_client_ip(request)
    client_mac = get_client_mac(request)
    
    if not client_mac:
        return render(request, 'wifi_portal/error.html', {
            'error': 'Unable to identify device'
        })
    
    # Check if session exists and is paid
    try:
        session = WifiSession.objects.get(mac_address=client_mac)
        if session.is_paid and session.expires_at and session.expires_at > timezone.now():
            # User has valid paid session
            return redirect('internet_access')
    except WifiSession.DoesNotExist:
        # Create new session
        session = WifiSession.objects.create(
            mac_address=client_mac,
            ip_address=client_ip
        )
    
    # Get available payment plans
    plans = PaymentPlan.objects.filter(is_active=True)
    
    return render(request, 'wifi_portal/login.html', {
        'session': session,
        'plans': plans,
        'client_ip': client_ip,
        'client_mac': client_mac
    })

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
    
    return render(request, 'wifi_portal/payment.html', {
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
        return render(request, 'wifi_portal/success.html', {
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