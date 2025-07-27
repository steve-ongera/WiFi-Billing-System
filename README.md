# WiFi Billing System Setup Guide

## Overview
This system creates a captive portal that blocks internet access until users pay for WiFi access. It includes payment processing, session management, and automatic access control.

## Prerequisites
- Linux server (Ubuntu/Debian recommended)
- Python 3.8+
- Router with configurable firewall rules
- Payment gateway account (Stripe recommended)
- Domain name pointing to your server

## Installation Steps

### 1. System Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install python3 python3-pip python3-venv nginx iptables-persistent

# Create project directory
mkdir wifi_billing_system
cd wifi_billing_system

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Django and dependencies
pip install django stripe requests
```

### 2. Django Project Setup
```bash
# Create Django project
django-admin startproject wifi_billing .
cd wifi_billing

# Create the wifi_portal app
python manage.py startapp wifi_portal

# Create necessary directories
mkdir -p templates/wifi_portal
mkdir -p management/commands
mkdir -p static
```

### 3. Database Setup
```bash
# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Add sample payment plans
python manage.py shell
```

In the Django shell, add sample plans:
```python
from wifi_portal.models import PaymentPlan

PaymentPlan.objects.create(
    name="1 Hour Access",
    price=2.00,
    duration_hours=1,
    description="Perfect for quick browsing"
)

PaymentPlan.objects.create(
    name="4 Hour Access", 
    price=5.00,
    duration_hours=4,
    description="Great for work sessions"
)

PaymentPlan.objects.create(
    name="24 Hour Access",
    price=10.00, 
    duration_hours=24,
    description="Full day unlimited access"
)
```

### 4. Network Configuration

#### Router Setup
Configure your router to redirect all HTTP traffic to your server:

1. **Enable Captive Portal Mode**: Most routers have this in advanced settings
2. **Set Redirect URL**: Point to your server IP (e.g., `http://192.168.1.100`)
3. **Configure DHCP**: Ensure your server is the gateway or can intercept traffic

#### Firewall Rules (iptables)
```bash
# Block all internet access by default
sudo iptables -I FORWARD -i wlan0 -j DROP

# Allow access to your captive portal server
sudo iptables -I FORWARD -i wlan0 -d YOUR_SERVER_IP -j ACCEPT

# Allow DNS (required for captive portal detection)
sudo iptables -I FORWARD -i wlan0 -p udp --dport 53 -j ACCEPT

# Save rules
sudo netfilter-persistent save
```

#### DNS Configuration
Set up DNS redirects for captive portal detection:

```bash
# Edit dnsmasq configuration
sudo nano /etc/dnsmasq.conf

# Add these lines:
address=/captive.apple.com/YOUR_SERVER_IP
address=/connectivitycheck.gstatic.com/YOUR_SERVER_IP
address=/www.msftconnecttest.com/YOUR_SERVER_IP
```

### 5. Nginx Configuration
```nginx
# /etc/nginx/sites-available/wifi_portal
server {
    listen 80 default_server;
    server_name _;
    
    # Redirect all traffic to captive portal
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Serve static files
    location /static/ {
        alias /path/to/your/project/static/;
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/wifi_portal /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 6. Payment Gateway Setup

#### Stripe Configuration
1. Create a Stripe account at https://stripe.com
2. Get your API keys from the dashboard
3. Update `settings.py`:

```python
# Payment settings
STRIPE_PUBLIC_KEY = 'pk_test_your_public_key_here'
STRIPE_SECRET_KEY = 'sk_test_your_secret_key_here'
```

#### Alternative Payment Gateways
You can integrate other payment providers by modifying the `process_payment` view:

```python
# For PayPal
import paypalrestsdk

# For local mobile money (M-Pesa, etc.)
# Add appropriate SDK and configuration
```

### 7. Security Configuration

#### SSL/HTTPS Setup (Recommended)
```bash
# Install Let's Encrypt
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

#### Additional Security
```python
# In settings.py
SECURE_SSL_REDIRECT = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Rate limiting (install django-ratelimit)
# pip install django-ratelimit
```

### 8. System Service Setup

Create a systemd service for your Django app:

```bash
# /etc/systemd/system/wifi-portal.service
[Unit]
Description=WiFi Portal Django App
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/wifi_billing_system
Environment=PATH=/path/to/wifi_billing_system/venv/bin
ExecStart=/path/to/wifi_billing_system/venv/bin/python manage.py runserver 127.0.0.1:8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable wifi-portal
sudo systemctl start wifi-portal
```

### 9. Monitoring and Maintenance

#### Log Management
```bash
# Django logs
mkdir -p /var/log/wifi-portal

# Add to settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/var/log/wifi-portal/django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

#### Automated Session Cleanup
Set up a cron job to clean expired sessions:

```bash
# Add to crontab
sudo crontab -e

# Run cleanup every 5 minutes
*/5 * * * * cd /path/to/wifi_billing_system && /path/to/venv/bin/python manage.py cleanup_expired_sessions
```

### 10. Testing the System

#### Test Flow
1. Connect a device to your WiFi network
2. Try to access any website - should redirect to captive portal
3. Select a payment plan and complete payment
4. Verify internet access is granted
5. Wait for session to expire and verify access is blocked

#### Debug Commands
```bash
# Check active sessions
python manage.py shell
>>> from wifi_portal.models import WifiSession
>>> WifiSession.objects.filter(is_active=True)

# View iptables rules
sudo iptables -L -n

# Check Django logs
tail -f /var/log/wifi-portal/django.log

# Test payment processing
curl -X POST http://localhost:8000/process-payment/ \
  -H "Content-Type: application/json" \
  -d '{"test": "payment"}'
```

## Advanced Features

### 1. Mobile Money Integration
For regions using mobile money (M-Pesa, MTN Mobile Money, etc.):

```python
# Add to views.py
def process_mobile_payment(request):
    if request.method == 'POST':
        phone_number = request.POST.get('phone')
        amount = request.POST.get('amount')
        
        # Integrate with mobile money API
        # Example for M-Pesa
        response = initiate_mpesa_payment(phone_number, amount)
        
        if response['success']:
            return JsonResponse({'success': True, 'transaction_id': response['id']})
        
        return JsonResponse({'success': False, 'error': response['error']})
```

### 2. Bandwidth Throttling
```python
# Add to models.py
class PaymentPlan(models.Model):
    # ... existing fields ...
    max_speed_mbps = models.IntegerField(default=10)  # Speed limit
    
def apply_bandwidth_limit(mac_address, speed_limit):
    """Apply bandwidth throttling using tc (traffic control)"""
    subprocess.run([
        'sudo', 'tc', 'qdisc', 'add', 'dev', 'wlan0', 
        'handle', '1:', 'root', 'htb'
    ])
    subprocess.run([
        'sudo', 'tc', 'class', 'add', 'dev', 'wlan0',
        'parent', '1:', 'classid', '1:1', 'htb',
        'rate', f'{speed_limit}mbit'
    ])
```

### 3. Multi-Language Support
```python
# Add to settings.py
USE_I18N = True
LANGUAGES = [
    ('en', 'English'),
    ('sw', 'Swahili'),
    ('fr', 'French'),
]

# Install django-modeltranslation
pip install django-modeltranslation
```

### 4. Analytics Dashboard
```python
# Add to models.py
class UsageStatistics(models.Model):
    date = models.DateField(auto_now_add=True)
    total_sessions = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unique_devices = models.IntegerField(default=0)
    
# Add analytics view
def analytics_dashboard(request):
    stats = UsageStatistics.objects.all().order_by('-date')[:30]
    return render(request, 'analytics.html', {'stats': stats})
```

## Troubleshooting

### Common Issues

1. **Devices not redirecting to portal**
   - Check DNS configuration
   - Verify iptables rules
   - Ensure router captive portal is enabled

2. **Payment processing fails**
   - Verify payment gateway credentials
   - Check network connectivity to payment API
   - Review Django logs for errors

3. **Internet access not granted after payment**
   - Check iptables rules are being applied
   - Verify MAC address detection
   - Review session management logic

4. **Sessions not expiring**
   - Ensure cleanup cron job is running
   - Check timezone settings
   - Verify expires_at field is set correctly

### Performance Optimization
```python
# Add database indexes
class Meta:
    indexes = [
        models.Index(fields=['mac_address']),
        models.Index(fields=['expires_at']),
        models.Index(fields=['is_paid', 'is_active']),
    ]

# Use connection pooling
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'OPTIONS': {
            'MAX_CONNS': 20,
            'CONN_MAX_AGE': 0,
        },
    }
}
```

## Security Considerations

1. **Input Validation**: Always validate and sanitize user inputs
2. **Rate Limiting**: Implement rate limiting on payment endpoints
3. **HTTPS**: Use SSL certificates for secure transactions
4. **Database Security**: Use strong database passwords and restrict access
5. **Regular Updates**: Keep Django and dependencies updated
6. **Monitoring**: Set up monitoring for suspicious activities

## Legal Considerations

1. **Terms of Service**: Create clear terms for WiFi usage
2. **Privacy Policy**: Comply with local data protection laws
3. **Payment Compliance**: Follow PCI DSS if handling card data directly
4. **User Consent**: Obtain proper consent for data collection

This system provides a complete WiFi billing solution with payment processing, session management, and automatic access control. Customize it according to your specific needs and local requirements.