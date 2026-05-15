/**
 * Main Loan Application
 * Central hub for all loan modules
 */

'use client'

import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { AppLayout, type LoanPageId } from '../../components/layout'
import { Dashboard } from '../../components/modules/dashboard'
import { OnboardingModule } from '../../components/modules/onboarding'
import { KYCModule } from '../../components/modules/kyc'
import { BankStatementModule } from '../../components/modules/bank-statement'
import { MandateSetupModule } from '../../components/modules/mandate'
import { DisbursementModule } from '../../components/modules/disbursement'
import { RepaymentModule, SupportModule } from '../../components/modules/repayment-support'
import { LoanApplicationProvider, useLoanApplication } from '../../lib/application-state'

type Page = LoanPageId

const prerequisiteCopy: Record<Page, string> = {
  dashboard: '',
  onboarding: '',
  kyc: 'Complete customer onboarding before starting KYC.',
  'bank-statement': 'Finish KYC before importing bank statements.',
  mandate: 'Analyze bank statements before setting up auto-debit.',
  disbursement: 'Activate the auto-debit mandate before disbursement.',
  repayment: 'Complete disbursement before opening repayment servicing.',
  support: '',
}

function LoanContent() {
  const { state } = useLoanApplication()
  const [currentPage, setCurrentPage] = useState<Page>('dashboard')
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null)

  const canNavigate = (page: Page) => {
    if (page === 'dashboard' || page === 'onboarding' || page === 'support') return true
    if (page === 'kyc') return state.onboardingStatus === 'approved'
    if (page === 'bank-statement') return state.kycStatus === 'approved'
    if (page === 'mandate') return state.statementUploaded
    if (page === 'disbursement') return state.mandateStatus === 'active'
    if (page === 'repayment') return state.disbursementStatus === 'completed'
    return false
  }

  const navigateTo = (page: Page) => {
    if (!canNavigate(page)) {
      setBlockedMessage(prerequisiteCopy[page])
      window.setTimeout(() => setBlockedMessage(null), 3200)
      return
    }
    setCurrentPage(page)
    setBlockedMessage(null)
    window.scrollTo(0, 0)
  }

  const handleModuleComplete = (nextPage: Page) => {
    navigateTo(nextPage)
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <Dashboard onNavigate={navigateTo} />
      case 'onboarding':
        return <OnboardingModule onComplete={() => handleModuleComplete('kyc')} />
      case 'kyc':
        return <KYCModule onComplete={() => handleModuleComplete('bank-statement')} />
      case 'bank-statement':
        return <BankStatementModule onComplete={() => handleModuleComplete('mandate')} />
      case 'mandate':
        return <MandateSetupModule onComplete={() => handleModuleComplete('disbursement')} />
      case 'disbursement':
        return <DisbursementModule onComplete={() => handleModuleComplete('repayment')} />
      case 'repayment':
        return <RepaymentModule onNavigate={navigateTo} />
      case 'support':
        return <SupportModule />
      default:
        return <Dashboard onNavigate={navigateTo} />
    }
  }

  return (
    <AppLayout
      onNavigate={navigateTo}
      currentPage={currentPage}
      canNavigate={canNavigate}
      onBlockedNavigate={(page) => {
        setBlockedMessage(prerequisiteCopy[page])
        window.setTimeout(() => setBlockedMessage(null), 3200)
      }}
    >
      <AnimatePresence>
        {blockedMessage && (
          <motion.div
            className="loan-gate-toast"
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.98 }}
          >
            {blockedMessage}
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence mode="wait">
        <motion.div
          key={currentPage}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
        >
          {renderPage()}
        </motion.div>
      </AnimatePresence>
    </AppLayout>
  )
}

export default function LoanPage() {
  return (
    <LoanApplicationProvider>
      <LoanContent />
    </LoanApplicationProvider>
  )
}
