# 🛠️ Developer Quick Reference Guide

## Table of Contents
1. [Component Usage](#component-usage)
2. [API Integration](#api-integration)
3. [State Management](#state-management)
4. [Design System](#design-system)
5. [Common Patterns](#common-patterns)
6. [Debugging Tips](#debugging-tips)

---

## Component Usage

### Basic Components from UI Library

#### Button
```typescript
import { Button } from '@/components/ui'

// Default variant
<Button onClick={() => {}}>Click me</Button>

// With variant
<Button variant="outline">Secondary</Button>
<Button variant="ghost">Subtle</Button>
<Button variant="danger">Delete</Button>

// With size
<Button size="sm">Small</Button>
<Button size="lg">Large</Button>

// With loading state
<Button isLoading={true}>Processing...</Button>

// With icon
<Button icon={<CheckIcon />}>Save</Button>
```

#### Card
```typescript
import { Card } from '@/components/ui'

<Card>
  <Card.Header>
    <Card.Title>Loan Details</Card.Title>
  </Card.Header>
  <Card.Content>
    Your loan information here
  </Card.Content>
</Card>

// Glass morphism effect
<Card isGlass={true}>
  Premium design!
</Card>
```

#### Input
```typescript
import { Input } from '@/components/ui'

<Input
  label="Email"
  type="email"
  value={email}
  onChange={(e) => setEmail(e.target.value)}
  error={emailError}
/>
```

#### Badge
```typescript
import { Badge } from '@/components/ui'

<Badge variant="success">Approved</Badge>
<Badge variant="warning">Pending</Badge>
<Badge variant="error">Rejected</Badge>
```

#### Timeline
```typescript
import { Timeline } from '@/components/ui'

<Timeline
  direction="vertical"
  items={[
    { label: 'Onboarding', status: 'completed' },
    { label: 'KYC', status: 'active' },
    { label: 'Disbursement', status: 'pending' },
  ]}
/>
```

#### ProgressRing
```typescript
import { ProgressRing } from '@/components/ui'

<ProgressRing
  completed={3}
  total={5}
  percentage={60}
/>
```

---

## API Integration

### Using the API Client

```typescript
import { apiClient } from '@/lib/api-client'

// Onboarding
const response = await apiClient.validateCustomerProfile(
  customerId,
  pan,
  mobile,
  email
)

// KYC
const panResult = await apiClient.verifyPan(customerId, pan)
const aadhaarResult = await apiClient.verifyAadhaar(customerId, aadhaarMasked)

// Bank Statement
const uploadResult = await apiClient.uploadStatement(file, customerId)

// With error handling
try {
  const result = await apiClient.createDisbursement(
    customerId,
    amount,
    bankCode
  )
  console.log('Success:', result)
} catch (error) {
  console.error('Error:', error.message)
}
```

### API Client Methods

**Customer Onboarding**
```typescript
apiClient.validateCustomerProfile(customerId, pan, mobile, email)
apiClient.createLead(customerId, pan)
apiClient.submitOnboarding(customerId, documents, profileData)
apiClient.getApplicationStatus(customerId)
```

**KYC Service**
```typescript
apiClient.verifyPan(customerId, pan)
apiClient.verifyAadhaar(customerId, aadhaarMasked)
apiClient.runFaceMatch(customerId, selfieImage)
apiClient.getKycStatus(customerId)
```

**Bank Statement**
```typescript
apiClient.uploadStatement(file, customerId)
apiClient.extractTransactions(statementId)
apiClient.summarizeCashflow(statementId)
apiClient.detectAnomalies(statementId)
```

**Auto-Debit**
```typescript
apiClient.registerMandate(customerId, bankCode, amount)
apiClient.validateMandate(mandateId)
apiClient.executeDebit(mandateId, transactionId, amount)
apiClient.getMandateStatus(mandateId)
```

**Disbursement**
```typescript
apiClient.createDisbursement(customerId, loanAmount, bankCode)
apiClient.validateAccount(accountNumber, ifsc)
apiClient.releaseFunds(disbursementId, utr)
apiClient.getDisbursementStatus(disbursementId)
```

**Support**
```typescript
apiClient.createTicket(customerId, issue, priority)
apiClient.updateTicket(ticketId, status, comments)
apiClient.getTicketStatus(ticketId)
```

---

## State Management

### Using Global State

```typescript
import { useLoanApplication } from '@/lib/application-state'

function MyComponent() {
  const { 
    state,
    updatePersonalInfo,
    updateOnboardingStatus,
    updateKycStatus,
    updateLoanDetails,
    reset
  } = useLoanApplication()

  // Access state
  console.log(state.customer.name)
  console.log(state.onboarding.status)

  // Update state
  const handleSaveName = (name: string) => {
    updatePersonalInfo({
      name,
      email: state.customer.email,
      mobile: state.customer.mobile
    })
  }

  // Update onboarding
  const handleCompleteOnboarding = () => {
    updateOnboardingStatus('completed', 100)
  }

  return (
    <div>
      <input
        value={state.customer.name}
        onChange={(e) => handleSaveName(e.target.value)}
      />
    </div>
  )
}
```

### State Structure
```typescript
interface LoanApplicationState {
  customer: {
    id: string
    name: string
    email: string
    mobile: string
    pan: string
    aadhaar: string
  }
  onboarding: { status: string; progress: number }
  kyc: { status: string; progress: number }
  documents: Document[]
  statement: {
    avgMonthlyCredit: number
    avgMonthlyDebit: number
    stabilityScore: number
    transactionCount: number
  }
  loan: { amount: number; tenure: number; rate: number }
  mandate: { id: string; status: string }
  disbursement: { id: string; status: string; utr: string }
}
```

---

## Design System

### Using Design Tokens

```typescript
import {
  colors,
  spacing,
  typography,
  motion,
  shadows,
  borderRadius,
  zIndex,
  breakpoints,
  transitions
} from '@/lib/design-tokens'

// Colors
const bgColor = colors.primary[500]  // Sky blue
const successColor = colors.success[600]  // Emerald

// Spacing
const padding = spacing.md  // 16px
const margin = spacing.lg  // 24px

// Typography
const fontSize = typography.fontSize.lg  // 1.125rem
const fontWeight = typography.fontWeight.semibold  // 600

// Motion
const duration = motion.duration.base  // 250ms
const easing = motion.easing.easeInOut

// Shadows
const shadow = shadows.md
const glassEffect = shadows.glass

// Border radius
const rounded = borderRadius.lg  // 8px

// Z-index
const modalZ = zIndex.modal  // 1000

// Breakpoints
if (window.innerWidth > breakpoints.md) {
  // Desktop layout
}

// Transitions
const transitionClass = transitions.smooth  // smooth-transition
```

### In Tailwind Classes
```typescript
className={clsx(
  // Colors
  'bg-sky-500 text-sky-950 border-sky-200',
  
  // Spacing
  'p-6 m-4 gap-3',
  
  // Typography
  'text-lg font-semibold leading-tight',
  
  // Shadows
  'shadow-lg hover:shadow-xl',
  
  // Rounded
  'rounded-lg',
  
  // Hover effects
  'hover:bg-sky-600 transition-colors'
)}
```

---

## Common Patterns

### Multi-Step Form
```typescript
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

export const MyForm = () => {
  const [currentStep, setCurrentStep] = useState(0)
  const [formData, setFormData] = useState({})

  const steps = ['Step 1', 'Step 2', 'Step 3']

  const handleNext = () => {
    setCurrentStep((prev) => Math.min(prev + 1, steps.length - 1))
  }

  const handlePrev = () => {
    setCurrentStep((prev) => Math.max(prev - 1, 0))
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={currentStep}
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -20 }}
        transition={{ duration: 0.3 }}
      >
        {/* Step content */}
      </motion.div>
    </AnimatePresence>
  )
}
```

### API Call with Loading
```typescript
const [isLoading, setIsLoading] = useState(false)
const [error, setError] = useState<string | null>(null)

const handleSubmit = async (data: any) => {
  try {
    setIsLoading(true)
    setError(null)
    
    const result = await apiClient.submitData(data)
    
    // Handle success
    console.log('Success:', result)
  } catch (err) {
    setError(err.message)
  } finally {
    setIsLoading(false)
  }
}
```

### Animated List Item
```typescript
import { motion } from 'framer-motion'

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
    },
  },
}

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

export const AnimatedList = ({ items }: { items: any[] }) => {
  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
    >
      {items.map((item) => (
        <motion.div key={item.id} variants={itemVariants}>
          {item.name}
        </motion.div>
      ))}
    </motion.div>
  )
}
```

---

## Debugging Tips

### 1. Check React DevTools
- Install React DevTools Chrome Extension
- Inspect component state
- View component hierarchy
- Check props being passed

### 2. Check Network Tab
```bash
# In Chrome DevTools → Network tab
# Look for API calls to your backend
# Check response status codes
# Verify response payloads
```

### 3. Console Logging
```typescript
// Log API responses
console.log('API Response:', response)

// Log state changes
console.log('Current State:', state)

// Log component render
console.useEffect(() => {
  console.log('Component mounted/updated')
}, [dependency])
```

### 4. TypeScript Errors
```bash
# Check for TypeScript errors
npm run build

# Or in terminal
tsc --noEmit
```

### 5. Common Issues

**Issue**: API returns 404
```
Solution: Check NEXT_PUBLIC_API_BASE_URL in .env.local
```

**Issue**: State not updating
```
Solution: Ensure you're using the update function from context
```

**Issue**: Styles not applied
```
Solution: Verify className spelling and Tailwind is configured
```

**Issue**: Animations not smooth
```
Solution: Check Framer Motion version and browser support
```

---

## Best Practices

✅ **Always use TypeScript**
```typescript
// Good
const handleClick = (value: string): void => {}

// Avoid
const handleClick = (value) => {}
```

✅ **Keep components small**
```typescript
// Break into smaller components
<Dashboard />
  <Header />
  <SideBar />
  <MainContent />
```

✅ **Use design tokens**
```typescript
// Good
backgroundColor: colors.primary[500]

// Avoid
backgroundColor: '#0ea5e9'
```

✅ **Handle errors properly**
```typescript
// Good
try {
  const result = await apiCall()
} catch (error) {
  setError(error.message)
}

// Avoid
const result = await apiCall()  // Unhandled promise
```

✅ **Memoize expensive components**
```typescript
const MemoizedComponent = React.memo(MyComponent)
```

---

## Useful Commands

```bash
# Development
npm run dev              # Start dev server

# Building
npm run build           # Create production build
npm run start           # Start production server

# Linting
npm run lint            # Check code quality

# Analysis
npm run build           # Shows build size

# Type checking
npm run type-check      # Validate TypeScript
```

---

## Resources

- [Next.js Docs](https://nextjs.org/docs)
- [React Hooks Guide](https://react.dev/reference/react)
- [Framer Motion](https://www.framer.com/motion/)
- [Tailwind CSS](https://tailwindcss.com/)
- [TypeScript Handbook](https://www.typescriptlang.org/)

---

**Questions?** Refer to the component code - it's well-documented!
