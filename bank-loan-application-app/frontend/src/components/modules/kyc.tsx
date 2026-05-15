'use client'

import React, { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, Camera, CheckCircle2, CreditCard, Fingerprint, ScanFace, ShieldCheck, UploadCloud } from 'lucide-react'
import { apiClient } from '../../../lib/api-client'
import { useLoanApplication } from '../../lib/application-state'
import { Badge, Button, Card } from '../ui'

type KycStep = 'pan' | 'aadhaar' | 'selfie'

const checks: Array<{ id: KycStep; title: string; subtitle: string; icon: typeof CreditCard }> = [
  { id: 'pan', title: 'PAN verification', subtitle: 'Validate tax identity and name match', icon: CreditCard },
  { id: 'aadhaar', title: 'Aadhaar eKYC', subtitle: 'Secure OTP-style identity verification', icon: Fingerprint },
  { id: 'selfie', title: 'Selfie and face match', subtitle: 'Match live image with identity record', icon: Camera },
]

export function KYCModule({ onComplete }: { onComplete: () => void }) {
  const { state, updateKycStatus, addActivity } = useLoanApplication()
  const [verified, setVerified] = useState<Record<KycStep, boolean>>({
    pan: ['pan_verified', 'aadhaar_verified', 'approved'].includes(state.kycStatus),
    aadhaar: ['aadhaar_verified', 'approved'].includes(state.kycStatus),
    selfie: state.kycStatus === 'approved',
  })
  const [loading, setLoading] = useState<KycStep | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selfieReady, setSelfieReady] = useState(false)

  const activeIndex = checks.findIndex((check) => !verified[check.id])
  const progress = Math.round((Object.values(verified).filter(Boolean).length / checks.length) * 100)

  const verify = async (type: KycStep) => {
    setError(null)
    setLoading(type)
    try {
      if (type === 'pan') {
        const response = await apiClient.verifyPan(state.customerId, state.personalInfo?.pan ?? '')
        const payload = response.payload as { verification?: { status?: string } }
        if (payload.verification?.status !== 'VERIFIED') throw new Error('PAN verification failed.')
        setVerified((prev) => ({ ...prev, pan: true }))
        updateKycStatus({ status: 'pan_verified', progress: 33 })
      }
      if (type === 'aadhaar') {
        const response = await apiClient.verifyAadhaar(state.customerId, state.personalInfo?.aadhaar ?? '')
        const payload = response.payload as { verification?: { status?: string } }
        if (payload.verification?.status !== 'VERIFIED') throw new Error('Aadhaar verification failed.')
        setVerified((prev) => ({ ...prev, aadhaar: true }))
        updateKycStatus({ status: 'aadhaar_verified', progress: 66 })
      }
      if (type === 'selfie') {
        const response = await apiClient.runFaceMatch(state.customerId, 'mock_base64_selfie')
        const payload = response.payload as { faceMatch?: { result?: string } }
        if (payload.faceMatch?.result !== 'MATCHED') throw new Error('Face match failed.')
        setVerified((prev) => ({ ...prev, selfie: true }))
        updateKycStatus({ status: 'approved', progress: 100 })
        addActivity({ title: 'KYC approved', description: 'PAN, Aadhaar, and face match verification completed.', tone: 'success' })
        window.setTimeout(onComplete, 1200)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to verify ${type}.`)
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <Card glass className="relative overflow-hidden border border-sky-100">
          <div className="absolute right-0 top-0 h-56 w-56 rounded-full bg-indigo-200/30 blur-3xl" />
          <span className="loan-eyebrow"><ShieldCheck className="h-4 w-4" /> Identity security</span>
          <h2 className="mt-5 text-4xl font-black tracking-tight text-slate-950">KYC verification</h2>
          <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">Verify identity details using secure PAN, Aadhaar, and face match checks.</p>
          <div className="mt-8 rounded-3xl bg-slate-950 p-6 text-white">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-300">Verified applicant</p>
                <strong className="mt-2 block text-2xl font-black">{state.personalInfo?.name || 'Applicant'}</strong>
              </div>
              <Badge variant={progress === 100 ? 'success' : 'info'}>{progress}% complete</Badge>
            </div>
            <div className="mt-6 h-3 overflow-hidden rounded-full bg-white/10">
              <motion.div className="h-full rounded-full bg-gradient-to-r from-sky-400 to-emerald-400" animate={{ width: `${progress}%` }} />
            </div>
            <div className="mt-6 grid grid-cols-3 gap-3 text-center">
              {checks.map((check) => (
                <div key={check.id} className="rounded-2xl bg-white/10 p-3">
                  <strong className="block text-lg font-black">{verified[check.id] ? 'OK' : '--'}</strong>
                  <small className="text-xs font-semibold text-white/60">{check.title.split(' ')[0]}</small>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card className="border border-white/70 bg-white/85">
          {error && <div className="mb-5 flex items-start gap-3 rounded-2xl border border-rose-100 bg-rose-50 p-4 text-sm font-bold leading-6 text-rose-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />{error}</div>}
          <div className="space-y-4">
            {checks.map((check, index) => {
              const Icon = check.icon
              const done = verified[check.id]
              const enabled = done || index === activeIndex
              return (
                <motion.div key={check.id} animate={enabled && !done ? { scale: [1, 1.012, 1] } : {}} transition={{ duration: 2, repeat: Infinity }} className={`relative overflow-hidden rounded-3xl border p-5 ${done ? 'border-emerald-200 bg-emerald-50/70' : enabled ? 'border-sky-200 bg-sky-50/70 shadow-xl shadow-sky-100/60' : 'border-slate-100 bg-slate-50 opacity-60'}`}>
                  <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
                    <div className="flex min-w-0 items-start gap-4">
                      <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl ${done ? 'bg-emerald-500 text-white' : 'bg-white text-sky-600'}`}>
                        {done ? <CheckCircle2 className="h-7 w-7" /> : <Icon className="h-7 w-7" />}
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-lg font-black text-slate-950">{check.title}</h3>
                        <p className="text-sm font-semibold text-slate-500">{check.subtitle}</p>
                      </div>
                    </div>
                    <div className="shrink-0 xl:self-center">
                      {done ? <Badge variant="success">Verified</Badge> : <Button disabled={!enabled || loading !== null || (check.id === 'selfie' && !selfieReady)} isLoading={loading === check.id} onClick={() => verify(check.id)}>{check.id === 'aadhaar' ? 'Verify OTP' : check.id === 'selfie' ? 'Run face match' : 'Verify PAN'}</Button>}
                    </div>
                  </div>
                  {loading === check.id && <motion.div className="absolute bottom-0 left-0 h-1 bg-sky-500" initial={{ width: 0 }} animate={{ width: '100%' }} transition={{ duration: 1.4, repeat: Infinity }} />}
                </motion.div>
              )
            })}
          </div>

          <div className="mt-6 rounded-3xl border border-dashed border-indigo-200 bg-indigo-50/70 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-start gap-4">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white text-indigo-600"><ScanFace className="h-6 w-6" /></span>
                <div className="min-w-0">
                  <strong className="block text-slate-950">Selfie upload preview</strong>
                  <small className="font-semibold text-slate-500">Upload a clear selfie for secure face matching.</small>
                </div>
              </div>
              <Button variant="outline" onClick={() => setSelfieReady(true)}><UploadCloud className="h-4 w-4" /> Upload selfie</Button>
            </div>
            <AnimatePresence>
              {selfieReady && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-4 rounded-2xl bg-white p-4">
                  <div className="relative mx-auto grid h-40 max-w-xs place-items-center overflow-hidden rounded-3xl bg-gradient-to-br from-sky-100 to-indigo-100">
                    <ScanFace className="h-16 w-16 text-indigo-500" />
                    <motion.span className="absolute left-0 right-0 h-1 bg-indigo-500/70" animate={{ y: [-70, 70, -70] }} transition={{ duration: 2, repeat: Infinity }} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </Card>
      </div>
    </div>
  )
}
