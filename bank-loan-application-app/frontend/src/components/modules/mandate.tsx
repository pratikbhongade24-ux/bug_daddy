'use client'

import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { AlertCircle, Building2, CheckCircle2, CreditCard, Landmark, RefreshCw, ShieldCheck, Smartphone, Zap } from 'lucide-react'
import { apiClient } from '../../../lib/api-client'
import { useLoanApplication } from '../../lib/application-state'
import { Badge, Button, Card } from '../ui'

const banks = [
  { code: 'HDFC', name: 'HDFC Bank', success: '98.2%' },
  { code: 'ICICI', name: 'ICICI Bank', success: '97.4%' },
  { code: 'SBI', name: 'State Bank of India', success: '96.8%' },
]

export function MandateSetupModule({ onComplete }: { onComplete: () => void }) {
  const { state, updateMandateStatus, addActivity } = useLoanApplication()
  const [bank, setBank] = useState('HDFC')
  const [method, setMethod] = useState<'netbanking' | 'debitcard' | 'upi'>('netbanking')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stage, setStage] = useState(state.mandateStatus === 'active' ? 3 : 0)

  const setupMandate = async () => {
    setLoading(true)
    setError(null)
    try {
      setStage(1)
      const response = await apiClient.registerMandate(state.customerId, bank, 25000)
      const payload = response.payload as { mandate?: { mandateId?: string } }
      const mandateId = payload.mandate?.mandateId ?? `MANDATE-${state.customerId}`
      updateMandateStatus({ id: mandateId, status: 'registered' })
      await new Promise((resolve) => window.setTimeout(resolve, 900))
      setStage(2)
      await apiClient.validateMandate(mandateId)
      updateMandateStatus({ id: mandateId, status: 'active' })
      addActivity({ title: 'Auto-debit mandate active', description: `${bank} eNACH mandate registered for EMI automation.`, tone: 'success' })
      setStage(3)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set up mandate.')
      setStage(0)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <Card glass className="relative overflow-hidden border border-amber-100">
          <div className="absolute right-0 top-0 h-56 w-56 rounded-full bg-amber-200/30 blur-3xl" />
          <span className="loan-eyebrow"><RefreshCw className="h-4 w-4" /> Autopay setup</span>
          <h2 className="mt-5 text-4xl font-black tracking-tight text-slate-950">Auto-debit mandate</h2>
          <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">Authorize recurring EMI payments from your preferred bank account.</p>
          <div className="mt-8 grid gap-3">
            {['Create mandate', 'Bank authorization', 'NPCI validation', 'Mandate active'].map((label, index) => (
              <div key={label} className={`flex items-start gap-3 rounded-2xl border p-4 ${stage > index ? 'border-emerald-100 bg-emerald-50' : stage === index ? 'border-amber-200 bg-amber-50' : 'border-slate-100 bg-white/70'}`}>
                <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${stage > index ? 'bg-emerald-500 text-white' : 'bg-white text-amber-600'}`}>{stage > index ? <CheckCircle2 className="h-5 w-5" /> : index + 1}</span>
                <strong className="text-sm font-black text-slate-900">{label}</strong>
              </div>
            ))}
          </div>
        </Card>

        <Card className="border border-white/70 bg-white/85">
          {error && <div className="mb-5 flex items-start gap-3 rounded-2xl border border-rose-100 bg-rose-50 p-4 text-sm font-bold leading-6 text-rose-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />{error}</div>}
          {stage === 3 ? (
            <div className="grid min-h-[520px] place-items-center text-center">
              <div>
                <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} className="mx-auto grid h-24 w-24 place-items-center rounded-full bg-emerald-100 text-emerald-600">
                  <CheckCircle2 className="h-12 w-12" />
                </motion.div>
                <h3 className="mt-6 text-3xl font-black text-slate-950">Mandate registered</h3>
                <p className="mx-auto mt-3 max-w-md font-semibold leading-7 text-slate-500">EMI automation is active. Mandate ID {state.mandateId ?? `MANDATE-${state.customerId}`} is ready for disbursement.</p>
                <Button className="mt-8" size="lg" onClick={onComplete}>Proceed to disbursement</Button>
              </div>
            </div>
          ) : (
            <div className="space-y-7">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-600">Bank selection</p>
                <div className="mt-4 grid gap-4 md:grid-cols-3">
                  {banks.map((item) => (
                    <button key={item.code} onClick={() => setBank(item.code)} className={`min-h-40 rounded-3xl border p-5 text-left transition ${bank === item.code ? 'border-sky-300 bg-sky-50 shadow-xl shadow-sky-100/60' : 'border-slate-100 bg-white'}`}>
                      <Building2 className="h-6 w-6 text-sky-600" />
                      <strong className="mt-4 block font-black text-slate-950">{item.name}</strong>
                      <small className="font-bold text-emerald-600">{item.success} success</small>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-600">Authorization method</p>
                <div className="mt-4 grid gap-4 md:grid-cols-3">
                  {[
                    { id: 'netbanking', label: 'Net banking', icon: Smartphone },
                    { id: 'debitcard', label: 'Debit card', icon: CreditCard },
                    { id: 'upi', label: 'UPI autopay', icon: Landmark },
                  ].map((item) => {
                    const Icon = item.icon
                    return (
                      <button key={item.id} onClick={() => setMethod(item.id as typeof method)} className={`min-h-32 rounded-3xl border p-5 text-center transition ${method === item.id ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : 'border-slate-100 bg-white text-slate-700'}`}>
                        <Icon className="mx-auto h-7 w-7" />
                        <strong className="mt-3 block text-sm font-black">{item.label}</strong>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="rounded-3xl border border-amber-100 bg-amber-50 p-5">
                <div className="flex items-start gap-4">
                  <ShieldCheck className="h-6 w-6 shrink-0 text-amber-600" />
                  <div className="min-w-0">
                    <strong className="text-slate-950">No amount is deducted now</strong>
                    <p className="mt-1 text-sm font-semibold leading-6 text-amber-800/80">This authorizes future EMI deductions up to ₹25,000 through secure NPCI rails.</p>
                  </div>
                </div>
              </div>

              <div className="rounded-3xl bg-slate-950 p-6 text-white">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div><p className="text-xs font-black uppercase tracking-[0.2em] text-sky-300">Recurring setup</p><strong className="mt-2 block text-2xl font-black">₹16,733 / month</strong></div>
                  <Badge variant="primary" className="border-white/20 bg-white/10 text-white"><Zap className="mr-1 h-3 w-3" /> EMI auto</Badge>
                </div>
              </div>

              <Button size="lg" fullWidth onClick={setupMandate} isLoading={loading}>Authenticate and register</Button>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
