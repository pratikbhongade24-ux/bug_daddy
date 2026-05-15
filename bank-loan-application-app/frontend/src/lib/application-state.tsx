'use client'

import React, { createContext, useCallback, useContext, useState } from 'react'

export type OnboardingStatus = 'not_started' | 'in_progress' | 'submitted' | 'approved' | 'rejected'
export type KycStatus = 'not_started' | 'pan_verified' | 'aadhaar_verified' | 'face_matched' | 'approved' | 'rejected'
export type MandateStatus = 'not_created' | 'registered' | 'validated' | 'active' | 'cancelled'
export type DisbursementStatus = 'not_created' | 'created' | 'account_validated' | 'processing' | 'completed'
export type TicketStatus = 'open' | 'assigned' | 'in_progress' | 'resolved'

export interface PersonalInfo {
  name: string
  email: string
  mobile: string
  pan: string
  aadhaar: string
}

export interface EmploymentInfo {
  type: string
  company: string
  role: string
  experience: string
}

export interface IncomeInfo {
  monthlyIncome: string
  existingEmi: string
  loanPurpose: string
}

export interface AddressInfo {
  line1: string
  city: string
  state: string
  pincode: string
}

export interface Transaction {
  id: string
  date: string
  description: string
  category: string
  type: 'credit' | 'debit'
  amount: number
  risk?: 'low' | 'medium' | 'high'
}

export interface CashflowSummary {
  avgMonthlyCredit: number
  avgMonthlyDebit: number
  avgMonthlyBalance: number
  stability: string
  score: number
}

export interface SupportTicket {
  id: string
  category: string
  issue: string
  priority: 'low' | 'medium' | 'high'
  status: TicketStatus
  comments: string[]
  createdAt: string
}

export interface ActivityItem {
  id: string
  title: string
  description: string
  time: string
  tone: 'info' | 'success' | 'warning' | 'error'
}

export interface LoanApplicationState {
  customerId: string
  personalInfo?: PersonalInfo
  employmentInfo?: EmploymentInfo
  incomeInfo?: IncomeInfo
  addressInfo?: AddressInfo
  onboardingStatus: OnboardingStatus
  onboardingProgress: number
  kycStatus: KycStatus
  kycProgress: number
  uploadedDocuments: string[]
  statementUploaded: boolean
  transactions: Transaction[]
  cashflow?: CashflowSummary
  loanAmount: number
  loanTenure: number
  interestRate: number
  mandateId?: string
  mandateStatus: MandateStatus
  disbursementId?: string
  disbursementStatus: DisbursementStatus
  utr?: string
  supportTickets: SupportTicket[]
  activities: ActivityItem[]
}

interface OnboardingPayload {
  personalInfo?: PersonalInfo
  employmentInfo?: EmploymentInfo
  incomeInfo?: IncomeInfo
  addressInfo?: AddressInfo
  documents?: string[]
  status?: OnboardingStatus
  progress?: number
}

interface KycPayload {
  status: KycStatus
  progress?: number
}

interface BankStatementPayload {
  documents: string[]
  transactions: Transaction[]
  cashflow: CashflowSummary
}

interface LoanDetailsPayload {
  amount: number
  tenure: number
  rate: number
}

interface MandatePayload {
  id?: string
  status: MandateStatus
}

interface DisbursementPayload {
  id?: string
  status: DisbursementStatus
  utr?: string
}

interface LoanApplicationContextType {
  state: LoanApplicationState
  updateOnboarding: (payload: OnboardingPayload) => void
  updatePersonalInfo: (info: Partial<PersonalInfo>) => void
  updateOnboardingStatus: (status: { status: OnboardingStatus; progress?: number }) => void
  updateKycStatus: (status: KycPayload) => void
  updateDocuments: (docs: string[]) => void
  updateBankStatement: (payload: BankStatementPayload) => void
  updateLoanDetails: (details: LoanDetailsPayload) => void
  updateMandateStatus: (status: MandatePayload) => void
  updateDisbursementStatus: (status: DisbursementPayload) => void
  addSupportTicket: (ticket: SupportTicket) => void
  updateSupportTicket: (ticketId: string, patch: Partial<SupportTicket>) => void
  addActivity: (activity: Omit<ActivityItem, 'id' | 'time'>) => void
  reset: () => void
}

const LoanApplicationContext = createContext<LoanApplicationContextType | undefined>(undefined)

const createCustomerId = () => `CUST-${Math.random().toString(36).slice(2, 11).toUpperCase()}`

const createInitialState = (): LoanApplicationState => ({
  customerId: createCustomerId(),
  onboardingStatus: 'not_started',
  onboardingProgress: 0,
  kycStatus: 'not_started',
  kycProgress: 0,
  uploadedDocuments: [],
  statementUploaded: false,
  transactions: [],
  loanAmount: 500000,
  loanTenure: 36,
  interestRate: 12.5,
  mandateStatus: 'not_created',
  disbursementStatus: 'not_created',
  supportTickets: [],
  activities: [
    {
      id: 'act-boot',
      title: 'Workspace initialized',
      description: 'Loan journey is ready for a new applicant.',
      time: 'Just now',
      tone: 'info',
    },
  ],
})

export const LoanApplicationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<LoanApplicationState>(() => createInitialState())

  const addActivity = useCallback((activity: Omit<ActivityItem, 'id' | 'time'>) => {
    setState((prev) => ({
      ...prev,
      activities: [
        { ...activity, id: `act-${Date.now()}`, time: 'Just now' },
        ...prev.activities,
      ].slice(0, 8),
    }))
  }, [])

  const updateOnboarding = useCallback((payload: OnboardingPayload) => {
    setState((prev) => ({
      ...prev,
      personalInfo: payload.personalInfo ?? prev.personalInfo,
      employmentInfo: payload.employmentInfo ?? prev.employmentInfo,
      incomeInfo: payload.incomeInfo ?? prev.incomeInfo,
      addressInfo: payload.addressInfo ?? prev.addressInfo,
      uploadedDocuments: payload.documents ?? prev.uploadedDocuments,
      onboardingStatus: payload.status ?? prev.onboardingStatus,
      onboardingProgress: payload.progress ?? prev.onboardingProgress,
    }))
  }, [])

  const updatePersonalInfo = useCallback((info: Partial<PersonalInfo>) => {
    setState((prev) => ({
      ...prev,
      personalInfo: { ...(prev.personalInfo ?? { name: '', email: '', mobile: '', pan: '', aadhaar: '' }), ...info },
    }))
  }, [])

  const updateOnboardingStatus = useCallback((status: { status: OnboardingStatus; progress?: number }) => {
    setState((prev) => ({
      ...prev,
      onboardingStatus: status.status,
      onboardingProgress: status.progress ?? prev.onboardingProgress,
    }))
  }, [])

  const updateKycStatus = useCallback((status: KycPayload) => {
    setState((prev) => ({
      ...prev,
      kycStatus: status.status,
      kycProgress: status.progress ?? prev.kycProgress,
    }))
  }, [])

  const updateDocuments = useCallback((docs: string[]) => {
    setState((prev) => ({
      ...prev,
      uploadedDocuments: docs,
      statementUploaded: docs.some((doc) => doc.toLowerCase().includes('statement')) || prev.statementUploaded,
    }))
  }, [])

  const updateBankStatement = useCallback((payload: BankStatementPayload) => {
    setState((prev) => ({
      ...prev,
      uploadedDocuments: payload.documents,
      statementUploaded: true,
      transactions: payload.transactions,
      cashflow: payload.cashflow,
    }))
  }, [])

  const updateLoanDetails = useCallback((details: LoanDetailsPayload) => {
    setState((prev) => ({
      ...prev,
      loanAmount: details.amount,
      loanTenure: details.tenure,
      interestRate: details.rate,
    }))
  }, [])

  const updateMandateStatus = useCallback((status: MandatePayload) => {
    setState((prev) => ({
      ...prev,
      mandateId: status.id ?? prev.mandateId,
      mandateStatus: status.status,
    }))
  }, [])

  const updateDisbursementStatus = useCallback((status: DisbursementPayload) => {
    setState((prev) => ({
      ...prev,
      disbursementId: status.id ?? prev.disbursementId,
      disbursementStatus: status.status,
      utr: status.utr ?? prev.utr,
    }))
  }, [])

  const addSupportTicket = useCallback((ticket: SupportTicket) => {
    setState((prev) => ({
      ...prev,
      supportTickets: [ticket, ...prev.supportTickets],
    }))
  }, [])

  const updateSupportTicket = useCallback((ticketId: string, patch: Partial<SupportTicket>) => {
    setState((prev) => ({
      ...prev,
      supportTickets: prev.supportTickets.map((ticket) =>
        ticket.id === ticketId ? { ...ticket, ...patch } : ticket,
      ),
    }))
  }, [])

  const reset = useCallback(() => {
    setState(createInitialState())
  }, [])

  return (
    <LoanApplicationContext.Provider
      value={{
        state,
        updateOnboarding,
        updatePersonalInfo,
        updateOnboardingStatus,
        updateKycStatus,
        updateDocuments,
        updateBankStatement,
        updateLoanDetails,
        updateMandateStatus,
        updateDisbursementStatus,
        addSupportTicket,
        updateSupportTicket,
        addActivity,
        reset,
      }}
    >
      {children}
    </LoanApplicationContext.Provider>
  )
}

export const useLoanApplication = () => {
  const context = useContext(LoanApplicationContext)
  if (!context) {
    throw new Error('useLoanApplication must be used within LoanApplicationProvider')
  }
  return context
}
