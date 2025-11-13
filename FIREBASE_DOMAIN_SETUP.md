# 🌐 Firebase Custom Domain Setup for sapphiretrade.xyz

## Prerequisites
- Firebase project created and configured
- Domain `sapphiretrade.xyz` registered and accessible
- Firebase CLI installed and authenticated
- Trading dashboard built and ready for deployment

---

## Step 1: Verify Domain Ownership

### Add Domain to Firebase Hosting
```bash
# Connect your custom domain
firebase hosting:sites:create sapphire-trading-dashboard

# Or if using default site
firebase target:apply hosting sapphire-trading-dashboard sapphire-trading-dashboard
```

### Update Firebase Configuration
```bash
# Update .firebaserc if needed
{
  "projects": {
    "default": "sapphire-trading-dashboard"
  },
  "targets": {
    "sapphire-trading-dashboard": {
      "hosting": {
        "sapphire-trading-dashboard": [
          "sapphire-trading-dashboard"
        ]
      }
    }
  }
}
```

---

## Step 2: DNS Configuration

### Access Your DNS Settings
1. Go to your domain registrar (where sapphiretrade.xyz is registered)
2. Find DNS settings or DNS management
3. Add the following records:

### Required DNS Records

#### CNAME Record (for www subdomain)
```
Host/Name: www
Type: CNAME
Value: sapphire-trading-dashboard.web.app
TTL: 3600 (1 hour)
```

#### A Records (for root domain)
```
Host/Name: @
Type: A
Value: 199.36.158.100
TTL: 3600 (1 hour)

Host/Name: @
Type: AAAA
Value: 2620:0:890::100
TTL: 3600 (1 hour)
```

---

## Step 3: Verify DNS Propagation

### Check DNS Propagation
```bash
# Check A record
nslookup sapphiretrade.xyz

# Check CNAME record
nslookup www.sapphiretrade.xyz

# Or use online tools:
# - https://dnschecker.org/
# - https://www.whatsmydns.net/
```

### Expected Results
```
sapphiretrade.xyz:
  A record: 199.36.158.100
  AAAA record: 2620:0:890::100

www.sapphiretrade.xyz:
  CNAME: sapphire-trading-dashboard.web.app
```

---

## Step 4: Firebase SSL Certificate

### Automatic SSL Setup
Firebase Hosting automatically provisions SSL certificates for custom domains.

### Verify SSL Certificate
```bash
# Check SSL certificate
curl -I https://sapphiretrade.xyz

# Should return HTTP/2 200 with proper SSL headers
```

---

## Step 5: Deploy to Custom Domain

### Update Firebase Configuration
```json
// firebase.json
{
  "hosting": {
    "site": "sapphire-trading-dashboard",
    "public": "dist",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ],
    "headers": [
      {
        "source": "**/*.@(js|css)",
        "headers": [
          {
            "key": "Cache-Control",
            "value": "max-age=31536000"
          }
        ]
      },
      {
        "source": "**/*.@(png|jpg|jpeg|gif|svg|ico)",
        "headers": [
          {
            "key": "Cache-Control",
            "value": "max-age=31536000"
          }
        ]
      }
    ]
  }
}
```

### Deploy to Custom Domain
```bash
# Build the application
cd trading-dashboard
npm run build

# Deploy to custom domain
firebase deploy --only hosting:sapphire-trading-dashboard

# Or if using default site
firebase deploy --only hosting
```

---

## Step 6: Update Application Configuration

### Update API Base URL
```typescript
// src/contexts/TradingContext.tsx
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://cloud-trader-342943608894.us-central1.run.app';
```

### Update Environment Variables
```bash
# .env.local
VITE_API_BASE_URL=https://cloud-trader-342943608894.us-central1.run.app
VITE_FIREBASE_API_KEY=your_api_key_here
VITE_FIREBASE_AUTH_DOMAIN=sapphire-trading-dashboard.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=sapphire-trading-dashboard
# ... other Firebase config
```

---

## Step 7: Testing & Validation

### Test Custom Domain
```bash
# Test HTTPS access
curl -I https://sapphiretrade.xyz
curl -I https://www.sapphiretrade.xyz

# Test application loading
open https://sapphiretrade.xyz
open https://www.sapphiretrade.xyz
```

### Verify Functionality
1. ✅ Login page loads
2. ✅ Authentication works
3. ✅ Dashboard displays data
4. ✅ Real-time updates work
5. ✅ Mobile responsiveness
6. ✅ All navigation works

---

## Step 8: Domain Redirects (Optional)

### Set Up Redirects
If you want to redirect non-www to www or vice versa:

#### Firebase Redirects Configuration
```json
// firebase.json
{
  "hosting": {
    "site": "sapphire-trading-dashboard",
    "public": "dist",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ],
    "redirects": [
      {
        "source": "/home",
        "destination": "/",
        "type": 301
      }
    ]
  }
}
```

---

## Troubleshooting

### DNS Issues
```bash
# Clear DNS cache
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder

# Or on Windows:
ipconfig /flushdns

# Check Firebase hosting status
firebase hosting:sites:list
```

### SSL Certificate Issues
- SSL certificates can take up to 24 hours to provision
- Firebase automatically manages certificate renewal
- Check Firebase Console → Hosting for certificate status

### Deployment Issues
```bash
# Check deployment status
firebase hosting:channel:list

# Redeploy if needed
firebase deploy --only hosting:sapphire-trading-dashboard
```

---

## Performance Optimization

### CDN Configuration
Firebase Hosting automatically serves content from Google's global CDN.

### Caching Headers
Already configured in `firebase.json` for optimal performance.

### Monitoring
```bash
# Check hosting analytics
firebase hosting:site:get sapphire-trading-dashboard

# Monitor performance
# Firebase Console → Hosting → Analytics
```

---

## Final URLs

After successful setup:
- **Primary Domain**: https://sapphiretrade.xyz
- **WWW Domain**: https://www.sapphiretrade.xyz
- **Firebase URL**: https://sapphire-trading-dashboard.web.app

---

## Cost Considerations

**Firebase Hosting (Custom Domain):**
- Free tier: 10GB storage, 360MB/day transfer
- Additional usage: $0.026/GB storage, $0.15/GB transfer
- Custom domain: Free (included)

**Total Estimated Cost**: <$5/month for production usage

---

## Success Checklist

- [ ] DNS records configured correctly
- [ ] SSL certificate provisioned
- [ ] Application deployed successfully
- [ ] Authentication working
- [ ] Real-time data loading
- [ ] Mobile responsive
- [ ] All routes functioning
- [ ] Performance optimized
- [ ] Error handling working

**🎉 Your Sapphire Trading Dashboard is now live at https://sapphiretrade.xyz!**
