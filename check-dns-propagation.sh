#!/bin/bash
# Check DNS propagation status for clerk.matthewcarter.info

echo "=== DNS Propagation Check for clerk.matthewcarter.info ==="
echo ""

# Test different DNS servers
declare -A dns_servers=(
    ["Cloudflare"]="1.1.1.1"
    ["Google"]="8.8.8.8"
    ["Quad9"]="9.9.9.9"
    ["OpenDNS"]="208.67.222.222"
    ["Cloudflare-Auth"]="aiden.ns.cloudflare.com"
)

working=0
total=0

for name in "${!dns_servers[@]}"; do
    server="${dns_servers[$name]}"
    total=$((total + 1))
    
    result=$(dig @"$server" clerk.matthewcarter.info CNAME +short 2>/dev/null | head -1)
    
    if [[ "$result" == *"frontend-api.clerk.services"* ]]; then
        echo "✅ $name ($server): $result"
        working=$((working + 1))
    else
        echo "❌ $name ($server): No result or NXDOMAIN"
    fi
done

echo ""
echo "Propagation: $working/$total DNS servers"
echo ""

if [ $working -eq $total ]; then
    echo "🎉 DNS fully propagated! Your site should work now."
    echo "If still not working, clear browser cache or try incognito mode."
else
    echo "⏳ DNS still propagating. This can take 1-4 hours for negative cache to clear."
    echo ""
    echo "Recommended: Change Clerk domain to temporary domain to make site work immediately."
    echo "See: Clerk Dashboard → Domains → Danger Zone → Change domain"
fi

