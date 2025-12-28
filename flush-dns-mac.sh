#!/bin/bash
# Flush DNS cache on macOS

echo "Flushing DNS cache on macOS..."
echo ""

# Flush DNS cache (works on macOS 10.10+)
sudo dscacheutil -flushcache

# Restart mDNSResponder (DNS resolver daemon)
sudo killall -HUP mDNSResponder

echo ""
echo "✅ DNS cache flushed!"
echo ""
echo "Now test:"
echo "  ping matthewcarter.info"
echo "  ping clerk.matthewcarter.info"
echo ""
echo "If still not working, change your DNS servers to:"
echo "  Primary: 1.1.1.1 (Cloudflare)"
echo "  Secondary: 8.8.8.8 (Google)"

