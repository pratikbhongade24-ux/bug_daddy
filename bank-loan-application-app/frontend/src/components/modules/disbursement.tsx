'use client'

import React, { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, ArrowRight, BadgeCheck, Banknote, CheckCircle2, FileSignature, Landmark, Send, ShieldCheck, Sparkles, Timer, Zap } from 'lucide-react'
import confetti from 'canvas-confetti'
import { apiClient } from '../../../lib/api-client'
import { useLoanApplication } from '../../lib/application-state'
import { Badge, Button, Card } from '../ui'

export function DisbursementModule({ onComplete }: { onComplete: () => void }) {
  const { state, updateDisbursementStatus, addActivity } = useLoanApplication()
  const [accepted, setAccepted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stage, setStage] = useState(state.disbursementStatus === 'completed' ? 4 : 0)

  const release = async () => {
    setLoading(true)
    setError(null)
    try {
      setStage(1)
      await apiClient.validateAccount('XXXX-XXXX-4321', 'HDFC0001234')
      updateDisbursementStatus({ status: 'account_validated' })
      await new Promise((resolve) => window.setTimeout(resolve, 700))
      setStage(2)
      const createResponse = await apiClient.createDisbursement(state.customerId, state.loanAmount, 'HDFC')
      const createPayload = createResponse.payload as { disbursement?: { disbursementId?: string } }
      const disbursementId = createPayload.disbursement?.disbursementId ?? `DISB-${state.customerId}`
      updateDisbursementStatus({ id: disbursementId, status: 'processing' })
      await new Promise((resolve) => window.setTimeout(resolve, 900))
      setStage(3)
      const utr = `UTR${Date.now()}`
      await apiClient.releaseFunds(disbursementId, utr)
      updateDisbursementStatus({ id: disbursementId, status: 'completed', utr })
      addActivity({ title: 'Loan disbursed', description: `Funds released with UTR ${utr}.`, tone: 'success' })
      confetti({ particleCount: 120, spread: 70, origin: { y: 0.55 }, colors: ['#0ea5e9', '#10b981', '#ffffff'] })
      setStage(4)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Disbursement failed.')
      setStage(0)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <AnimatePresence>
        {stage === 4 ? (
          <motion.div key="success" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="overflow-hidden rounded-[32px] bg-gradient-to-br from-emerald-500 to-sky-600 p-10 text-center text-white shadow-2xl">
            <motion.div initial={{ scale: 0, rotate: -120 }} animate={{ scale: 1, rotate: 0 }} className="mx-auto grid h-28 w-28 place-items-center rounded-full bg-white/20 backdrop-blur-xl">
              <Zap className="h-14 w-14" />
            </motion.div>
            <h2 className="mt-8 text-5xl font-black tracking-tight">Funds transferred</h2>
            <p className="mx-auto mt-4 max-w-xl text-lg font-semibold text-white/85">₹{state.loanAmount.toLocaleString('en-IN')} has been credited to the verified HDFC account.</p>
            <div className="mx-auto mt-8 max-w-xl rounded-3xl border border-white/20 bg-white/15 p-5 font-mono text-xl font-black backdrop-blur-xl">{state.utr}</div>
            <Button className="mt-8 bg-white text-emerald-700 hover:bg-white" size="lg" onClick={onComplete}>Open repayment dashboard <ArrowRight className="h-5 w-5" /></Button>
          </motion.div>
        ) : (
          <motion.div key="flow" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <Card glass className="relative overflow-hidden border border-violet-100">
              <div className="absolute right-0 top-0 h-56 w-56 rounded-full bg-violet-200/30 blur-3xl" />
              <span className="loan-eyebrow"><Banknote className="h-4 w-4" /> Loan transfer</span>
              <h2 className="mt-5 text-4xl font-black tracking-tight text-slate-950">Loan approval and disbursement</h2>
              <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">Review the approved amount, confirm the agreement, and track the bank transfer reference.</p>
              <div className="mt-8 rounded-3xl bg-slate-950 p-7 text-white">
                <div className="flex items-center justify-between">
                  <Badge variant="success"><Sparkles className="mr-1 h-3 w-3" /> Approved</Badge>
                  <span className="font-mono text-sm text-white/60">APR {state.interestRate}%</span>
                </div>
                <p className="mt-8 text-sm font-black uppercase tracking-[0.2em] text-sky-300">Approved amount</p>
                <strong className="mt-3 block text-6xl font-black">₹{state.loanAmount.toLocaleString('en-IN')}</strong>
                <div className="mt-8 grid grid-cols-3 gap-3">
                  <div className="rounded-2xl bg-white/10 p-4"><small className="text-white/60">Tenure</small><strong className="block">{state.loanTenure}m</strong></div>
                  <div className="rounded-2xl bg-white/10 p-4"><small className="text-white/60">EMI</small><strong className="block">₹16,733</strong></div>
                  <div className="rounded-2xl bg-white/10 p-4"><small className="text-white/60">Fee</small><strong className="block">1%</strong></div>
                </div>
              </div>
            </Card>

            <Card className="border border-white/70 bg-white/85">
              {error && <div className="mb-5 flex items-start gap-3 rounded-2xl border border-rose-100 bg-rose-50 p-4 text-sm font-bold leading-6 text-rose-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />{error}</div>}
              <div className="space-y-4">
                {[
                  { label: 'Account validation', icon: Landmark },
                  { label: 'Agreement accepted', icon: FileSignature },
                  { label: 'Transfer initiated', icon: Send },
                  { label: 'Bank confirmation', icon: BadgeCheck },
                ].map((item, index) => {
                  const Icon = item.icon
                  const done = stage > index
                  const active = stage === index
                  return (
                    <div key={item.label} className={`flex items-start gap-4 rounded-3xl border p-5 ${done ? 'border-emerald-100 bg-emerald-50' : active ? 'border-sky-200 bg-sky-50' : 'border-slate-100 bg-white'}`}>
                      <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl ${done ? 'bg-emerald-500 text-white' : 'bg-white text-sky-600'}`}>{done ? <CheckCircle2 className="h-6 w-6" /> : <Icon className="h-6 w-6" />}</span>
                      <div className="min-w-0 flex-1"><strong className="block text-slate-950">{item.label}</strong><small className="font-semibold text-slate-500">{done ? 'Completed' : active ? 'In progress' : 'Pending'}</small></div>
                      {active && loading && <Timer className="h-5 w-5 shrink-0 animate-spin text-sky-500" />}
                    </div>
                  )
                })}
              </div>
              <label className="mt-6 flex cursor-pointer items-start gap-4 rounded-3xl border border-slate-200 bg-slate-50 p-5">
                <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} className="mt-1 h-5 w-5 accent-sky-500" />
                <span className="text-sm font-semibold leading-6 text-slate-600"><strong className="text-slate-950">Accept loan agreement.</strong> I agree to KFS, repayment schedule, mandate terms, and disbursement destination.</span>
              </label>
              <Button className="mt-6" fullWidth size="lg" disabled={!accepted} isLoading={loading} onClick={release}><ShieldCheck className="h-5 w-5" /> Accept and transfer funds</Button>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
