#!/usr/bin/env python3
"""
Minimal Flask Integration for Social Event Image Sharing
Focus: Upload -> Immediate disconnect -> Clean UX
"""

from flask import Flask, request, render_template, redirect, jsonify
import os
import subprocess
import json
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/home/pi/event_images'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_client_ip():
    """Get real client IP"""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def log_event(ip, action, details=None):
    """Simple event logging"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'ip': ip,
        'action': action,
        'details': details
    }
    
    with open('/var/log/image-hotspot/events.log', 'a') as f:
        f.write(json.dumps(log_entry) + '\n')

def disconnect_user(ip):
    """Disconnect user from hotspot"""
    try:
        subprocess.run([
            '/usr/local/bin/manage-hotspot-users.sh', 
            'kick', 
            ip
        ], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

@app.route('/')
def index():
    """Landing page - redirect to upload"""
    client_ip = get_client_ip()
    log_event(client_ip, 'connected')
    return redirect('/upload')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Main upload endpoint"""
    client_ip = get_client_ip()
    
    if request.method == 'POST':
        if 'files[]' not in request.files:
            return jsonify({'error': 'No files selected'}), 400
        
        files = request.files.getlist('files[]')
        uploaded_files = []
        
        for file in files:
            if file and file.filename != '':
                # Secure filename with timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                original_name = secure_filename(file.filename)
                filename = f"{timestamp}_{original_name}"
                
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                uploaded_files.append(original_name)
        
        log_event(client_ip, 'uploaded', {'count': len(uploaded_files), 'files': uploaded_files})
        
        # Return success with disconnect option
        return render_template('upload_success.html', 
                             files=uploaded_files,
                             client_ip=client_ip,
                             total_uploaded=len(uploaded_files))
    
    log_event(client_ip, 'viewing_upload_page')
    return render_template('upload.html')

@app.route('/disconnect')
def auto_disconnect():
    """Auto-disconnect current user"""
    client_ip = get_client_ip()
    
    if disconnect_user(client_ip):
        log_event(client_ip, 'disconnected', 'user_requested')
        return render_template('disconnected.html')
    else:
        return render_template('disconnect_manual.html')

@app.route('/gallery')
def gallery():
    """Optional: View uploaded images (for event host)"""
    try:
        images = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                images.append(filename)
        
        images.sort(reverse=True)  # Newest first
        return render_template('gallery.html', images=images)
    except Exception as e:
        return f"Error loading gallery: {e}"

@app.route('/image/<filename>')
def serve_image(filename):
    """Serve uploaded images"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/stats')
def stats():
    """Simple stats for event host"""
    try:
        # Count files
        image_count = len([f for f in os.listdir(app.config['UPLOAD_FOLDER']) 
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))])
        
        # Count current connections
        result = subprocess.run([
            '/usr/local/bin/manage-hotspot-users.sh', 'count'
        ], capture_output=True, text=True)
        
        current_connections = int(result.stdout.strip()) if result.returncode == 0 else 0
        
        return jsonify({
            'images_uploaded': image_count,
            'current_connections': current_connections,
            'status': 'active'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)