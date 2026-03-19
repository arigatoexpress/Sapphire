# Raspberry Pi as Ethernet Bridge for Windows Laptop

## Problem
- Old Windows laptop cannot connect to WiFi
- Laptop is connected to Pi via Ethernet (through dock)
- Need to use Pi's WiFi connection to give laptop internet access

## Solution: Pi as Network Bridge

```
Internet ←→ Wi-Fi ←→ Raspberry Pi ←[Ethernet]← Windows Laptop (via dock)
                        (Bridge)
```

## Step 1: Configure Raspberry Pi as Bridge

### On the Raspberry Pi (via SSH from your Mac or direct keyboard/monitor):

```bash
# Check current network setup
ip addr show

# You should see:
# - wlan0 (WiFi with internet)
# - eth0 (Ethernet connected to laptop)
```

### Enable IP Forwarding

```bash
# Edit sysctl config
sudo nano /etc/sysctl.conf

# Find and uncomment this line:
net.ipv4.ip_forward=1

# Apply immediately
sudo sysctl -w net.ipv4.ip_forward=1
```

### Configure DHCP Server on Ethernet

```bash
# Install dnsmasq (lightweight DHCP/DNS server)
sudo apt update
sudo apt install dnsmasq -y

# Backup original config
sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.backup

# Create new config
sudo nano /etc/dnsmasq.conf
```

Add this to the file:
```
interface=eth0
dhcp-range=192.168.4.2,192.168.4.100,255.255.255.0,12h
dhcp-option=3,192.168.4.1
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
server=8.8.4.4
listen-address=127.0.0.1,192.168.4.1
bind-interfaces
```

### Set Static IP on Ethernet Interface

```bash
# Edit DHCP config
sudo nano /etc/dhcpcd.conf

# Add at the bottom:
interface eth0
static ip_address=192.168.4.1/24
nohook wpa_supplicant
```

### Configure NAT (Network Address Translation)

```bash
# Install iptables-persistent
sudo apt install iptables-persistent -y

# Add NAT rule
sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
sudo iptables -A FORWARD -i wlan0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A FORWARD -i eth0 -o wlan0 -j ACCEPT

# Save rules
sudo netfilter-persistent save
```

### Restart Services

```bash
# Restart networking
sudo systemctl restart dhcpcd

# Start dnsmasq
sudo systemctl enable dnsmasq
sudo systemctl restart dnsmasq

# Check status
sudo systemctl status dnsmasq
```

## Step 2: Configure Windows Laptop

On the Windows laptop:

1. **Open Network Settings**
   - Settings → Network & Internet → Ethernet

2. **Set to Automatic (DHCP)**
   - IP assignment: Automatic (DHCP)
   - DNS assignment: Automatic

3. **Check connection**
   - Open Command Prompt
   - Run: `ipconfig`
   - Should show IP like `192.168.4.x`
   - Run: `ping 8.8.8.8`
   - Should get replies

## Step 3: Verify Bridge is Working

### On the Pi:
```bash
# Check if laptop got an IP
cat /var/lib/dhcp/dnsmasq.leases

# Should show the laptop's MAC and assigned IP
```

### On Windows:
```powershell
# Check IP configuration
ipconfig /all

# Should see:
# - IPv4 Address: 192.168.4.x
# - Default Gateway: 192.168.4.1
# - DNS Servers: 8.8.8.8

# Test internet
ping 8.8.8.8
ping google.com
```

## Step 4: Install Kimi on Windows

Now that Windows has internet through the Pi:

1. **Install Python** (if not installed)
   - Download from python.org
   - Check "Add to PATH"

2. **Install Kimi**
   ```powershell
   pip install kimi-cli
   kimi login
   ```

3. **Setup Distributed Cluster**
   ```powershell
   # Create directories
   mkdir %USERPROFILE%\.kimi\distributed\master
   
   # Create nodes.json
   notepad %USERPROFILE%\.kimi\distributed\master\nodes.json
   ```

   Paste this (the Pi is now both the network bridge AND a slave node):
   ```json
   {
     "slaves": [
       {
         "node_id": "pi-bridge-slave",
         "host": "192.168.4.1",
         "ssh_user": "pi",
         "max_tasks": 2
       }
     ]
   }
   ```

## Network Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    NETWORK TOPOLOGY                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Internet                                                       │
│      │                                                           │
│      ▼                                                           │
│   [WiFi Router]                                                  │
│      │                                                           │
│      ├── 192.168.1.x → Your Mac (separate)                       │
│      │                                                           │
│      └── 192.168.1.y → Raspberry Pi (wlan0)                      │
│                          │                                       │
│                    ┌─────┴─────┐                                 │
│                    │  Bridge   │                                 │
│                    │  eth0     │ 192.168.4.1                     │
│                    │  192.168.4.1/24                              │
│                    └─────┬─────┘                                 │
│                          │ Ethernet                              │
│                          ▼                                       │
│                    [USB-C Dock]                                  │
│                          │                                       │
│                          ▼                                       │
│                    Windows Laptop                                │
│                    192.168.4.x                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Test Script for Pi

Create this script on the Pi:

```bash
#!/bin/bash
# /home/pi/setup-bridge.sh

echo "Setting up Pi as Ethernet Bridge..."

# Enable IP forwarding
sudo sysctl -w net.ipv4.ip_forward=1
sudo sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf

# Install dnsmasq
sudo apt update
sudo apt install dnsmasq -y

# Configure dnsmasq
cat << 'EOF' | sudo tee /etc/dnsmasq.conf
interface=eth0
dhcp-range=192.168.4.2,192.168.4.100,255.255.255.0,12h
dhcp-option=3,192.168.4.1
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
listen-address=127.0.0.1,192.168.4.1
bind-interfaces
EOF

# Configure static IP for eth0
cat << 'EOF' | sudo tee -a /etc/dhcpcd.conf

# Bridge configuration
interface eth0
static ip_address=192.168.4.1/24
nohook wpa_supplicant
EOF

# Setup NAT
sudo apt install iptables-persistent -y
sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
sudo iptables -A FORWARD -i wlan0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A FORWARD -i eth0 -o wlan0 -j ACCEPT
sudo netfilter-persistent save

# Restart services
sudo systemctl restart dhcpcd
sudo systemctl enable dnsmasq
sudo systemctl restart dnsmasq

echo "✅ Bridge setup complete!"
echo "Windows laptop should now get IP 192.168.4.x"
```

Run it:
```bash
chmod +x setup-bridge.sh
./setup-bridge.sh
```

## Troubleshooting

### Windows shows "Unidentified Network"
- This is normal for Pi bridge
- Check if IP was assigned: `ipconfig`
- Try: `ping 192.168.4.1` (should reach Pi)

### No internet on Windows
- Check Pi can reach internet: `ping 8.8.8.8` (on Pi)
- Check NAT rules: `sudo iptables -t nat -L`
- Check dnsmasq is running: `sudo systemctl status dnsmasq`

### Can't SSH to Pi from Windows
- Use Pi's Ethernet IP: `ssh pi@192.168.4.1`
- Or use the WiFi IP if known

### DNS not working on Windows
- Manually set DNS to 8.8.8.8 on Windows
- Or restart dnsmasq: `sudo systemctl restart dnsmasq`

## Next Steps

Once Windows has internet:
1. Install Kimi CLI on Windows
2. Setup distributed config
3. The Pi acts as both network bridge AND compute slave
4. Kimi-Claw can offload tasks to the Pi

## One-Line Setup (if you can SSH to Pi)

From your Mac, if Pi is on WiFi:

```bash
ssh pi@PI_WIFI_IP "curl -fsSL https://raw.githubusercontent.com/yourrepo/setup-bridge.sh | bash"
```

Or run the setup-bridge.sh script manually on the Pi.
