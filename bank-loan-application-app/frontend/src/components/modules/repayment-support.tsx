'use client'

import React, { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import clsx from 'clsx'
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  ArrowUpRight,
  Bot,
  Calendar,
  CheckCircle2,
  ChevronDown,
  Clock3,
  CreditCard,
  Download,
  HeadphonesIcon,
  MessageCircle,
  Plus,
  ReceiptText,
  ScanFace,
  Send,
  ShieldCheck,
  Sparkles,
  Ticket,
  WalletCards,
  Zap,
} from 'lucide-react'

import { apiClient } from '../../../lib/api-client'
import {
  useLoanApplication,
  type SupportTicket,
} from '../../lib/application-state'

import type { LoanPageId } from '../layout'
import { Badge, Button, Card, Input } from '../ui'

const payments = [
  {
    id: 'emi-1',
    date: '05 Jun 2026',
    amount: 16733,
    status: 'upcoming',
  },
  {
    id: 'emi-2',
    date: '05 Jul 2026',
    amount: 16733,
    status: 'scheduled',
  },
  {
    id: 'emi-3',
    date: '05 Aug 2026',
    amount: 16733,
    status: 'scheduled',
  },
  {
    id: 'fee-1',
    date: 'Today',
    amount: 5000,
    status: 'paid',
  },
]

const chartData = [
  { month: 'Jan', value: 92 },
  { month: 'Feb', value: 84 },
  { month: 'Mar', value: 80 },
  { month: 'Apr', value: 71 },
  { month: 'May', value: 62 },
  { month: 'Jun', value: 55 },
]

function PremiumCard({
  children,
  className,
}: React.PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={clsx(
        'rounded-[32px] border border-white/40 bg-white/70 backdrop-blur-2xl shadow-[0_8px_40px_rgba(15,23,42,0.08)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

function SectionLabel({ children }: React.PropsWithChildren) {
  return (
    <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">
      {children}
    </p>
  )
}

function StatCard({
  label,
  value,
  description,
  icon: Icon,
}: {
  label: string
  value: string
  description: string
  icon: any
}) {
  return (
    <motion.div
      whileHover={{ y: -4 }}
      transition={{ duration: 0.2 }}
      className="rounded-[28px] border border-slate-100 bg-white p-6"
    >
      <div className="flex items-center justify-between">
        <div className="rounded-2xl bg-slate-100 p-3 text-slate-700">
          <Icon className="h-5 w-5" />
        </div>

        <ArrowUpRight className="h-5 w-5 text-slate-300" />
      </div>

      <p className="mt-6 text-sm font-medium text-slate-400">{label}</p>

      <h3 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
        {value}
      </h3>

      <p className="mt-2 text-sm leading-6 text-slate-500">
        {description}
      </p>
    </motion.div>
  )
}

export function RepaymentModule({
  onNavigate,
}: {
  onNavigate?: (page: LoanPageId) => void
}) {
  const [openCard, setOpenCard] = useState('emi-1')

  const paidPercent = 8

  const repaymentHealth = useMemo(() => {
    if (paidPercent < 25) return 'Healthy'
    if (paidPercent < 50) return 'Very Stable'
    return 'Excellent'
  }, [paidPercent])

  return (
    <div className="relative mx-auto max-w-7xl space-y-8 px-4 pb-12 md:px-6">
      <div className="fixed inset-0 -z-10 overflow-hidden bg-[#f6f8fb]">
        <div className="absolute left-0 top-0 h-[500px] w-[500px] rounded-full bg-sky-200/30 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-[500px] w-[500px] rounded-full bg-violet-200/20 blur-3xl" />
      </div>

      <PremiumCard className="overflow-hidden p-8 md:p-10">
        <div className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div>
            <Badge className="rounded-full border-0 bg-sky-100 px-4 py-1 text-sky-700">
              Active Loan Account
            </Badge>

            <h1 className="mt-6 max-w-xl text-4xl font-semibold tracking-tight text-slate-950 md:text-5xl">
              Smart repayment dashboard for your personal loan.
            </h1>

            <p className="mt-5 max-w-2xl text-base leading-8 text-slate-500">
              Track EMIs, automate repayments, monitor outstanding balance,
              download statements, and manage your loan journey from one
              beautiful workspace.
            </p>

            <div className="mt-10 grid gap-4 md:grid-cols-3">
              <StatCard
                label="Next EMI"
                value="₹16,733"
                description="Due on 05 Jun"
                icon={Calendar}
              />

              <StatCard
                label="Outstanding"
                value="₹4.95L"
                description="35 EMIs remaining"
                icon={WalletCards}
              />

              <StatCard
                label="Auto Debit"
                value="Active"
                description="Mandate verified"
                icon={ShieldCheck}
              />
            </div>
          </div>

          <div className="flex justify-center">
            <div className="relative flex h-[320px] w-[320px] items-center justify-center rounded-full bg-white/60 backdrop-blur-xl">
              <div
                className="relative h-[250px] w-[250px] rounded-full"
                style={{
                  background: `conic-gradient(#0ea5e9 ${paidPercent}%, #e2e8f0 0%)`,
                }}
              >
                <div className="absolute inset-5 flex flex-col items-center justify-center rounded-full bg-white shadow-inner">
                  <p className="text-sm font-medium text-slate-400">
                    Loan Repaid
                  </p>

                  <h2 className="mt-2 text-6xl font-semibold tracking-tight text-slate-950">
                    {paidPercent}%
                  </h2>

                  <div className="mt-5 rounded-full bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700">
                    {repaymentHealth}
                  </div>
                </div>
              </div>

              <div className="absolute -right-5 top-10 rounded-2xl border border-white/50 bg-white/90 p-4 shadow-xl backdrop-blur-xl">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-sky-100 p-2 text-sky-700">
                    <Sparkles className="h-5 w-5" />
                  </div>

                  <div>
                    <p className="text-xs font-medium text-slate-400">
                      AI Insight
                    </p>

                    <p className="text-sm font-semibold text-slate-900">
                      No overdue risk detected.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </PremiumCard>

      <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
        <PremiumCard className="p-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <SectionLabel>Payment Timeline</SectionLabel>

              <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
                EMI Schedule
              </h2>
            </div>

            <Button className="h-12 rounded-2xl bg-slate-950 px-5 text-white hover:bg-slate-800">
              <Download className="mr-2 h-4 w-4" />
              Download Statement
            </Button>
          </div>

          <div className="mt-10 space-y-4">
            {payments.map((payment) => (
              <motion.div
                whileHover={{ y: -2 }}
                key={payment.id}
                className="overflow-hidden rounded-[28px] border border-slate-100 bg-white"
              >
                <button
                  onClick={() =>
                    setOpenCard(openCard === payment.id ? '' : payment.id)
                  }
                  className="w-full p-6 text-left"
                >
                  <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex items-center gap-5">
                      <div
                        className={clsx(
                          'flex h-14 w-14 items-center justify-center rounded-2xl',
                          payment.status === 'paid'
                            ? 'bg-emerald-50 text-emerald-600'
                            : 'bg-sky-50 text-sky-600',
                        )}
                      >
                        <Calendar className="h-6 w-6" />
                      </div>

                      <div>
                        <h3 className="text-lg font-semibold text-slate-950">
                          {payment.date}
                        </h3>

                        <p className="mt-1 text-sm text-slate-500">
                          EMI autopay via HDFC eMandate
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-4">
                      <Badge
                        className={clsx(
                          'rounded-full px-4 py-1 capitalize',
                          payment.status === 'paid'
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-amber-100 text-amber-700',
                        )}
                      >
                        {payment.status}
                      </Badge>

                      <h4 className="text-xl font-semibold text-slate-950">
                        ₹{payment.amount.toLocaleString('en-IN')}
                      </h4>

                      <ChevronDown
                        className={clsx(
                          'h-5 w-5 text-slate-400 transition-transform duration-300',
                          openCard === payment.id && 'rotate-180',
                        )}
                      />
                    </div>
                  </div>
                </button>

                <AnimatePresence>
                  {openCard === payment.id && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden border-t border-slate-100"
                    >
                      <div className="grid gap-4 p-6 md:grid-cols-3">
                        <div className="rounded-2xl bg-slate-50 p-5">
                          <p className="text-sm font-medium text-slate-400">
                            Principal
                          </p>

                          <h4 className="mt-2 text-2xl font-semibold text-slate-950">
                            ₹12,050
                          </h4>
                        </div>

                        <div className="rounded-2xl bg-slate-50 p-5">
                          <p className="text-sm font-medium text-slate-400">
                            Interest
                          </p>

                          <h4 className="mt-2 text-2xl font-semibold text-slate-950">
                            ₹4,683
                          </h4>
                        </div>

                        <button className="rounded-2xl bg-sky-50 p-5 text-left transition hover:bg-sky-100">
                          <ReceiptText className="mb-3 h-5 w-5 text-sky-700" />

                          <p className="font-semibold text-sky-700">
                            Download Receipt
                          </p>
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))}
          </div>
        </PremiumCard>

        <div className="space-y-8">
          <PremiumCard className="p-8">
            <div className="flex items-center justify-between">
              <div>
                <SectionLabel>Analytics</SectionLabel>

                <h3 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
                  Balance Forecast
                </h3>
              </div>

              <div className="rounded-2xl bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700">
                Stable
              </div>
            </div>

            <div className="mt-8 h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                    </linearGradient>
                  </defs>

                  <XAxis dataKey="month" axisLine={false} tickLine={false} />

                  <YAxis hide />

                  <Tooltip />

                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#0ea5e9"
                    strokeWidth={3}
                    fillOpacity={1}
                    fill="url(#colorValue)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="mt-6 rounded-3xl bg-emerald-50 p-5">
              <div className="flex items-start gap-4">
                <div className="rounded-2xl bg-white p-3 text-emerald-600">
                  <CheckCircle2 className="h-5 w-5" />
                </div>

                <div>
                  <h4 className="font-semibold text-emerald-800">
                    Excellent repayment behaviour
                  </h4>

                  <p className="mt-1 text-sm leading-6 text-emerald-700">
                    Your EMI repayments are on track and no overdue indicators
                    were detected in the last 90 days.
                  </p>
                </div>
              </div>
            </div>
          </PremiumCard>

          <PremiumCard className="bg-slate-950 p-8 text-white">
            <div className="flex items-center gap-4">
              <div className="rounded-2xl bg-white/10 p-3">
                <Bot className="h-6 w-6" />
              </div>

              <div>
                <p className="text-sm text-slate-400">AI Assistant</p>

                <h3 className="text-2xl font-semibold tracking-tight">
                  Need help with repayments?
                </h3>
              </div>
            </div>

            <p className="mt-5 text-sm leading-7 text-slate-400">
              Get instant answers for repayment schedules, foreclosure charges,
              loan statements, mandate failures, and more.
            </p>

            <Button
              onClick={() => onNavigate?.('support')}
              className="mt-8 h-12 rounded-2xl bg-white px-5 text-slate-950 hover:bg-slate-100"
            >
              <HeadphonesIcon className="mr-2 h-4 w-4" />
              Contact Support
            </Button>
          </PremiumCard>
        </div>
      </div>
    </div>
  )
}

export function SupportModule() {
  const { state, addSupportTicket, updateSupportTicket, addActivity } =
    useLoanApplication()

  const [category, setCategory] = useState('Repayment')
  const [issue, setIssue] = useState('')

  const [priority, setPriority] = useState<
    'low' | 'medium' | 'high'
  >('medium')

  const [loading, setLoading] = useState(false)
  const [openFaq, setOpenFaq] = useState(0)

  const createTicket = async () => {
    if (!issue.trim()) return

    setLoading(true)

    try {
      const response = await apiClient.createTicket(
        state.customerId,
        `${category}: ${issue}`,
        priority,
      )

      const payload = response.payload as {
        ticket?: {
          ticketId?: string
        }
      }

      const ticket: SupportTicket = {
        id: payload.ticket?.ticketId ?? `SUP-${Date.now()}`,
        category,
        issue,
        priority,
        status: 'assigned',
        comments: ['Ticket created', 'Assigned to support queue'],
        createdAt: 'Just now',
      }

      addSupportTicket(ticket)

      addActivity({
        title: 'Support ticket created',
        description: `${category} ticket assigned to support team.`,
        tone: 'info',
      })

      setIssue('')
    } finally {
      setLoading(false)
    }
  }

  const supportCategories = [
    {
      name: 'Repayment',
      icon: WalletCards,
    },
    {
      name: 'Mandate',
      icon: ShieldCheck,
    },
    {
      name: 'Disbursement',
      icon: Zap,
    },
    {
      name: 'KYC',
      icon: ScanFace,
    },
  ]

  const faqs = [
    {
      q: 'How do I prepay my loan?',
      a: 'You can initiate full or partial foreclosure directly from the repayment dashboard.',
    },
    {
      q: 'What happens if EMI fails?',
      a: 'The system retries auto-debit after 3 to 5 days depending on bank response.',
    },
    {
      q: 'Can I change my bank mandate?',
      a: 'Yes. Register a new eMandate and the previous mandate will be deactivated automatically.',
    },
  ]

  return (
    <div className="relative mx-auto max-w-7xl space-y-8 px-4 pb-12 md:px-6">
      <PremiumCard className="overflow-hidden bg-slate-950 p-10 text-white">
        <div className="absolute right-0 top-0 h-[300px] w-[300px] rounded-full bg-sky-500/20 blur-3xl" />

        <div className="relative z-10 max-w-3xl">
          <Badge className="rounded-full border-0 bg-white/10 px-4 py-1 text-sky-200 backdrop-blur-xl">
            24/7 Premium Support
          </Badge>

          <h1 className="mt-6 text-5xl font-semibold tracking-tight">
            How can we help you today?
          </h1>

          <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-400">
            Get instant help from support agents and AI assistants for all loan,
            repayment, KYC, and mandate related queries.
          </p>
        </div>
      </PremiumCard>

      <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-8">
          <PremiumCard className="p-8">
            <SectionLabel>Support Categories</SectionLabel>

            <div className="mt-6 grid grid-cols-2 gap-4">
              {supportCategories.map((cat) => (
                <motion.button
                  whileHover={{ y: -2 }}
                  key={cat.name}
                  onClick={() => setCategory(cat.name)}
                  className={clsx(
                    'rounded-[24px] border p-6 text-left transition-all',
                    category === cat.name
                      ? 'border-sky-500 bg-sky-50'
                      : 'border-slate-100 bg-white hover:border-slate-200',
                  )}
                >
                  <div
                    className={clsx(
                      'inline-flex rounded-2xl p-3',
                      category === cat.name
                        ? 'bg-sky-100 text-sky-700'
                        : 'bg-slate-100 text-slate-700',
                    )}
                  >
                    <cat.icon className="h-5 w-5" />
                  </div>

                  <h4 className="mt-5 text-lg font-semibold text-slate-950">
                    {cat.name}
                  </h4>
                </motion.button>
              ))}
            </div>
          </PremiumCard>

          <PremiumCard className="p-8">
            <SectionLabel>Frequently Asked Questions</SectionLabel>

            <div className="mt-6 space-y-4">
              {faqs.map((faq, index) => (
                <div
                  key={index}
                  className="overflow-hidden rounded-3xl border border-slate-100 bg-white"
                >
                  <button
                    onClick={() =>
                      setOpenFaq(openFaq === index ? -1 : index)
                    }
                    className="flex w-full items-center justify-between p-5 text-left"
                  >
                    <h4 className="pr-4 font-semibold text-slate-950">
                      {faq.q}
                    </h4>

                    <ChevronDown
                      className={clsx(
                        'h-5 w-5 text-slate-400 transition-transform duration-300',
                        openFaq === index && 'rotate-180',
                      )}
                    />
                  </button>

                  <AnimatePresence>
                    {openFaq === index && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden border-t border-slate-100"
                      >
                        <p className="p-5 text-sm leading-7 text-slate-500">
                          {faq.a}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              ))}
            </div>
          </PremiumCard>
        </div>

        <div className="space-y-8">
          <PremiumCard className="p-8">
            <div className="flex items-center justify-between">
              <div>
                <SectionLabel>Create Ticket</SectionLabel>

                <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
                  Raise Support Request
                </h2>
              </div>

              <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700">
                <Clock3 className="h-4 w-4" />
                Avg response: 2 mins
              </div>
            </div>

            <div className="mt-8 space-y-6">
              <Input
                label="Describe your issue"
                value={issue}
                onChange={(e) => setIssue(e.target.value)}
                placeholder="Tell us what's happening..."
                icon={<MessageCircle className="h-5 w-5" />}
                className="h-14 rounded-2xl border-0 bg-slate-100/70"
              />

              <div className="flex flex-wrap gap-3">
                {(['low', 'medium', 'high'] as const).map((item) => (
                  <button
                    key={item}
                    onClick={() => setPriority(item)}
                    className={clsx(
                      'rounded-full px-5 py-3 text-sm font-medium capitalize transition-all',
                      priority === item
                        ? item === 'high'
                          ? 'bg-rose-500 text-white'
                          : 'bg-slate-950 text-white'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                    )}
                  >
                    {item}
                  </button>
                ))}
              </div>

              <Button
                onClick={createTicket}
                isLoading={loading}
                className="h-14 w-full rounded-2xl bg-slate-950 text-base text-white hover:bg-slate-800"
              >
                <Plus className="mr-2 h-5 w-5" />
                Submit Request
              </Button>
            </div>
          </PremiumCard>

          <div className="space-y-4">
            {(state.supportTickets.length
              ? state.supportTickets
              : [
                {
                  id: 'TKT-DEMO-001',
                  category: 'Repayment',
                  issue:
                    'Need clarification on foreclosure charges and NOC timeline.',
                  priority: 'medium' as const,
                  status: 'in_progress' as const,
                  comments: [
                    'Ticket created',
                    'Support agent reviewing loan terms',
                  ],
                  createdAt: '2 hours ago',
                },
              ]
            ).map((ticket, idx) => (
              <motion.div
                key={ticket.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
              >
                <PremiumCard className="p-6">
                  <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                    <div className="flex gap-4">
                      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sky-100 text-sky-700">
                        <Ticket className="h-6 w-6" />
                      </div>

                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <p className="text-xs font-medium uppercase tracking-[0.15em] text-slate-400">
                            {ticket.id}
                          </p>

                          <Badge className="rounded-full border-0 bg-slate-100 text-slate-700">
                            {ticket.priority}
                          </Badge>
                        </div>

                        <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                          {ticket.category}
                        </h3>

                        <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-500">
                          {ticket.issue}
                        </p>
                      </div>
                    </div>

                    <Badge className="rounded-full border-0 bg-amber-100 px-4 py-1 capitalize text-amber-700">
                      {ticket.status.replace('_', ' ')}
                    </Badge>
                  </div>

                  <div className="mt-8 space-y-4 border-l border-slate-200 pl-6">
                    {ticket.comments.map((comment, cIdx) => (
                      <div key={cIdx} className="relative">
                        <div className="absolute -left-[31px] top-2 h-3 w-3 rounded-full bg-sky-500" />

                        <p className="text-sm font-medium text-slate-500">
                          {comment}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-6">
                    <div className="flex items-center gap-2 text-sm text-slate-400">
                      <Clock3 className="h-4 w-4" />
                      {ticket.createdAt}
                    </div>

                    <div className="flex gap-3">
                      {ticket.status !== 'resolved' && (
                        <Button
                          onClick={() =>
                            updateSupportTicket(ticket.id, {
                              status: 'resolved',
                              comments: [
                                ...ticket.comments,
                                'Resolved by user',
                              ],
                            })
                          }
                          className="h-11 rounded-2xl bg-emerald-500 px-5 text-white hover:bg-emerald-600"
                        >
                          <CheckCircle2 className="mr-2 h-4 w-4" />
                          Resolve
                        </Button>
                      )}

                      <Button className="h-11 rounded-2xl bg-slate-100 px-5 text-slate-700 hover:bg-slate-200">
                        <Send className="mr-2 h-4 w-4" />
                        Open Chat
                      </Button>
                    </div>
                  </div>
                </PremiumCard>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}