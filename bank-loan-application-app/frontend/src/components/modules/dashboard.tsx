'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowRight,
  Banknote,
  ChevronRight,
  Clock3,
  FileText,
  Gauge,
  IndianRupee,
  Landmark,
  LineChart,
  LockKeyhole,
  ScanFace,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
} from 'lucide-react'
import { Button } from '../ui'
import { useLoanApplication } from '../../lib/application-state'
import type { LoanPageId } from '../layout'

type DashboardProps = {
  onNavigate: (page: LoanPageId) => void
}

const accountSections = [
  { id: 'onboarding', label: 'Profile', detail: 'Customer data captured', icon: FileText, tone: 'sky' },
  { id: 'kyc', label: 'KYC', detail: 'PAN, Aadhaar, liveness', icon: ScanFace, tone: 'indigo' },
  { id: 'bank-statement', label: 'Cashflow', detail: 'Income graph extracted', icon: LineChart, tone: 'emerald' },
  { id: 'mandate', label: 'Mandate', detail: 'eNACH autopay rail', icon: ShieldCheck, tone: 'amber' },
  { id: 'disbursement', label: 'Payout', detail: 'Funds to bank account', icon: Banknote, tone: 'violet' },
] as const

const insights = [
  { label: 'Approval probability', value: 92, suffix: '%', trend: '+8.4%', icon: Gauge },
  { label: 'Median decision time', value: 4, suffix: 'm', trend: '-62%', icon: Clock3 },
  { label: 'Eligible limit', value: 500000, suffix: '', trend: 'pre-approved', icon: IndianRupee },
]

function useCountUp(target: number, duration = 1100) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(target * eased))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [duration, target])

  return value
}

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value)

export function Dashboard({ onNavigate }: DashboardProps) {
  const { state } = useLoanApplication()

  const completedSteps = useMemo(() => {
    return [
      state.onboardingStatus === 'approved',
      state.kycStatus === 'approved',
      Boolean(state.statementUploaded || state.uploadedDocuments?.length),
      state.mandateStatus === 'active',
      state.disbursementStatus === 'completed',
    ]
  }, [state])

  const currentStepIndex = Math.min(
    completedSteps.findIndex((done) => !done) === -1 ? accountSections.length - 1 : completedSteps.findIndex((done) => !done),
    accountSections.length - 1,
  )
  const progress = Math.round((completedSteps.filter(Boolean).length / accountSections.length) * 100)
  const animatedProgress = useCountUp(progress)
  const animatedLimit = useCountUp(500000)
  const approval = useCountUp(92)

  const nextPage = accountSections[currentStepIndex]?.id ?? 'repayment'
  const nextAction = progress === 100 ? 'View Repayment Hub' : progress > 0 ? 'Continue' : 'Get Started'

  return (
    <div className="loan-dashboard">
      <motion.section
        className="loan-hero"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="loan-hero-copy">
          <div className="loan-eyebrow"><Sparkles className="h-4 w-4" /> Secure digital credit</div>
          <h2>Securely apply for credit and manage your loan account in one place.</h2>
          <p>
            Complete your application process with our high-security digital flow.
            We use agentic intelligence to process your request instantly.
          </p>
          <div className="loan-hero-actions">
            <Button size="lg" onClick={() => onNavigate(progress === 100 ? 'repayment' : nextPage)}>
              {nextAction} <ArrowRight className="h-5 w-5" />
            </Button>
          </div>
        </div>

        <div className="loan-card-stack" aria-label="Loan offer preview">
          <motion.div className="loan-metal-card" whileHover={{ rotateX: 3, rotateY: -5, y: -6 }}>
            <div className="loan-metal-glow" />
            <div className="loan-metal-top">
              <span><Landmark className="h-4 w-4" /> LoanOS Platinum</span>
              <LockKeyhole className="h-5 w-5" />
            </div>
            <div>
              <small>Pre-approved limit</small>
              <strong>{formatCurrency(animatedLimit)}</strong>
            </div>
            <div className="loan-metal-bottom">
              <span>APR 12.5%</span>
              <span>36 months</span>
              <span>EMI {formatCurrency(16733)}</span>
            </div>
          </motion.div>
          <div className="loan-score-ring">
            <svg viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="48" />
              <motion.circle
                cx="60"
                cy="60"
                r="48"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: progress / 100 }}
                transition={{ duration: 1.1, ease: 'easeOut' }}
              />
            </svg>
            <div>
              <strong>{animatedProgress}%</strong>
              <span>complete</span>
            </div>
          </div>
        </div>
      </motion.section>

      <section className="loan-metric-grid">
        {insights.map((item, index) => {
          const Icon = item.icon
          const raw = item.label === 'Eligible limit' ? animatedLimit : item.label === 'Approval probability' ? approval : item.value
          const value = item.label === 'Eligible limit' ? formatCurrency(raw) : `${raw}${item.suffix}`
          return (
            <motion.div
              key={item.label}
              className="loan-metric-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.08 }}
              whileHover={{ y: -6 }}
            >
              <div className="loan-metric-icon"><Icon className="h-5 w-5" /></div>
              <span>{item.label}</span>
              <strong>{value}</strong>
              <small><TrendingUp className="h-3.5 w-3.5" /> {item.trend}</small>
            </motion.div>
          )
        })}
      </section>

      <div className="loan-dashboard-grid">
        <motion.section className="loan-workflow-panel" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}>
          <div className="loan-section-head">
            <div>
              <span>Active Task</span>
              <h3>Required next step</h3>
            </div>
          </div>

          <div className="loan-account-task-grid">
            {accountSections.filter((_, idx) => idx === currentStepIndex).map((stage) => {
              const Icon = stage.icon
              const done = completedSteps[currentStepIndex]
              const active = !done
              return (
                <motion.button
                  key={stage.id}
                  className={`loan-account-task ${done ? 'done' : ''} ${active ? 'active' : ''}`}
                  onClick={() => onNavigate(stage.id)}
                  whileHover={{ y: -5 }}
                  whileTap={{ scale: 0.98 }}
                  style={{ width: '100%', gridColumn: 'span 2' }}
                >
                  <span className="loan-account-task-icon">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span>
                    <strong>{stage.label}</strong>
                    <small>{done ? 'Completed' : active ? 'Needs your attention to proceed' : stage.detail}</small>
                  </span>
                  <ChevronRight className="ml-auto h-5 w-5 text-neutral-400" />
                </motion.button>
              )
            })}
          </div>
        </motion.section>

        <motion.section className="loan-underwriting-panel" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}>
          <div className="loan-section-head compact">
            <div>
              <span>Underwriting signal</span>
              <h3>Credit confidence</h3>
            </div>
            <span className="loan-ai-chip"><Zap className="h-3.5 w-3.5" /> AI live</span>
          </div>

          <div className="loan-chart">
            {[46, 64, 52, 78, 72, 88, 92, 84, 96].map((height, index) => (
              <motion.span
                key={index}
                initial={{ height: 0 }}
                animate={{ height: `${height}%` }}
                transition={{ delay: 0.08 * index, duration: 0.75, ease: 'easeOut' }}
              />
            ))}
          </div>
          <div className="loan-risk-copy">
            <strong>{approval}% approval confidence</strong>
            <p>Stable income, low volatility, verified repayment rail pending.</p>
          </div>
        </motion.section>
      </div>

      <div className="loan-dashboard-grid bottom">
        <section className="loan-orchestration-panel">
          <div className="loan-section-head">
            <div>
              <span>Account health</span>
              <h3>Security and service status</h3>
            </div>
            <span className="loan-live-chip inline"><span /> Available</span>
          </div>
          <div className="loan-service-list">
            {[
              { label: 'Data encryption', status: 'Enabled', latency: 'AES-256' },
              { label: 'Identity checks', status: 'Available', latency: 'Secure' },
              { label: 'Autopay services', status: 'Available', latency: 'NPCI' },
              { label: 'Transfer tracking', status: 'Ready', latency: 'UTR' },
            ].map((service, index) => (
              <motion.div
                className="loan-service-row"
                key={service.label}
                initial={{ opacity: 0, x: -18 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 * index }}
              >
                <span className="loan-service-pulse" />
                <div>
                  <strong>{service.label}</strong>
                  <small>{service.status}</small>
                </div>
                <code>{service.latency}</code>
              </motion.div>
            ))}
          </div>
        </section>

        <section className="loan-story-panel">
          <div className="loan-section-head compact">
            <div>
              <span>Account summary</span>
              <h3>Status update</h3>
            </div>
          </div>
          <div className="loan-story-list">
            <div><ShieldCheck className="h-5 w-5" /><span>{progress === 100 ? 'Loan application process is complete.' : 'Your application is currently being processed securely.'}</span></div>
            <div><Sparkles className="h-5 w-5" /><span>Next step will be unlocked once the current task is completed.</span></div>
          </div>
        </section>
      </div>
    </div>
  )
}
