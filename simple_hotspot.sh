#!/usr/bin/env bash
# Simplified Hotspot Setup for Image Sharing Project
# Based on RaspberryConnect.com script but simplified for specific use case

# Configuration variables
HOTSPOT_SSID="ImageShare_$(openssl rand -hex 3)"  # Random SSID for security
HOTSPOT_PASSWORD="ShareImg2024!"  # Change this to your preferred password
HOTSPOT_IP="192.168.4.1"
HOTSPOT_SUBNET="192.168.4.0/24"
HOTSPOT_DHCP_RANGE="192.168.4.2,192.168.4.20,255.255.255.0,12h"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

# Check for required packages
check_packages() {
    echo "Checking required packages..."
    
    if ! dpkg -s "hostapd" | grep 'Status: install ok installed' >/dev/null 2>&1; then
        echo "Installing hostapd..."
        apt update && apt install -y hostapd
    fi
    
    if ! dpkg -s "dnsmasq" | grep 'Status: install ok installed' >/dev/null 2>&1; then
        echo "Installing dnsmasq..."
        apt update && apt install -y dnsmasq
    fi
}

# Configure hostapd for hidden SSID
setup_hostapd() {
    echo "Configuring hostapd..."
    
    # Backup existing config
    if [ -f "/etc/hostapd/hostapd.conf" ]; then
        cp "/etc/hostapd/hostapd.conf" "/etc/hostapd/hostapd.conf.backup"
    fi
    
    # Get WiFi country code
    COUNTRY_CODE=$(grep "country=" /etc/wpa_supplicant/wpa_supplicant.conf | cut -d'=' -f2 | tr -d '\r\n' || echo "US")
    
    # Create hostapd config with hidden SSID
    cat > /etc/hostapd/hostapd.conf << EOF
# Hostapd config for Image Sharing Project
interface=wlan0
driver=nl80211

# Network name (SSID) - Hidden network
ssid=${HOTSPOT_SSID}
ignore_broadcast_ssid=1

# WiFi channel (1-13)
channel=7
country_code=${COUNTRY_CODE}

# WiFi security
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
wpa_passphrase=${HOTSPOT_PASSWORD}
rsn_pairwise=CCMP

# Hardware mode
hw_mode=g
ieee80211n=1
wmm_enabled=1
ht_capab=[HT40][SHORT-GI-20][DSSS_CCK-40]

# Connection limits
max_num_sta=10
EOF

    # Enable hostapd service
    systemctl unmask hostapd
    systemctl enable hostapd
}

# Configure dnsmasq for DHCP
setup_dnsmasq() {
    echo "Configuring dnsmasq..."
    
    # Backup existing config
    if [ -f "/etc/dnsmasq.conf" ]; then
        cp "/etc/dnsmasq.conf" "/etc/dnsmasq.conf.backup"
    fi
    
    # Create dnsmasq config
    cat > /etc/dnsmasq.conf << EOF
# dnsmasq config for Image Sharing Project
interface=wlan0
bind-interfaces
domain-needed
bogus-priv

# DHCP range
dhcp-range=${HOTSPOT_DHCP_RANGE}

# DNS settings (no internet, so use local only)
no-resolv
no-poll
server=8.8.8.8  # Backup DNS, won't be used without internet

# Captive portal redirect (optional)
address=/#/${HOTSPOT_IP}
EOF

    systemctl enable dnsmasq
}

# Configure network interface
setup_network() {
    echo "Configuring network interface..."
    
    # Configure static IP for wlan0
    cat >> /etc/dhcpcd.conf << EOF

# Static IP configuration for Image Sharing Hotspot
interface wlan0
static ip_address=${HOTSPOT_IP}/24
nohook wpa_supplicant
EOF
}

# Create systemd service for startup
create_service() {
    echo "Creating startup service..."
    
    cat > /etc/systemd/system/image-hotspot.service << EOF
[Unit]
Description=Image Sharing Hotspot
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/start-image-hotspot.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    # Create startup script
    cat > /usr/local/bin/start-image-hotspot.sh << 'EOF'
#!/bin/bash
# Startup script for Image Sharing Hotspot

# Ensure WiFi interface is up
ip link set wlan0 up

# Start services
systemctl start hostapd
systemctl start dnsmasq

# Optional: Log connections
mkdir -p /var/log/image-hotspot
echo "$(date): Hotspot started" >> /var/log/image-hotspot/hotspot.log
EOF

    chmod +x /usr/local/bin/start-image-hotspot.sh
    systemctl daemon-reload
    systemctl enable image-hotspot
}

# Create user management script (optional feature)
create_user_manager() {
    cat > /usr/local/bin/manage-hotspot-users.sh << 'EOF'
#!/bin/bash
# User management for Image Sharing Hotspot

LOGFILE="/var/log/image-hotspot/connections.log"
LEASEFILE="/var/lib/dhcp/dhcpd.leases"

case "$1" in
    "list")
        echo "Connected devices:"
        arp -a | grep -E "192\.168\.4\.[0-9]+" | awk '{print $1 " " $2}'
        ;;
    "count")
        arp -a | grep -E "192\.168\.4\.[0-9]+" | wc -l
        ;;
    "kick")
        if [ -n "$2" ]; then
            # Disconnect specific IP
            iptables -A INPUT -s "$2" -j DROP
            iptables -A OUTPUT -d "$2" -j DROP
            echo "$(date): Disconnected $2" >> "$LOGFILE"
            
            # Remove rules after 30 seconds to allow reconnection
            (sleep 30 && iptables -D INPUT -s "$2" -j DROP && iptables -D OUTPUT -d "$2" -j DROP) &
        fi
        ;;
    "auto-disconnect")
        # Auto-disconnect users after specified time (in minutes)
        TIMEOUT=${2:-30}  # Default 30 minutes
        
        while true; do
            # Check for users connected longer than timeout
            # This would need more sophisticated tracking
            sleep 300  # Check every 5 minutes
        done
        ;;
esac
EOF
    chmod +x /usr/local/bin/manage-hotspot-users.sh
}

# Create QR code data
generate_qr_info() {
    echo "Generating connection information for QR code..."
    
    # WiFi QR format: WIFI:T:WPA;S:SSID;P:PASSWORD;H:true;;
    QR_DATA="WIFI:T:WPA;S:${HOTSPOT_SSID};P:${HOTSPOT_PASSWORD};H:true;;"
    
    cat > /home/pi/hotspot_info.txt << EOF
=== Image Sharing Hotspot Configuration ===

SSID: ${HOTSPOT_SSID}
Password: ${HOTSPOT_PASSWORD}
IP Address: ${HOTSPOT_IP}
Hidden Network: YES

QR Code Data (for WiFi connection):
${QR_DATA}

Flask App URL: http://${HOTSPOT_IP}:5000

=== QR Code Should Redirect To ===
After connection, redirect to: http://${HOTSPOT_IP}:5000/upload

=== Management Commands ===
- List connected devices: sudo /usr/local/bin/manage-hotspot-users.sh list
- Count connections: sudo /usr/local/bin/manage-hotspot-users.sh count
- Disconnect IP: sudo /usr/local/bin/manage-hotspot-users.sh kick [IP]
- View logs: tail -f /var/log/image-hotspot/hotspot.log
EOF

    echo "Configuration saved to /home/pi/hotspot_info.txt"
    echo ""
    echo "=== IMPORTANT ==="
    echo "SSID: ${HOTSPOT_SSID}"
    echo "Password: ${HOTSPOT_PASSWORD}"
    echo "QR Data: ${QR_DATA}"
}

# Main installation function
install_hotspot() {
    echo "Installing Image Sharing Hotspot..."
    
    check_packages
    setup_hostapd
    setup_dnsmasq
    setup_network
    create_service
    create_user_manager
    generate_qr_info
    
    echo ""
    echo "Installation complete!"
    echo "Please reboot your Raspberry Pi to activate the hotspot."
    echo ""
    echo "After reboot, your Pi will automatically start as a hidden hotspot."
    echo "Users will need to manually connect using the SSID and password shown above."
}

# Uninstall function
uninstall_hotspot() {
    echo "Uninstalling Image Sharing Hotspot..."
    
    systemctl stop hostapd
    systemctl stop dnsmasq
    systemctl disable hostapd
    systemctl disable dnsmasq
    systemctl disable image-hotspot
    
    # Restore backups
    if [ -f "/etc/hostapd/hostapd.conf.backup" ]; then
        mv "/etc/hostapd/hostapd.conf.backup" "/etc/hostapd/hostapd.conf"
    fi
    
    if [ -f "/etc/dnsmasq.conf.backup" ]; then
        mv "/etc/dnsmasq.conf.backup" "/etc/dnsmasq.conf"
    fi
    
    # Remove added lines from dhcpcd.conf
    sed -i '/# Static IP configuration for Image Sharing Hotspot/,$d' /etc/dhcpcd.conf
    
    # Remove service files
    rm -f /etc/systemd/system/image-hotspot.service
    rm -f /usr/local/bin/start-image-hotspot.sh
    rm -f /usr/local/bin/manage-hotspot-users.sh
    
    systemctl daemon-reload
    
    echo "Uninstallation complete. Please reboot."
}

# Menu
case "$1" in
    "install"|"")
        install_hotspot
        ;;
    "uninstall")
        uninstall_hotspot
        ;;
    "info")
        if [ -f "/home/pi/hotspot_info.txt" ]; then
            cat /home/pi/hotspot_info.txt
        else
            echo "Hotspot not installed yet."
        fi
        ;;
    *)
        echo "Usage: $0 [install|uninstall|info]"
        echo "  install   - Install and configure the hotspot (default)"
        echo "  uninstall - Remove the hotspot configuration"
        echo "  info      - Show hotspot connection information"
        ;;
esac