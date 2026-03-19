# Windows Static IP Configuration (If DHCP Fails)

## Problem
Windows laptop not getting IP from Pi's DHCP server.

## Solution: Manual Static IP Configuration

### Option 1: Automatic DHCP (Try First After Restart)

1. Restart Windows laptop
2. Unplug and replug Ethernet cable
3. Wait 30 seconds
4. Check if IP was assigned:
   ```cmd
   ipconfig
   ```
   Look for `192.168.4.x` address

### Option 2: Manual Static IP (If DHCP Still Fails)

If Windows still shows `169.254.x.x` (APIPA) or no IP:

**Step 1: Open Network Settings**
1. Settings → Network & Internet → Ethernet
2. Click "Change adapter options"
3. Right-click Ethernet adapter → Properties

**Step 2: Configure IPv4**
1. Select "Internet Protocol Version 4 (TCP/IPv4)"
2. Click Properties
3. Select "Use the following IP address"
4. Enter:
   ```
   IP address:      192.168.4.10
   Subnet mask:     255.255.255.0
   Default gateway: 192.168.4.1
   ```
5. Enter DNS:
   ```
   Preferred: 8.8.8.8
   Alternate: 8.8.4.4
   ```
6. Click OK

**Step 3: Verify**
```cmd
ipconfig
ping 192.168.4.1
ping 8.8.8.8
```

### Option 3: PowerShell Commands

Run as Administrator in PowerShell:

```powershell
# Get Ethernet interface name
Get-NetAdapter | Where-Object {$_.Status -eq "Up"}

# Set static IP (replace "Ethernet" with your interface name if different)
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.4.10 -PrefixLength 24 -DefaultGateway 192.168.4.1

# Set DNS
Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ServerAddresses 8.8.8.8,8.8.4.4

# Verify
ipconfig
ping 192.168.4.1
ping 8.8.8.8
```

### Option 4: Check Pi DHCP Server

If Windows still doesn't work, check on the Pi:

```bash
# Check if dnsmasq is running
sudo systemctl status dnsmasq

# If not running, start it
sudo systemctl restart dnsmasq

# Check DHCP leases
cat /var/lib/misc/dnsmasq.leases

# Check if Ethernet interface is up
ip addr show eth0

# View dnsmasq logs
sudo tail -50 /var/log/daemon.log | grep dnsmasq
```

### Common Issues

#### Issue: Windows shows "Identifying..." forever
**Fix:** This is normal for new networks. Wait 2-3 minutes or restart the Ethernet adapter:
```powershell
# PowerShell as Admin
Disable-NetAdapter -Name "Ethernet" -Confirm:$false
Start-Sleep 2
Enable-NetAdapter -Name "Ethernet"
```

#### Issue: Windows has 169.254.x.x IP
**Fix:** This is APIPA (auto-config when DHCP fails). Means Windows can't reach DHCP server.
- Check Ethernet cable connection
- Restart dnsmasq on Pi: `sudo systemctl restart dnsmasq`
- Use static IP (Option 2 above)

#### Issue: Can ping Pi but no internet
**Fix:** NAT not working on Pi
```bash
# On Pi, check NAT rules
sudo iptables -t nat -L -v -n

# If empty, re-add them
sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
sudo iptables -A FORWARD -i wlan0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A FORWARD -i eth0 -o wlan0 -j ACCEPT
sudo netfilter-persistent save
```

### Quick Diagnostic Commands

**On Windows:**
```cmd
# Check IP
ipconfig /all

# Check if Pi is reachable
ping 192.168.4.1

# Check route
traceroute 8.8.8.8

# Reset network adapter
netsh winsock reset
netsh int ip reset
ipconfig /release
ipconfig /renew
```

**On Pi:**
```bash
# Check services
sudo systemctl status dnsmasq
sudo systemctl status dhcpcd

# Check interfaces
ip addr show
ip route show

# Check DHCP leases
cat /var/lib/misc/dnsmasq.leases

# Restart everything
sudo systemctl restart dnsmasq dhcpcd
```

### Fallback: USB Tethering from Pi

If Ethernet bridge refuses to work, try USB tethering:

**On Pi:**
```bash
# Install USB gadget mode (if using Pi Zero or 4)
# This makes Pi appear as USB Ethernet device to Windows
```

**On Windows:**
- Pi will show up as USB Ethernet adapter
- Should auto-configure with DHCP

But let's stick with the Ethernet bridge approach first.

### Nuclear Option: Reset Everything

**On Pi:**
```bash
# Stop services
sudo systemctl stop dnsmasq dhcpcd

# Flush iptables
sudo iptables -F
sudo iptables -t nat -F
sudo iptables -X

# Restart from scratch
sudo systemctl start dhcpcd
sleep 2
sudo systemctl start dnsmasq
```

**On Windows:**
```powershell
# Reset network stack
netsh int ip reset
netsh winsock reset
# Restart Windows
```

After restart, try DHCP again or use static IP.

## Success Criteria

You've succeeded when you can:
1. `ipconfig` shows `192.168.4.x` IP
2. `ping 192.168.4.1` works (reaches Pi)
3. `ping 8.8.8.8` works (internet)
4. `ping google.com` works (DNS working)

Then you're ready to install Kimi on Windows!
