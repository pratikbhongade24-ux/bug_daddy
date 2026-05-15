'use client'

import React, { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Activity, AlertCircle, ArrowRight, CheckCircle2, FileBarChart, Filter, IndianRupee, Search, ShieldCheck, TrendingDown, TrendingUp, UploadCloud, Zap } from 'lucide-react'
import { apiClient } from '../../../lib/api-client'
import { useLoanApplication, type CashflowSummary, type Transaction } from '../../lib/application-state'
import { Badge, Button, Card, Input, Skeleton } from '../ui'

const sampleTransactions: Transaction[] = [
  { id: 'txn-1', date: '15 May', description: 'Salary credit - Acme Fintech', category: 'Salary', type: 'credit', amount: 145000, risk: 'low' },
  { id: 'txn-2', date: '13 May', description: 'Cloud subscription', category: 'Business', type: 'debit', amount: 6200, risk: 'low' },
  { id: 'txn-3', date: '09 May', description: 'Vendor payout', category: 'Operations', type: 'debit', amount: 28500, risk: 'medium' },
  { id: 'txn-4', date: '02 May', description: 'Client invoice receipt', category: 'Receivable', type: 'credit', amount: 86000, risk: 'low' },
  { id: 'txn-5', date: '29 Apr', description: 'Unusual cash withdrawal', category: 'Cash', type: 'debit', amount: 45000, risk: 'high' },
]

export function BankStatementModule({ onComplete }: { onComplete: () => void }) {
  const { state, updateBankStatement, addActivity } = useLoanApplication()
  const [stage, setStage] = useState<'idle' | 'uploading' | 'parsing' | 'done'>(state.statementUploaded ? 'done' : 'idle')
  const [progress, setProgress] = useState(state.statementUploaded ? 100 : 0)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | 'credit' | 'debit' | 'risk'>('all')

  const cashflow: CashflowSummary = state.cashflow ?? {
    avgMonthlyCredit: 231000,
    avgMonthlyDebit: 126000,
    avgMonthlyBalance: 92500,
    stability: 'Strong',
    score: 785,
  }
  const transactions = state.transactions.length ? state.transactions : sampleTransactions

  const filteredTransactions = useMemo(() => {
    return transactions.filter((transaction) => {
      const matchesQuery = transaction.description.toLowerCase().includes(query.toLowerCase()) || transaction.category.toLowerCase().includes(query.toLowerCase())
      const matchesFilter = filter === 'all' || transaction.type === filter || (filter === 'risk' && transaction.risk === 'high')
      return matchesQuery && matchesFilter
    })
  }, [filter, query, transactions])

  const handleUpload = async () => {
    setError(null)
    setStage('uploading')
    setProgress(18)
    const customerId = state.customerId
    try {
      await apiClient.uploadStatement(new File(['mock'], 'HDFC_Statement_Last6Months.pdf'), customerId)
      setProgress(48)
      setStage('parsing')
      await apiClient.extractTransactions(`STM-${customerId}`)
      setProgress(74)
      const summaryResponse = await apiClient.summarizeCashflow(`STM-${customerId}`)
      await apiClient.detectAnomalies(`STM-${customerId}`)
      const summaryPayload = summaryResponse.payload as { cashflowSummary?: Partial<CashflowSummary> }
      const mergedCashflow = { ...cashflow, ...summaryPayload.cashflowSummary }
      setProgress(100)
      updateBankStatement({
        documents: ['HDFC_Statement_Last6Months.pdf'],
        transactions: sampleTransactions,
        cashflow: mergedCashflow,
      })
      addActivity({ title: 'Cashflow analyzed', description: 'Statement parsing, anomaly detection, and summaries completed.', tone: 'success' })
      setStage('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to analyze statement.')
      setStage('idle')
      setProgress(0)
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <Card glass className="relative overflow-hidden border border-emerald-100">
          <div className="absolute right-0 top-0 h-52 w-52 rounded-full bg-emerald-200/30 blur-3xl" />
          <div className="relative">
            <span className="loan-eyebrow"><FileBarChart className="h-4 w-4" /> Income review</span>
            <h2 className="mt-5 text-4xl font-black tracking-tight text-slate-950">Bank statement upload</h2>
            <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">Upload statements to securely review income, balances, and transaction patterns.</p>
          </div>

          <div className="mt-8 rounded-3xl border-2 border-dashed border-emerald-200 bg-emerald-50/70 p-8 text-center">
            <motion.div animate={stage === 'parsing' ? { rotateY: 360 } : { y: [0, -6, 0] }} transition={{ duration: stage === 'parsing' ? 1.5 : 3, repeat: Infinity }} className="mx-auto grid h-24 w-24 place-items-center rounded-3xl bg-white text-emerald-600 shadow-xl">
              {stage === 'done' ? <CheckCircle2 className="h-12 w-12" /> : <UploadCloud className="h-12 w-12" />}
            </motion.div>
            <h3 className="mt-5 text-2xl font-black text-slate-950">{stage === 'done' ? 'Statement analyzed' : stage === 'parsing' ? 'Parsing transactions' : stage === 'uploading' ? 'Uploading securely' : 'Drop statement here'}</h3>
            <p className="mx-auto mt-2 max-w-md text-sm font-semibold leading-6 text-slate-500">PDF statements are encrypted, parsed locally through the bank statement service, and converted into explainable signals.</p>
            <div className="mt-6 h-3 overflow-hidden rounded-full bg-white">
              <motion.div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-sky-500" animate={{ width: `${progress}%` }} />
            </div>
            <Button className="mt-6" size="lg" onClick={handleUpload} disabled={stage === 'uploading' || stage === 'parsing'} isLoading={stage === 'uploading' || stage === 'parsing'}>
              {stage === 'done' ? 'Re-run analysis' : 'Upload statement'}
            </Button>
          </div>

          {error && <div className="mt-5 flex items-start gap-3 rounded-2xl border border-rose-100 bg-rose-50 p-4 text-sm font-bold leading-6 text-rose-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />{error}</div>}
        </Card>

        <div className="grid gap-5 md:grid-cols-2">
          <Card hover glass className="border border-sky-100">
            <TrendingUp className="h-6 w-6 text-emerald-500" />
            <p className="mt-4 text-sm font-bold text-slate-500">Average monthly credit</p>
            <strong className="mt-2 block text-4xl font-black text-slate-950">₹{cashflow.avgMonthlyCredit.toLocaleString('en-IN')}</strong>
            <span className="mt-3 inline-flex rounded-full bg-emerald-50 px-3 py-1 text-xs font-black text-emerald-700">+18% income consistency</span>
          </Card>
          <Card hover glass className="border border-sky-100">
            <IndianRupee className="h-6 w-6 text-sky-500" />
            <p className="mt-4 text-sm font-bold text-slate-500">Average balance</p>
            <strong className="mt-2 block text-4xl font-black text-slate-950">₹{cashflow.avgMonthlyBalance.toLocaleString('en-IN')}</strong>
            <span className="mt-3 inline-flex rounded-full bg-sky-50 px-3 py-1 text-xs font-black text-sky-700">{cashflow.stability} stability</span>
          </Card>
          <Card className="md:col-span-2 border border-white/70">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-600">Cashflow chart</p>
                <h3 className="mt-1 text-xl font-black text-slate-950">Six month financial pulse</h3>
              </div>
              <Badge variant="success">Score {cashflow.score}</Badge>
            </div>
            <div className="mt-8 flex h-52 items-end gap-3 rounded-3xl bg-slate-50 p-5">
              {[42, 68, 55, 86, 74, 95].map((height, index) => (
                <motion.div key={index} className="flex-1 rounded-t-2xl bg-gradient-to-t from-sky-500 to-emerald-400" initial={{ height: 0 }} animate={{ height: `${height}%` }} transition={{ delay: index * 0.08 }} />
              ))}
            </div>
          </Card>
        </div>
      </div>

      <AnimatePresence>
        {(stage === 'uploading' || stage === 'parsing') && (
          <motion.div className="grid gap-4 md:grid-cols-3" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_0.6fr]">
        <Card className="border border-white/70">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-600">Transaction explorer</p>
              <h3 className="mt-1 text-2xl font-black text-slate-950">Parsed ledger</h3>
            </div>
            <div className="grid w-full gap-3 sm:grid-cols-[minmax(0,1fr)_auto] md:w-auto">
              <Input placeholder="Search transactions" value={query} onChange={(e) => setQuery(e.target.value)} icon={<Search className="h-4 w-4" />} className="h-11" />
              <button onClick={() => setFilter(filter === 'all' ? 'risk' : 'all')} className="inline-flex h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-black text-slate-600"><Filter className="h-4 w-4" />{filter === 'all' ? 'All' : 'Risk'}</button>
            </div>
          </div>
          <div className="mt-6 space-y-3">
            {filteredTransactions.map((transaction) => (
              <motion.div key={transaction.id} layout className="grid gap-3 rounded-2xl border border-slate-100 bg-white p-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center">
                <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${transaction.type === 'credit' ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                  {transaction.type === 'credit' ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />}
                </span>
                <div className="min-w-0 flex-1">
                  <strong className="block truncate text-sm font-black text-slate-900">{transaction.description}</strong>
                  <small className="font-semibold text-slate-500">{transaction.date} • {transaction.category}</small>
                </div>
                <div className="flex flex-wrap items-center gap-3 sm:justify-end">
                  <Badge variant={transaction.risk === 'high' ? 'warning' : 'neutral'}>{transaction.risk ?? 'low'} risk</Badge>
                  <strong className={transaction.type === 'credit' ? 'text-emerald-600' : 'text-slate-900'}>{transaction.type === 'credit' ? '+' : '-'}₹{transaction.amount.toLocaleString('en-IN')}</strong>
                </div>
              </motion.div>
            ))}
          </div>
        </Card>

        <Card className="border border-white/70">
          <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-600">Anomaly detection</p>
          <div className="mt-5 space-y-4">
            <div className="rounded-2xl bg-emerald-50 p-4"><Activity className="h-5 w-5 text-emerald-600" /><strong className="mt-3 block text-slate-950">Salary cadence stable</strong><p className="mt-1 text-sm font-semibold text-slate-500">Recurring credits detected monthly.</p></div>
            <div className="rounded-2xl bg-amber-50 p-4"><Zap className="h-5 w-5 text-amber-600" /><strong className="mt-3 block text-slate-950">One unusual withdrawal</strong><p className="mt-1 text-sm font-semibold text-slate-500">Flagged but not blocking approval.</p></div>
            <div className="rounded-2xl bg-sky-50 p-4"><ShieldCheck className="h-5 w-5 text-sky-600" /><strong className="mt-3 block text-slate-950">Fraud checks clear</strong><p className="mt-1 text-sm font-semibold text-slate-500">No duplicate or tampered pages.</p></div>
          </div>
          <Button className="mt-6 w-full" size="lg" onClick={onComplete} disabled={!state.statementUploaded}>Proceed to mandate <ArrowRight className="h-5 w-5" /></Button>
        </Card>
      </div>
    </div>
  )
}
