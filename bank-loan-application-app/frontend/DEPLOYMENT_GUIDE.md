# 🚀 Frontend Setup & Deployment Guide

## Quick Start (5 minutes)

### Prerequisites
- Node.js 18+ (Check: `node --version`)
- npm or yarn (Check: `npm --version`)
- Backend services configured and running

### Step 1: Install Dependencies
```bash
cd platform/frontend
npm install
```

### Step 2: Configure Environment
```bash
cp .env.example .env.local
# Edit .env.local with your backend API URL
nano .env.local
```

### Step 3: Start Development Server
```bash
npm run dev
```

Visit `http://localhost:3000` 🎉

---

## 📂 Project Structure Explained

```
frontend/
├── src/
│   ├── app/                      # Next.js app directory
│   │   ├── dashboard/
│   │   │   └── page.tsx          # Main application entry point
│   │   ├── layout.tsx            # Root layout with providers
│   │   ├── globals.css           # Global styles
│   │   └── page.tsx              # Home page (redirects to dashboard)
│   │
│   ├── components/
│   │   ├── layout.tsx            # App layout (sidebar, header, nav)
│   │   ├── ui.tsx                # Design system (90+ components)
│   │   │
│   │   └── modules/              # Feature modules
│   │       ├── dashboard.tsx      # Loan journey overview
│   │       ├── onboarding.tsx     # 6-step onboarding wizard
│   │       ├── kyc.tsx           # PAN, Aadhaar, face verification
│   │       ├── bank-statement.tsx# Upload & analysis
│   │       ├── mandate.tsx       # Auto-debit setup
│   │       ├── disbursement.tsx  # Fund transfer
│   │       └── repayment-support.tsx # EMI & support
│   │
│   └── lib/
│       ├── api-client.ts         # Type-safe API client
│       ├── application-state.tsx # React Context state
│       ├── design-tokens.ts      # Design system
│       └── storage.ts            # Local storage helpers
│
├── public/                        # Static assets
├── package.json                  # Dependencies
├── tsconfig.json                # TypeScript config
├── next.config.ts               # Next.js config
└── .env.example                 # Environment template
```

---

## 🎯 Application Flow

```
Dashboard (Overview)
    ↓
Onboarding (Profile Setup) → Personal → Employment → Income → Address → Documents → Review
    ↓
KYC Verification → PAN Check → Aadhaar Verify → Face Match
    ↓
Bank Statement → Upload → Analyze → Review
    ↓
Auto-Debit Setup → Bank Select → Amount → Confirm → Authorize
    ↓
Loan Disbursement → Amount → Account → Review → Transfer
    ↓
Repayment Dashboard (Track EMIs)
    ↓
Customer Support (Tickets)
```

---

## 🔧 Development Workflow

### Running the Application

**Development Mode**
```bash
npm run dev
# Hot reload enabled - changes reflect instantly
# Runs on http://localhost:3000
```

**Production Build**
```bash
npm run build    # Compile and optimize
npm run start    # Start production server
```

**Linting**
```bash
npm run lint     # Check code quality
```

### Making Changes

1. **Add a new component**
   ```typescript
   // src/components/MyComponent.tsx
   'use client'
   import React from 'react'
   import { motion } from 'framer-motion'
   
   export const MyComponent = () => {
     return <motion.div>Hello</motion.div>
   }
   ```

2. **Use the component**
   ```typescript
   import { MyComponent } from '@/components/MyComponent'
   
   export default function Page() {
     return <MyComponent />
   }
   ```

3. **Add styling**
   ```typescript
   import clsx from 'clsx'
   import { colors, spacing } from '@/lib/design-tokens'
   
   className={clsx(
     'p-4 rounded-lg',
     'bg-gradient-to-r from-sky-50 to-blue-50'
   )}
   ```

---

## 🌍 Environment Configuration

### Development
```bash
# .env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:3001
NEXT_PUBLIC_ENABLE_DEBUG_MODE=true
```

### Staging
```bash
NEXT_PUBLIC_API_BASE_URL=https://staging-api.loanapp.com
NEXT_PUBLIC_ENABLE_DEBUG_MODE=false
```

### Production
```bash
NEXT_PUBLIC_API_BASE_URL=https://api.loanapp.com
NEXT_PUBLIC_ENABLE_DEBUG_MODE=false
```

---

## 🚀 Deployment Options

### Option 1: Vercel (Recommended)
Fastest deployment with best Next.js support

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel

# Follow interactive prompts
# Production: vercel --prod
```

**Benefits:**
- Automatic preview deployments for PRs
- Built-in analytics
- Edge functions support
- Automatic scaling

### Option 2: Docker
For containerized deployments

**Create Dockerfile**
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package*.json ./
RUN npm ci --only=production
EXPOSE 3000
CMD ["npm", "start"]
```

**Build and run**
```bash
# Build
docker build -t loanapp-frontend:latest .

# Run locally
docker run -p 3000:3000 \
  -e NEXT_PUBLIC_API_BASE_URL=http://backend:3001 \
  loanapp-frontend:latest

# Push to registry
docker tag loanapp-frontend:latest your-registry/loanapp-frontend:latest
docker push your-registry/loanapp-frontend:latest
```

### Option 3: Self-Hosted (AWS, GCP, Azure)
For complete control

**Linux Server Setup**
```bash
# SSH to server
ssh user@your-server.com

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Clone repository
git clone <your-repo-url>
cd platform/frontend

# Install dependencies
npm install

# Build
npm run build

# Use PM2 for process management
npm install -g pm2
pm2 start "npm run start" --name "loanapp-frontend"
pm2 startup
pm2 save
```

**With Nginx Reverse Proxy**
```nginx
upstream loanapp {
    server localhost:3000;
}

server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://loanapp;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

---

## 🔌 Backend Integration

### API Client Setup

The `apiClient` is pre-configured to connect to all microservices:

```typescript
import { apiClient } from '@/lib/api-client'

// All methods are type-safe
await apiClient.validateCustomerProfile(customerId, pan, mobile, email)
await apiClient.verifyPan(customerId, pan)
await apiClient.uploadStatement(file, customerId)
```

### Connecting to Local Backend

**Ensure backend services are running**
```bash
# In a separate terminal, start your backend
cd ../backend
python main.py  # or your backend command
```

**Verify API connectivity**
```bash
# Test API endpoint
curl http://localhost:3001/api/CustomerOnboardingService

# Check logs in browser DevTools console
```

---

## 🎨 Customization Guide

### Changing Colors

**Edit `lib/design-tokens.ts`**
```typescript
export const colors = {
  primary: {
    500: '#0ea5e9',  // Change this
    600: '#0284c7',
    // ...
  }
}
```

### Changing Typography

```typescript
export const typography = {
  fontSize: {
    base: '1rem',      // Adjust base size
    lg: '1.125rem',
    // ...
  }
}
```

### Changing Animations

```typescript
export const motion = {
  duration: {
    fast: '150ms',     // Speed up/slow down
    base: '250ms',
  },
  easing: {
    easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
    // Add more easing functions
  }
}
```

---

## 🐛 Debugging

### Browser DevTools
- **Console**: Check for JavaScript errors
- **Network**: Monitor API calls
- **React DevTools**: Inspect component state

### Check API Responses
```bash
# Test onboarding API
curl -X POST http://localhost:3001/api/CustomerOnboardingService \
  -H "Content-Type: application/json" \
  -d '{"requestId":"validateCustomerProfile","customerId":"test"}'
```

### Enable Debug Mode
```bash
# .env.local
NEXT_PUBLIC_ENABLE_DEBUG_MODE=true
```

---

## 📊 Performance Optimization

### Build Analysis
```bash
npm run build
# Check build size in .next/static

# Use bundle analyzer
npm install --save-dev @next/bundle-analyzer
```

### Lighthouse Testing
```bash
# Use Google Lighthouse in Chrome DevTools
# Target: Performance > 90, Accessibility > 90, Best Practices > 90
```

---

## 🔒 Security Checklist

- [ ] Environment variables configured
- [ ] API URLs use HTTPS in production
- [ ] No sensitive data in component code
- [ ] CORS properly configured on backend
- [ ] CSP headers enabled
- [ ] Input validation on all forms
- [ ] Rate limiting configured

---

## 📞 Troubleshooting

### Issue: API Connection Failed
```
❌ Error: Failed to fetch from API

Solution:
1. Check NEXT_PUBLIC_API_BASE_URL in .env.local
2. Verify backend services are running
3. Check browser console for CORS errors
4. Ensure backend accepts requests from frontend origin
```

### Issue: Build Failed
```
❌ Error: TypeScript compilation error

Solution:
npm install  # Reinstall dependencies
npm run build  # Try building again
rm -rf .next  # Clear build cache if needed
```

### Issue: Slow Performance
```
❌ Symptoms: Page loads slowly

Solution:
1. Check Network tab in DevTools for slow requests
2. Enable code splitting: npm run build
3. Optimize images: use Next.js Image component
4. Check Framer Motion performance
```

---

## 📚 Resources

- [Next.js Documentation](https://nextjs.org/docs)
- [React Documentation](https://react.dev)
- [Framer Motion Guide](https://www.framer.com/motion/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Tailwind CSS](https://tailwindcss.com/docs)

---

## 🤝 Contributing

1. Create a new branch: `git checkout -b feature/your-feature`
2. Make changes and test thoroughly
3. Commit with clear messages: `git commit -m "feat: add feature"`
4. Push to branch: `git push origin feature/your-feature`
5. Submit pull request

---

## 📄 Deployment Checklist

- [ ] All tests passing
- [ ] Environment variables configured
- [ ] Build completes without errors
- [ ] Production build optimized
- [ ] API URLs configured correctly
- [ ] Database migrations run
- [ ] Security headers configured
- [ ] CDN/caching configured
- [ ] Monitoring/logging enabled
- [ ] Backup and disaster recovery plan
- [ ] Performance baseline established

---

**Questions?** Check the main README.md or contact the development team.
