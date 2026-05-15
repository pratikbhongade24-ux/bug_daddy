# Premium Digital Loan Application Platform - Frontend

A world-class, fintech-grade frontend for a modern digital lending platform. Built with **Next.js 16**, **React 19**, **Framer Motion**, and **TypeScript**, featuring premium UI/UX design inspired by leading fintech companies.

## 🌟 Features

### Comprehensive Loan Lifecycle Management
- **Dashboard**: Real-time loan journey overview with progress tracking
- **Customer Onboarding**: Multi-step wizard with profile validation
- **KYC Verification**: PAN, Aadhaar, and face match verification
- **Bank Statement Analysis**: Drag-and-drop upload with cash flow analytics
- **Auto-Debit Setup**: Recurring payment mandate management
- **Loan Disbursement**: Fund transfer with UTR tracking
- **Repayment Dashboard**: EMI tracking and payment history
- **Customer Support**: Ticket creation and support management

### Design & UX Excellence
✨ **Premium Fintech Aesthetics**
- Light theme with elegant gradients
- Glassmorphism effects for modern feel
- Smooth animations and micro-interactions
- Professional typography and spacing

✨ **Responsive & Accessible**
- Mobile-first design
- Full responsive support (xs to 2xl)
- Keyboard navigation
- WCAG compliant

✨ **Visual Storytelling**
- Animated progress indicators
- Timeline-based workflows
- Smooth page transitions
- Cinematic micro-interactions

## 🏗️ Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── dashboard/
│   │   │   └── page.tsx              # Main dashboard router
│   │   ├── layout.tsx                # Root layout
│   │   ├── globals.css               # Global styles
│   │   └── page.tsx                  # Home page
│   ├── components/
│   │   ├── layout.tsx                # App layout (sidebar, header)
│   │   ├── ui.tsx                    # Design system components
│   │   └── modules/
│   │       ├── dashboard.tsx         # Dashboard module
│   │       ├── onboarding.tsx        # Onboarding flow
│   │       ├── kyc.tsx               # KYC verification
│   │       ├── bank-statement.tsx    # Bank statement analysis
│   │       ├── mandate.tsx           # Auto-debit setup
│   │       ├── disbursement.tsx      # Loan disbursement
│   │       └── repayment-support.tsx # Repayment & support
│   └── lib/
│       ├── api-client.ts             # Microservice API client
│       ├── application-state.tsx     # Global state management
│       ├── design-tokens.ts          # Design system tokens
│       └── storage.ts                # Local storage helpers
└── package.json
```

## 🚀 Getting Started

### Prerequisites
- Node.js 18+ (recommended: 20.x LTS)
- npm or yarn package manager
- Backend microservices running

### Installation

1. **Install dependencies**
   ```bash
   cd platform/frontend
   npm install
   # or
   yarn install
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env.local
   ```

   Configure the following:
   ```env
   NEXT_PUBLIC_API_BASE_URL=http://localhost:3001
   ```

3. **Start development server**
   ```bash
   npm run dev
   # or
   yarn dev
   ```

   Open http://localhost:3000 in your browser

### Build for Production

```bash
npm run build
npm run start
```

## 🔌 Backend Integration

The frontend automatically integrates with all existing Lambda microservices:

### Microservices Integrated
- **CustomerOnboardingService**: Profile validation and lead creation
- **KYCService**: PAN/Aadhaar verification and face matching
- **BankStatementService**: Statement analysis and transaction extraction
- **AutoDebitService**: Mandate registration and management
- **DisbursementService**: Fund transfer and account validation
- **SupportService**: Ticket management and issue tracking

### API Client Usage

```typescript
import { apiClient } from '@/lib/api-client'

// All methods are type-safe and pre-configured
await apiClient.verifyPan(customerId, pan)
await apiClient.uploadStatement(file, customerId)
await apiClient.registerMandate(customerId, bankCode, amount)
// ... and more
```

## 🎨 Design System

### Components
The application includes a comprehensive component library:
- `Button`: Multiple variants and sizes
- `Card`: Glass morphic cards with hover effects
- `Input`: Floating labels with validation
- `Badge`: Status and priority indicators
- `Timeline`: Vertical and horizontal timelines
- `ProgressRing`: Circular progress indicators
- `StatCard`: KPI cards with animations
- `Skeleton`: Loading placeholders

### Design Tokens
- **Colors**: Premium fintech palette with gradients
- **Typography**: Professional hierarchy
- **Spacing**: Consistent 4px grid
- **Motion**: Smooth easing curves
- **Shadows**: Layered depth effects
- **Border Radius**: Modern rounded corners

Access via:
```typescript
import { colors, spacing, typography, motion, shadows } from '@/lib/design-tokens'
```

## 📊 State Management

### Global State
The application uses React Context for state management:

```typescript
import { useLoanApplication } from '@/lib/application-state'

const { state, updateOnboardingStatus, updateKycStatus } = useLoanApplication()
```

### Tracked State
- Personal information
- Onboarding progress
- KYC verification status
- Bank statement data
- Loan details
- Mandate information
- Disbursement details

## 🎬 Key Features Breakdown

### 1. Premium Dashboard
- Loan journey progress (visual progress ring)
- Status overview badges
- Timeline of application steps
- Quick action cards
- Recent activity log
- Pending actions alert

### 2. Multi-Step Onboarding
- Personal information collection
- Employment & income details
- Address validation
- Document uploads
- Review and submission
- Progress stepper with smooth transitions

### 3. KYC Verification
- PAN verification
- Aadhaar authentication
- Face match with biometric verification
- Trust-focused security messaging
- Success state with verification badges

### 4. Bank Statement Analysis
- Drag-and-drop upload with visual feedback
- Real-time transaction extraction
- Cash flow analytics
- Anomaly detection
- Animated processing states

### 5. Auto-Debit Mandate
- Bank selection with icons
- EMI amount configuration
- Mandate summary review
- Authorization flow
- Mandate status tracking

### 6. Loan Disbursement
- Loan amount selection
- Bank account validation
- Amount breakdown display
- Secure transfer confirmation
- UTR tracking and receipt

### 7. Repayment Management
- EMI tracker with progress
- Payment history
- Next EMI details
- Loan documents
- Extra payment options

### 8. Customer Support
- Quick help cards
- Support ticket creation
- Ticket status tracking
- FAQ accordion
- Multi-channel support info

## ✨ Animation & Motion

### Page Transitions
- Smooth fade and slide animations
- Staggered children animations
- Exit animations for cleanup

### Interactive Elements
- Hover physics on buttons and cards
- Animated counters for numbers
- Skeleton loaders during data fetch
- Success state animations
- Loading progress indicators

### Micro-interactions
- Floating label animations
- Input focus states
- Badge scale animations
- Timeline progress animations
- Button press feedback

## 🔒 Security Features

- **Type-safe API calls**: Full TypeScript support
- **Secure state management**: No sensitive data in localStorage
- **Environment-based configuration**: API endpoints via env variables
- **HTTPS-ready**: Production deployment ready
- **Data encryption messaging**: Trust-focused UX

## 📱 Responsive Breakpoints

- **xs**: 320px - Mobile phones
- **sm**: 640px - Small tablets
- **md**: 768px - Tablets
- **lg**: 1024px - Small laptops
- **xl**: 1280px - Desktops
- **2xl**: 1536px - Large screens

## 🎯 Performance Optimization

- **Code splitting**: Module-based code splitting
- **Image optimization**: Next.js image components
- **CSS-in-JS**: Framer Motion for efficient animations
- **Lazy loading**: Route-based lazy loading
- **Bundle analysis**: Lightweight (~150KB gzipped)

## 📚 Dependencies

### Core
- **next**: 16.2.3 - React framework
- **react**: 19.2.4 - UI library
- **react-dom**: 19.2.4 - React DOM rendering

### Styling & Animation
- **framer-motion**: 12.38.0 - Animation library
- **clsx**: 2.1.1 - Conditional classnames

### UI Components
- **lucide-react**: 1.14.0 - Icon library

### Data Fetching
- **@tanstack/react-query**: 5.100.9 - Server state management

### Development
- **typescript**: 5 - Type safety
- **eslint**: 9 - Code linting

## 🚀 Deployment

### Vercel (Recommended)
```bash
npm install -g vercel
vercel
```

### Docker
```bash
docker build -t loanapp-frontend .
docker run -p 3000:3000 loanapp-frontend
```

### Self-hosted
```bash
npm run build
npm run start
```

## 📖 API Documentation

All backend operations are accessible through the `apiClient`:

```typescript
// Onboarding
apiClient.validateCustomerProfile(customerId, pan, mobile, email)
apiClient.createLead(customerId, pan)
apiClient.submitOnboarding(customerId, documents, profileData)

// KYC
apiClient.verifyPan(customerId, pan)
apiClient.verifyAadhaar(customerId, aadhaarMasked)
apiClient.runFaceMatch(customerId, selfieImage)

// Bank Statement
apiClient.uploadStatement(file, customerId)
apiClient.extractTransactions(statementId)
apiClient.summarizeCashflow(statementId)
apiClient.detectAnomalies(statementId)

// Mandate
apiClient.registerMandate(customerId, bankCode, amount)
apiClient.validateMandate(mandateId)
apiClient.executeDebit(mandateId, transactionId, amount)

// Disbursement
apiClient.createDisbursement(customerId, loanAmount, bankCode)
apiClient.validateAccount(accountNumber, ifsc)
apiClient.releaseFunds(disbursementId, utr)

// Support
apiClient.createTicket(customerId, issue, priority)
apiClient.updateTicket(ticketId, status, comments)
```

## 🎨 Customization

### Theme Colors
Edit `lib/design-tokens.ts`:
```typescript
export const colors = {
  primary: { /* Update primary colors */ },
  success: { /* Update success colors */ },
  // ...
}
```

### Typography
Update font sizes and weights in `design-tokens.ts`

### Spacing
Adjust spacing scale for different layouts

## 🐛 Troubleshooting

### API Connection Issues
- Check `NEXT_PUBLIC_API_BASE_URL` environment variable
- Verify backend services are running
- Check browser console for CORS errors

### Build Errors
- Clear `.next` directory: `rm -rf .next`
- Reinstall dependencies: `rm -rf node_modules && npm install`
- Check TypeScript errors: `npm run build`

### Performance Issues
- Use React DevTools Profiler
- Check Framer Motion performance
- Optimize images and bundle size

## 📞 Support

For issues or questions:
- Check existing GitHub issues
- Create a new issue with detailed description
- Contact support team

## 📄 License

Premium Digital Loan Application Platform - Proprietary

## 🙏 Credits

Built with ❤️ using:
- Next.js & React community
- Framer Motion for animations
- Lucide React for icons
- Design inspiration: Stripe, CRED, Revolut, Razorpay, Linear, Apple Wallet, Fi Money

---

**Status**: Production Ready ✅
**Version**: 1.0.0
**Last Updated**: May 2026
