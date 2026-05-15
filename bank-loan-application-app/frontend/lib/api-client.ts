/**
 * Central API Client for all Lambda microservices
 * Provides typed access to all backend operations
 */

type ServicePayload = Record<string, unknown>

interface ServiceResponse<T = ServicePayload> {
  service: string
  requestId: string
  operation: string
  timestamp: string
  payload: T
  requestTraceId?: string
  db?: {
    host: string
    port: string
    name: string
    user: string
  }
  [key: string]: unknown
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || ''

class APIClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl
  }

  private async invokeService<T>(
    service: string,
    operation: string,
    payload: ServicePayload
  ): Promise<ServiceResponse<T>> {
    try {
      const url = `${this.baseUrl}/api/${service.toLowerCase()}`
      
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          requestId: operation,
          ...payload,
        }),
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`)
      }

      const data = await response.json()
      return data as ServiceResponse<T>
    } catch (error) {
      console.error(`Service call failed: ${service}.${operation}`, error)
      throw error
    }
  }

  // === Customer Onboarding Service ===
  async validateCustomerProfile(customerId: string, pan: string, mobile: string, email: string) {
    return this.invokeService('CustomerOnboardingService', 'validateCustomerProfile', {
      customerId,
      pan,
      mobile,
      email,
      name: `Customer-${customerId}`,
      riskBand: 'B',
      source: 'web',
    })
  }

  async createLead(customerId: string, pan: string, riskData?: ServicePayload) {
    return this.invokeService('CustomerOnboardingService', 'createLead', {
      customerId,
      pan,
      ...riskData,
    })
  }

  async submitOnboarding(
    customerId: string,
    documents: string[],
    profileData: ServicePayload
  ) {
    return this.invokeService('CustomerOnboardingService', 'submitOnboarding', {
      customerId,
      documents,
      ...profileData,
    })
  }

  async getOnboardingStatus(customerId: string) {
    return this.invokeService('CustomerOnboardingService', 'getOnboardingStatus', {
      customerId,
    })
  }

  // === KYC Service ===
  async verifyPan(customerId: string, pan: string) {
    return this.invokeService('KYCService', 'verifyPan', {
      customerId,
      pan,
    })
  }

  async verifyAadhaar(customerId: string, aadhaarMasked: string) {
    return this.invokeService('KYCService', 'verifyAadhaar', {
      customerId,
      aadhaarMasked,
    })
  }

  async runFaceMatch(customerId: string, selfieImage: string) {
    return this.invokeService('KYCService', 'runFaceMatch', {
      customerId,
      selfieImage,
    })
  }

  async getKycStatus(customerId: string) {
    return this.invokeService('KYCService', 'getKycStatus', {
      customerId,
    })
  }

  // === Bank Statement Service ===
  async uploadStatement(statementFile: File, customerId: string) {
    return this.invokeService('BankStatementService', 'uploadStatement', {
      statementId: `STM-${customerId}`,
      customerId,
      fileName: statementFile.name,
      pages: 3,
    })
  }

  async extractTransactions(statementId: string) {
    return this.invokeService('BankStatementService', 'extractTransactions', {
      statementId,
    })
  }

  async summarizeCashflow(statementId: string) {
    return this.invokeService('BankStatementService', 'summarizeCashflow', {
      statementId,
      pages: 3,
    })
  }

  async detectAnomalies(statementId: string) {
    return this.invokeService('BankStatementService', 'detectAnomalies', {
      statementId,
    })
  }

  // === Auto Debit Service ===
  async registerMandate(customerId: string, bankCode: string, amount: number) {
    return this.invokeService('AutoDebitService', 'registerMandate', {
      mandateId: `MANDATE-${customerId}`,
      customerId,
      bankCode,
      amount,
    })
  }

  async validateMandate(mandateId: string) {
    return this.invokeService('AutoDebitService', 'validateMandate', {
      mandateId,
    })
  }

  async executeDebit(mandateId: string, transactionId: string, amount: number) {
    return this.invokeService('AutoDebitService', 'executeDebit', {
      mandateId,
      transactionId,
      amount,
    })
  }

  async getMandateStatus(mandateId: string) {
    return this.invokeService('AutoDebitService', 'getMandateStatus', {
      mandateId,
    })
  }

  // === Disbursement Service ===
  async createDisbursement(customerId: string, loanAmount: number, destinationBank: string) {
    return this.invokeService('DisbursementService', 'createDisbursement', {
      disbursementId: `DISB-${customerId}`,
      customerId,
      amount: loanAmount,
      destinationBank,
    })
  }

  async validateAccount(accountNumberMasked: string, ifsc: string) {
    return this.invokeService('DisbursementService', 'validateAccount', {
      accountNumberMasked,
      ifsc,
    })
  }

  async releaseFunds(disbursementId: string, utr: string) {
    return this.invokeService('DisbursementService', 'releaseFunds', {
      disbursementId,
      utr,
    })
  }

  async getDisbursementStatus(disbursementId: string) {
    return this.invokeService('DisbursementService', 'getDisbursementStatus', {
      disbursementId,
    })
  }

  // === Support Service ===
  async createTicket(customerId: string, issue: string, priority: string = 'medium') {
    return this.invokeService('SupportService', 'createTicket', {
      ticketId: `SUP-${customerId}`,
      customerId,
      issue,
      priority,
      assignedQueue: 'loan-ops',
    })
  }

  async assignTicket(ticketId: string, queue: string) {
    return this.invokeService('SupportService', 'assignTicket', {
      ticketId,
      assignedQueue: queue,
    })
  }

  async updateTicket(ticketId: string, status: string, comments: string[]) {
    return this.invokeService('SupportService', 'updateTicket', {
      ticketId,
      status,
      comments,
    })
  }

  async getTicketStatus(ticketId: string) {
    return this.invokeService('SupportService', 'getTicketStatus', {
      ticketId,
    })
  }
}

export const apiClient = new APIClient()
export type { ServiceResponse }
