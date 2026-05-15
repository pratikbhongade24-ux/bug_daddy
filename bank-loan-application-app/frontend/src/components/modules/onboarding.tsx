'use client'

import React, { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, BriefcaseBusiness, CheckCircle2, FileUp, Home, IndianRupee, Mail, Phone, ShieldCheck, User } from 'lucide-react'
import { apiClient } from '../../../lib/api-client'
import { useLoanApplication, type AddressInfo, type EmploymentInfo, type IncomeInfo, type PersonalInfo } from '../../lib/application-state'
import { Button, Card, Input } from '../ui'

const steps = [
  { label: 'Profile', icon: User },
  { label: 'Employment', icon: BriefcaseBusiness },
  { label: 'Income', icon: IndianRupee },
  { label: 'Address', icon: Home },
  { label: 'Documents', icon: FileUp },
]

const initialPersonal: PersonalInfo = { name: '', email: '', mobile: '', pan: '', aadhaar: '' }
const initialEmployment: EmploymentInfo = { type: 'Salaried', company: '', role: '', experience: '' }
const initialIncome: IncomeInfo = { monthlyIncome: '', existingEmi: '', loanPurpose: 'Business expansion' }
const initialAddress: AddressInfo = { line1: '', city: '', state: '', pincode: '' }

export function OnboardingModule({ onComplete }: { onComplete: () => void }) {
  const { state, updateOnboarding, addActivity } = useLoanApplication()
  const [step, setStep] = useState(0)
  const [personal, setPersonal] = useState<PersonalInfo>(state.personalInfo ?? initialPersonal)
  const [employment, setEmployment] = useState<EmploymentInfo>(state.employmentInfo ?? initialEmployment)
  const [income, setIncome] = useState<IncomeInfo>(state.incomeInfo ?? initialIncome)
  const [address, setAddress] = useState<AddressInfo>(state.addressInfo ?? initialAddress)
  const [documents, setDocuments] = useState<string[]>(state.uploadedDocuments.length ? state.uploadedDocuments : [])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [complete, setComplete] = useState(state.onboardingStatus === 'approved')

  const progress = useMemo(() => Math.round(((step + (complete ? 1 : 0)) / steps.length) * 100), [complete, step])

  const validateStep = () => {
    if (step === 0) {
      if (!personal.name || !/^\S+@\S+\.\S+$/.test(personal.email) || personal.mobile.length < 10 || personal.pan.length < 10 || personal.aadhaar.length < 4) {
        return 'Enter valid profile details, including email, mobile, PAN, and Aadhaar.'
      }
    }
    if (step === 1 && (!employment.company || !employment.role || !employment.experience)) return 'Complete employment details.'
    if (step === 2 && (!income.monthlyIncome || !income.loanPurpose)) return 'Add income and loan purpose.'
    if (step === 3 && (!address.line1 || !address.city || !address.state || address.pincode.length < 6)) return 'Complete your current address.'
    if (step === 4 && documents.length < 2) return 'Upload at least PAN and income proof documents.'
    return null
  }

  const next = () => {
    const validation = validateStep()
    if (validation) {
      setError(validation)
      return
    }
    setError(null)
    setStep((value) => Math.min(value + 1, steps.length - 1))
    updateOnboarding({ personalInfo: personal, employmentInfo: employment, incomeInfo: income, addressInfo: address, documents, status: 'in_progress', progress: Math.round(((step + 1) / steps.length) * 100) })
  }

  const submit = async () => {
    const validation = validateStep()
    if (validation) {
      setError(validation)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const validationResponse = await apiClient.validateCustomerProfile(state.customerId, personal.pan, personal.mobile, personal.email)
      const validationPayload = validationResponse.payload as { validation?: { panPresent?: boolean; mobilePresent?: boolean } }
      if (validationPayload.validation && (!validationPayload.validation.panPresent || !validationPayload.validation.mobilePresent)) {
        throw new Error('Profile validation failed. Please review PAN and mobile number.')
      }
      await apiClient.createLead(state.customerId, personal.pan, { riskBand: 'B', source: 'premium-web' })
      await apiClient.submitOnboarding(state.customerId, documents, { ...personal, ...employment, ...income, ...address })
      updateOnboarding({ personalInfo: personal, employmentInfo: employment, incomeInfo: income, addressInfo: address, documents, status: 'approved', progress: 100 })
      addActivity({ title: 'Onboarding approved', description: 'Applicant profile, income, address, and documents are complete.', tone: 'success' })
      setComplete(true)
      window.setTimeout(onComplete, 1200)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit onboarding.')
    } finally {
      setLoading(false)
    }
  }

  const addDocument = (label: string) => {
    setDocuments((prev) => Array.from(new Set([...prev, label])))
  }
  const ActiveStepIcon = steps[step].icon

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="grid gap-6 lg:grid-cols-[0.72fr_1.28fr]">
        <Card glass className="relative overflow-hidden border border-sky-100">
          <div className="absolute right-0 top-0 h-40 w-40 rounded-full bg-sky-200/30 blur-3xl" />
          <div className="relative">
            <span className="loan-eyebrow"><ShieldCheck className="h-4 w-4" /> Secure profile</span>
            <h2 className="mt-5 text-4xl font-black tracking-tight text-slate-950">Applicant details</h2>
            <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">Provide accurate identity, work, income, address, and document details for secure loan review.</p>
            <div className="mt-8 h-3 overflow-hidden rounded-full bg-slate-100">
              <motion.div className="h-full rounded-full bg-gradient-to-r from-sky-500 to-emerald-500" animate={{ width: `${complete ? 100 : progress}%` }} />
            </div>
            <div className="mt-6 rounded-3xl border border-sky-100 bg-white/70 p-5">
              <div className="flex items-start gap-4">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-sky-50 text-sky-600">
                  {complete ? <CheckCircle2 className="h-6 w-6" /> : <ActiveStepIcon className="h-6 w-6" />}
                </span>
                <div>
                  <strong className="block text-slate-950">{complete ? 'Profile complete' : steps[step].label}</strong>
                  <p className="mt-1 text-sm font-semibold leading-6 text-slate-500">
                    {complete ? 'Your details are ready for the next secure review.' : 'Complete the visible details to continue.'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </Card>

        <Card className="min-h-[620px] border border-white/70 bg-white/85 shadow-2xl shadow-sky-950/5">
          <AnimatePresence mode="wait">
            <motion.div key={complete ? 'complete' : step} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.28 }}>
              {complete ? (
                <div className="grid min-h-[520px] place-items-center text-center">
                  <div>
                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} className="mx-auto grid h-24 w-24 place-items-center rounded-full bg-emerald-100 text-emerald-600">
                      <CheckCircle2 className="h-12 w-12" />
                    </motion.div>
                    <h3 className="mt-6 text-3xl font-black text-slate-950">Onboarding complete</h3>
                    <p className="mx-auto mt-3 max-w-md font-semibold leading-7 text-slate-500">The applicant profile is validated and KYC is now unlocked.</p>
                    <Button className="mt-8" size="lg" onClick={onComplete}>Continue to KYC</Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-7">
                  <div className="border-b border-slate-100 pb-6">
                    <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-600">{steps[step].label}</p>
                    <h3 className="mt-2 text-2xl font-black text-slate-950">{
                      ['Validate applicant profile', 'Employment details', 'Income and loan need', 'Current address', 'Upload documents'][step]
                    }</h3>
                    <p className="mt-2 text-sm font-semibold leading-6 text-slate-500">
                      {[
                        'Enter the borrower identity details exactly as they appear on official records.',
                        'Add the applicant work profile so underwriting can assess stability.',
                        'Capture income and loan intent before cashflow verification.',
                        'Confirm the current residence used for communication and verification.',
                        'Upload the minimum documents required to complete onboarding.',
                      ][step]}
                    </p>
                  </div>

                  {error && <div className="flex items-start gap-3 rounded-2xl border border-rose-100 bg-rose-50 p-4 text-sm font-bold leading-6 text-rose-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />{error}</div>}

                  {step === 0 && (
                    <div className="grid gap-5 md:grid-cols-2">
                      <Input label="Full name" value={personal.name} onChange={(e) => setPersonal({ ...personal, name: e.target.value })} icon={<User className="h-5 w-5" />} floating />
                      <Input label="Email" value={personal.email} onChange={(e) => setPersonal({ ...personal, email: e.target.value })} icon={<Mail className="h-5 w-5" />} floating />
                      <Input label="Mobile" value={personal.mobile} onChange={(e) => setPersonal({ ...personal, mobile: e.target.value })} icon={<Phone className="h-5 w-5" />} inputMode="tel" floating />
                      <Input label="PAN" value={personal.pan} onChange={(e) => setPersonal({ ...personal, pan: e.target.value.toUpperCase() })} maxLength={10} floating />
                      <Input label="Aadhaar masked" value={personal.aadhaar} onChange={(e) => setPersonal({ ...personal, aadhaar: e.target.value })} inputMode="numeric" floating />
                    </div>
                  )}

                  {step === 1 && (
                    <div className="grid gap-5 md:grid-cols-2">
                      {['Salaried', 'Self-employed', 'Business owner'].map((type) => (
                        <button key={type} onClick={() => setEmployment({ ...employment, type })} className={`min-h-16 rounded-2xl border p-4 text-left text-sm font-black leading-snug ${employment.type === type ? 'border-sky-300 bg-sky-50 text-sky-700' : 'border-slate-100 bg-white text-slate-700'}`}>{type}</button>
                      ))}
                      <Input label="Company / business" value={employment.company} onChange={(e) => setEmployment({ ...employment, company: e.target.value })} floating />
                      <Input label="Role" value={employment.role} onChange={(e) => setEmployment({ ...employment, role: e.target.value })} floating />
                      <Input label="Experience" value={employment.experience} onChange={(e) => setEmployment({ ...employment, experience: e.target.value })} floating />
                    </div>
                  )}

                  {step === 2 && (
                    <div className="grid gap-5 md:grid-cols-2">
                      <Input label="Monthly income" value={income.monthlyIncome} onChange={(e) => setIncome({ ...income, monthlyIncome: e.target.value })} inputMode="numeric" floating />
                      <Input label="Existing EMI" value={income.existingEmi} onChange={(e) => setIncome({ ...income, existingEmi: e.target.value })} inputMode="numeric" floating />
                      {['Business expansion', 'Working capital', 'Personal liquidity', 'Equipment purchase'].map((purpose) => (
                        <button key={purpose} onClick={() => setIncome({ ...income, loanPurpose: purpose })} className={`min-h-16 rounded-2xl border p-4 text-left text-sm font-black leading-snug ${income.loanPurpose === purpose ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : 'border-slate-100 bg-white text-slate-700'}`}>{purpose}</button>
                      ))}
                    </div>
                  )}

                  {step === 3 && (
                    <div className="grid gap-5 md:grid-cols-2">
                      <Input label="Address line" value={address.line1} onChange={(e) => setAddress({ ...address, line1: e.target.value })} floating />
                      <Input label="City" value={address.city} onChange={(e) => setAddress({ ...address, city: e.target.value })} floating />
                      <Input label="State" value={address.state} onChange={(e) => setAddress({ ...address, state: e.target.value })} floating />
                      <Input label="Pincode" value={address.pincode} onChange={(e) => setAddress({ ...address, pincode: e.target.value })} inputMode="numeric" floating />
                    </div>
                  )}

                  {step === 4 && (
                    <div className="grid gap-5 md:grid-cols-3">
                      {['PAN card', 'Aadhaar proof', 'Salary slips', 'Bank statement'].map((doc) => (
                        <button key={doc} onClick={() => addDocument(doc)} className={`group min-h-36 rounded-3xl border border-dashed p-4 text-center transition ${documents.includes(doc) ? 'border-emerald-300 bg-emerald-50' : 'border-sky-200 bg-sky-50/60 hover:bg-sky-50'}`}>
                          <FileUp className="mx-auto h-9 w-9 text-sky-500 transition group-hover:-translate-y-1" />
                          <strong className="mt-4 block text-sm font-black text-slate-900">{doc}</strong>
                          <small className="mt-2 block font-semibold text-slate-500">{documents.includes(doc) ? 'Uploaded' : 'Click to upload'}</small>
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-6">
                    <Button variant="ghost" disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}>Back</Button>
                    {step < steps.length - 1 ? <Button onClick={next}>Continue</Button> : <Button onClick={submit} isLoading={loading}>Submit onboarding</Button>}
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </Card>
      </div>
    </div>
  )
}
