#!/usr/bin/env python3
"""
QR Code and Flask Integration for Image Sharing Hotspot
This script helps generate QR codes and manage the Flask app integration
"""

import qrcode
import json
from io import BytesIO
import base64

def generate_wifi_qr(ssid, password, hidden=True):
    """
    Generate QR code for WiFi connection
    Format: WIFI:T:WPA;S:SSID;P:PASSWORD;H:true;;
    """
    qr_data = f"WIFI:T:WPA;S:{ssid};P:{password};H:{'true' if hidden else 'false'};;"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    return qr.make_image(fill_color="black", back_color="white")

def generate_combined_qr(ssid, password, upload_url="http://192.168.4.1:5000/upload"):
    """
    Generate QR that contains connection info and redirect URL
    This creates a more complex QR that apps like QR & Barcode Scanner can handle
    """
    # Create a JSON payload with both WiFi and URL info
    qr_payload = {
        "wifi": {
            "ssid": ssid,
            "password": password,
            "hidden": True,
            "security": "WPA"
        },
        "redirect": upload_url,
        "message": "1. Connect to WiFi network 2. Visit the URL to upload images"
    }
    
    # For most QR readers, we'll use a simple format
    # Advanced apps can parse JSON, simple ones get basic info
    simple_data = f"Connect to: {ssid}\nPassword: {password}\nThen visit: {upload_url}"
    
    qr = qrcode.QRCode(
        version=2,  # Bigger version for more data
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(simple_data)
    qr.make(fit=True)
    
    return qr.make_image(fill_color="black", back_color="white")

def save_qr_codes(ssid, password, output_dir="/home/pi/qr_codes/"):
    """Save QR codes as files"""
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    
    # WiFi-only QR
    wifi_qr = generate_wifi_qr(ssid, password)
    wifi_qr.save(f"{output_dir}wifi_connection.png")
    
    # Combined QR
    combined_qr = generate_combined_qr(ssid, password)
    combined_qr.save(f"{output_dir}complete_instructions.png")
    
    print(f"QR codes saved to {output_dir}")
    return output_dir

# Flask integration helpers
def get_client_ip(request):
    """Get client IP from Flask request"""
    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        return request.environ['REMOTE_ADDR']
    else:
        return request.environ['HTTP_X_FORWARDED_FOR']

def log_user_activity(ip, action, filename=None):
    """Log user activities for potential auto-disconnect"""
    import datetime
    
    log_entry = {
        'timestamp': datetime.datetime.now().isoformat(),
        'ip': ip,
        'action': action,
        'filename': filename
    }
    
    with open('/var/log/image-hotspot/user_activity.log', 'a') as f:
        f.write(json.dumps(log_entry) + '\n')

# Example Flask route modifications
FLASK_INTEGRATION_EXAMPLE = '''
from flask import Flask, request, render_template, redirect, url_for
import os
import subprocess
from datetime import datetime, timedelta

app = Flask(__name__)

# Track user sessions for auto-disconnect feature
user_sessions = {}

@app.route('/')
def index():
    client_ip = get_client_ip(request)
    
    # Log connection
    log_user_activity(client_ip, 'connected')
    
    # Track session start time
    user_sessions[client_ip] = {
        'connected_at': datetime.now(),
        'last_activity': datetime.now()
    }
    
    return redirect(url_for('upload'))

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    client_ip = get_client_ip(request)
    
    # Update last activity
    if client_ip in user_sessions:
        user_sessions[client_ip]['last_activity'] = datetime.now()
    
    if request.method == 'POST':
        # Handle file upload
        file = request.files['file']
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join('uploads', filename))
            
            # Log upload
            log_user_activity(client_ip, 'uploaded', filename)
            
            # Optional: Auto-disconnect after upload
            return render_template('upload_success.html', 
                                 disconnect_option=True,
                                 client_ip=client_ip)
    
    return render_template('upload.html')

@app.route('/disconnect/<ip>')
def disconnect_user(ip):
    """Allow user to self-disconnect"""
    try:
        # Use the management script to disconnect
        subprocess.run(['/usr/local/bin/manage-hotspot-users.sh', 'kick', ip], 
                      check=True)
        return "You have been disconnected. You can now reconnect to your regular WiFi."
    except:
        return "Disconnection failed. Please manually disconnect from WiFi settings."

@app.route('/status')
def status():
    """Show current connections (admin only)"""
    try:
        result = subprocess.run(['/usr/local/bin/manage-hotspot-users.sh', 'list'], 
                               capture_output=True, text=True)
        connections = result.stdout
        return f"<pre>{connections}</pre>"
    except:
        return "Unable to get status"

# Background task for auto-disconnect (optional)
def auto_disconnect_inactive_users():
    """Disconnect users who have been inactive for too long"""
    import threading
    import time
    
    def check_and_disconnect():
        while True:
            now = datetime.now()
            for ip, session in list(user_sessions.items()):
                # Disconnect if inactive for more than 30 minutes
                if now - session['last_activity'] > timedelta(minutes=30):
                    try:
                        subprocess.run(['/usr/local/bin/manage-hotspot-users.sh', 'kick', ip])
                        log_user_activity(ip, 'auto_disconnected')
                        del user_sessions[ip]
                    except:
                        pass
            time.sleep(300)  # Check every 5 minutes
    
    thread = threading.Thread(target=check_and_disconnect)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    auto_disconnect_inactive_users()  # Start background task
    app.run(host='0.0.0.0', port=5000, debug=False)
'''

def create_flask_template():
    """Create HTML templates with disconnect option"""
    
    upload_success_template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Upload Successful</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
        .success { color: green; font-size: 24px; margin-bottom: 30px; }
        .disconnect { background-color: #ff6b6b; color: white; padding: 15px 30px; 
                     text-decoration: none; border-radius: 5px; font-size: 18px; }
        .info { background-color: #f0f8ff; padding: 20px; margin: 20px; border-radius: 10px; }
    </style>
</head>
<body>
    <div class="success">✅ Image uploaded successfully!</div>
    
    <div class="info">
        <h3>What's next?</h3>
        <p>Your image has been uploaded to the server.</p>
        <p>Since this hotspot doesn't provide internet access, you may want to disconnect 
           and return to your regular WiFi network.</p>
    </div>
    
    {% if disconnect_option %}
    <a href="/disconnect/{{ client_ip }}" class="disconnect">
        Disconnect from Hotspot
    </a>
    <p><small>Or manually disconnect from your WiFi settings</small></p>
    {% endif %}
    
    <div style="margin-top: 30px;">
        <a href="/upload">Upload another image</a>
    </div>
</body>
</html>
'''
    
    return upload_success_template

if __name__ == "__main__":
    # Example usage
    ssid = "ImageShare_abc123"
    password = "ShareImg2024!"
    
    # Generate and save QR codes
    output_path = save_qr_codes(ssid, password)
    
    print(f"QR codes generated and saved to {output_path}")
    print("\nFlask integration example:")
    print("Save the FLASK_INTEGRATION_EXAMPLE code to your main Flask app")
    
    # Create templates directory and files
    os.makedirs("templates", exist_ok=True)
    with open("templates/upload_success.html", "w") as f:
        f.write(create_flask_template())
    
    print("HTML template created: templates/upload_success.html")