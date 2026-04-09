#!/bin/bash
# Wake the Windows PC via Wake-on-LAN
# MAC address: BC:FC:E7:1E:29:D5
# Requires: brew install wakeonlan (or use python)

MAC="BC:FC:E7:1E:29:D5"

# Try wakeonlan command first
if command -v wakeonlan &>/dev/null; then
    wakeonlan "$MAC"
    echo "WoL packet sent to $MAC"
elif command -v python3 &>/dev/null; then
    python3 -c "
import socket, struct
mac = '$MAC'.replace(':','').replace('-','')
magic = b'\\xff' * 6 + bytes.fromhex(mac) * 16
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.sendto(magic, ('255.255.255.255', 9))
sock.close()
print('WoL packet sent')
"
else
    echo "Install wakeonlan: brew install wakeonlan"
fi
