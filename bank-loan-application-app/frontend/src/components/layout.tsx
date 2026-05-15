'use client'

import React, { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import clsx from 'clsx'
import {
  Activity,
  ArrowUpRight,
  Banknote,
  Bell,
  ChevronDown,
  CircleDollarSign,
  CreditCard,
  FileText,
  HeadphonesIcon,
  Home,
  Landmark,
  LockKeyhole,
  LogOut,
  Menu,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  ScanFace,
  Settings,
  ShieldCheck,
  User,
  WalletCards,
  X,
  Zap,
} from 'lucide-react'

export type LoanPageId =
  | 'dashboard'
  | 'onboarding'
  | 'kyc'
  | 'bank-statement'
  | 'mandate'
  | 'disbursement'
  | 'repayment'
  | 'support'

interface NavItem {
  id: LoanPageId
  label: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  status: 'ready' | 'live' | 'queued' | 'done'
  accent: string
}

const navItems: NavItem[] = [
  { id: 'dashboard', label: 'Command Center', description: 'Portfolio overview', icon: Home, status: 'live', accent: 'from-sky-500 to-blue-600' },
  { id: 'onboarding', label: 'Loan Application', description: 'Digital journey', icon: FileText, status: 'ready', accent: 'from-cyan-500 to-sky-600' },
  { id: 'support', label: 'Priority Support', description: 'Customer care', icon: MessageSquare, status: 'ready', accent: 'from-rose-500 to-pink-600' },
]

const notifications = [
  { title: 'Account review ready', body: 'Your latest details are ready for a secure review.', tone: 'info' },
  { title: 'Autopay services available', body: 'Mandate registration services are currently healthy.', tone: 'success' },
  { title: 'Documents may be required', body: 'Keep identity and income documents handy for faster processing.', tone: 'warning' },
]

const quickActions = [
  { id: 'onboarding' as LoanPageId, label: 'Profile details', icon: FileText },
  { id: 'kyc' as LoanPageId, label: 'Verify identity', icon: ShieldCheck },
  { id: 'bank-statement' as LoanPageId, label: 'Income review', icon: Activity },
  { id: 'repayment' as LoanPageId, label: 'Repayments', icon: CircleDollarSign },
]

const pageCopy: Record<LoanPageId, { title: string; crumb: string; subtitle: string }> = {
  dashboard: { title: 'Loan Overview', crumb: 'Overview', subtitle: 'Manage your loan account, documents, transfers, and repayments.' },
  onboarding: { title: 'Applicant Profile', crumb: 'Profile', subtitle: 'Keep your personal, work, income, and address details updated.' },
  kyc: { title: 'Identity Verification', crumb: 'Identity', subtitle: 'Verify PAN, Aadhaar, and selfie details securely.' },
  'bank-statement': { title: 'Income Review', crumb: 'Income', subtitle: 'Upload bank statements for a secure financial review.' },
  mandate: { title: 'Autopay Setup', crumb: 'Autopay', subtitle: 'Authorize EMI payments from your preferred bank.' },
  disbursement: { title: 'Loan Transfer', crumb: 'Payout', subtitle: 'Review your approved loan and transfer details.' },
  repayment: { title: 'Repayment Hub', crumb: 'Servicing', subtitle: 'Track EMI health, transactions, and account service.' },
  support: { title: 'Customer Support', crumb: 'Care', subtitle: 'Raise service requests and get help with your loan account.' },
}

export const AppLayout: React.FC<{
  children: React.ReactNode
  onNavigate?: (id: LoanPageId) => void
  currentPage?: LoanPageId
  canNavigate?: (id: LoanPageId) => boolean
  onBlockedNavigate?: (id: LoanPageId) => void
}> = ({ children, onNavigate, currentPage = 'dashboard', canNavigate = () => true, onBlockedNavigate }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [notificationOpen, setNotificationOpen] = useState(false)

  const activeCopy = pageCopy[currentPage]

  const navigate = (id: LoanPageId) => {
    if (!canNavigate(id)) {
      onBlockedNavigate?.(id)
      return
    }
    onNavigate?.(id)
    setMobileOpen(false)
  }

  return (
    <div className="loan-shell">
      <div className="loan-aurora" />

      <AnimatePresence>
        {mobileOpen && (
          <motion.button
            aria-label="Close navigation"
            className="loan-mobile-scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      <motion.aside
        className={clsx('loan-sidebar', !sidebarOpen && 'is-collapsed', mobileOpen && 'is-mobile-open')}
        animate={{ width: sidebarOpen ? 304 : 92 }}
        transition={{ type: 'spring', stiffness: 260, damping: 28 }}
      >
        <div className="loan-brand">
          <button className="loan-mark" onClick={() => navigate('dashboard')} aria-label="Open command center">
            <Landmark className="h-5 w-5" />
          </button>
          <AnimatePresence initial={false}>
            {sidebarOpen && (
              <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }}>
                <div className="loan-brand-title">LoanOS</div>
                <div className="loan-brand-subtitle">Digital lending suite</div>
              </motion.div>
            )}
          </AnimatePresence>
          <button className="loan-collapse" onClick={() => setSidebarOpen((value) => !value)} aria-label="Toggle sidebar">
            {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </button>
        </div>

        <div className="loan-nav-label">{sidebarOpen ? 'Loan Account' : 'Menu'}</div>
        <nav className="loan-nav">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = item.id === currentPage
            const locked = !canNavigate(item.id)
            return (
              <button
                key={item.id}
                className={clsx('loan-nav-item', isActive && 'is-active', locked && 'is-locked')}
                onClick={() => navigate(item.id)}
                title={!sidebarOpen ? item.label : undefined}
              >
                <span className={clsx('loan-nav-icon', `bg-gradient-to-br ${item.accent}`)}>
                  <Icon className="h-4 w-4" />
                </span>
                {sidebarOpen && (
                  <>
                    <span className="loan-nav-copy">
                      <span>{item.label}</span>
                      <small>{item.description}</small>
                    </span>
                    {locked ? <LockKeyhole className="loan-lock h-3.5 w-3.5" /> : <span className={clsx('loan-status-dot', item.status)} />}
                  </>
                )}
                {isActive && <motion.span className="loan-active-pill" layoutId="loan-active-pill" />}
              </button>
            )
          })}
        </nav>

        <AnimatePresence initial={false}>
          {sidebarOpen && (
            <motion.div className="loan-sidebar-card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}>
              <div className="loan-card-orbit">
                <Zap className="h-4 w-4" />
              </div>
              <p>Secure account</p>
              <strong>Bank-grade protection</strong>
              <div className="loan-mini-meter">
                <span style={{ width: '82%' }} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.aside>

      <div className="loan-main">
        <header className="loan-topbar">
          <div className="loan-top-left">
            <button className="loan-icon-btn mobile-only" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
              <Menu className="h-5 w-5" />
            </button>
            <div className="loan-breadcrumb">
              <span>LoanOS</span>
              <ArrowUpRight className="h-3.5 w-3.5" />
              <strong>{activeCopy.crumb}</strong>
            </div>
            <div>
              <h1>{activeCopy.title}</h1>
              <p>{activeCopy.subtitle}</p>
            </div>
          </div>

          <div className="loan-top-actions">
            <button className="loan-live-chip">
              <span />
              Live
            </button>

            <div className="relative">
              <button className="loan-icon-btn" onClick={() => setNotificationOpen((value) => !value)} aria-label="Open notifications">
                <Bell className="h-5 w-5" />
                <span className="loan-alert-dot" />
              </button>
              <AnimatePresence>
                {notificationOpen && (
                  <motion.div className="loan-popover notifications" initial={{ opacity: 0, y: 10, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.96 }}>
                    <div className="loan-popover-head">
                      <strong>Notification Center</strong>
                      <button onClick={() => setNotificationOpen(false)} aria-label="Close notifications">
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    {notifications.map((item) => (
                      <div className="loan-note" key={item.title}>
                        <span className={clsx('loan-note-dot', item.tone)} />
                        <div>
                          <strong>{item.title}</strong>
                          <p>{item.body}</p>
                        </div>
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <div className="relative">
              <button className="loan-profile" onClick={() => setUserMenuOpen((value) => !value)}>
                <span className="loan-avatar"><User className="h-4 w-4" /></span>
                <span className="loan-profile-copy">
                  <strong>Priya Shah</strong>
                  <small>Credit Ops Lead</small>
                </span>
                <ChevronDown className="h-4 w-4" />
              </button>
              <AnimatePresence>
                {userMenuOpen && (
                  <motion.div className="loan-popover profile" initial={{ opacity: 0, y: 10, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.96 }}>
                    <button><User className="h-4 w-4" /> Profile</button>
                    <button><Settings className="h-4 w-4" /> Workspace settings</button>
                    <button><HeadphonesIcon className="h-4 w-4" /> Concierge support</button>
                    <button><LogOut className="h-4 w-4" /> Sign out</button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </header>

        <div className="loan-action-dock" aria-label="Quick actions">
          {quickActions.map((action) => {
            const Icon = action.icon
            return (
              <button key={action.id} onClick={() => navigate(action.id)} title={action.label}>
                <Icon className="h-5 w-5" />
                <span>{action.label}</span>
                {!canNavigate(action.id) && <LockKeyhole className="h-3.5 w-3.5" />}
              </button>
            )
          })}
        </div>

        <main className="loan-content">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentPage}
              initial={{ opacity: 0, y: 18, filter: 'blur(8px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              exit={{ opacity: 0, y: -14, filter: 'blur(8px)' }}
              transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  )
}
