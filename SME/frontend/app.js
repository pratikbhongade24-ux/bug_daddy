const endpoints = {
  onboarding: "http://localhost:8001",
  kyc: "http://localhost:8002",
  loan: "http://localhost:8003",
  repayment: "http://localhost:8004"
};

const state = {
  customerId: null,
  kycId: null,
  loanId: null,
  completed: []
};

const stages = [
  { key: "customer", title: "Customer Onboarding" },
  { key: "kycUpload", title: "KYC Upload" },
  { key: "kycVerify", title: "KYC Verification" },
  { key: "loan", title: "Loan Creation" },
  { key: "disbursement", title: "Approval & Disbursement" },
  { key: "emi", title: "EMI Generation" }
];

const healthGrid = document.getElementById("healthGrid");
const kpiGrid = document.getElementById("kpiGrid");
const pipelineEl = document.getElementById("pipeline");
const progressBar = document.getElementById("progressBar");
const progressText = document.getElementById("progressText");
const activityFeed = document.getElementById("activityFeed");
const loader = document.getElementById("actionLoader");

function setLoading(on) {
  loader.classList.toggle("hidden", !on);
}

function logEvent(title, payload) {
  const row = document.createElement("div");
  row.className = "log-item";
  const timestamp = new Date().toLocaleTimeString();
  row.innerHTML = `<span class="log-time">${timestamp}</span><strong>${title}</strong><br>${JSON.stringify(payload)}`;
  activityFeed.prepend(row);
}

async function api(url, options = {}) {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt);
  }
  return res.json();
}

function markDone(key) {
  if (!state.completed.includes(key)) state.completed.push(key);
  renderPipeline();
}

function renderPipeline() {
  const current = stages.find((s) => !state.completed.includes(s.key));
  pipelineEl.innerHTML = stages
    .map((s, idx) => {
      const done = state.completed.includes(s.key);
      const css = done ? "done" : current?.key === s.key ? "current" : "";
      const label = done ? "Complete" : current?.key === s.key ? "In Progress" : "Pending";
      return `<div class="stage ${css}"><span>${idx + 1}. ${s.title}</span><strong>${label}</strong></div>`;
    })
    .join("");

  const percent = Math.round((state.completed.length / stages.length) * 100);
  progressBar.style.width = `${percent}%`;
  progressText.textContent = `${percent}% completed`;
}

async function healthCheck() {
  const services = [
    ["Onboarding", `${endpoints.onboarding}/health`],
    ["KYC", `${endpoints.kyc}/health`],
    ["Loan", `${endpoints.loan}/health`],
    ["Repayment", `${endpoints.repayment}/health`]
  ];

  const results = await Promise.all(
    services.map(async ([name, url]) => {
      try {
        await api(url);
        return { name, up: true };
      } catch {
        return { name, up: false };
      }
    })
  );

  healthGrid.innerHTML = results
    .map((r) => `<article class="health"><h4>${r.name}</h4><p>${r.up ? "Connected" : "Unavailable"}</p><span class="service-badge ${r.up ? "service-up" : "service-down"}">${r.up ? "Healthy" : "Down"}</span></article>`)
    .join("");
}

async function refreshMetrics() {
  const [customers, kyc, loans, emis] = await Promise.all([
    api(`${endpoints.onboarding}/customers`),
    api(`${endpoints.kyc}/kyc`),
    api(`${endpoints.loan}/loans`),
    api(`${endpoints.repayment}/emis`)
  ]);

  const overdue = emis.filter((e) => e.payment_status === "OVERDUE").length;
  const disbursed = loans.filter((l) => l.status === "DISBURSED").length;

  const kpis = [
    ["Total Customers", customers.length],
    ["KYC Records", kyc.length],
    ["Disbursed Loans", disbursed],
    ["EMI Schedules", emis.length],
    ["Overdue EMIs", overdue],
    ["Pipeline Completion", `${Math.round((state.completed.length / stages.length) * 100)}%`]
  ];

  kpiGrid.innerHTML = kpis.map(([k, v]) => `<article class="kpi"><h4>${k}</h4><p>${v}</p></article>`).join("");
}

async function createCustomer() {
  const payload = {
    full_name: "Riya Sharma",
    email: `riya.${Date.now()}@mail.com`,
    phone: `${Math.floor(7000000000 + Math.random() * 1999999999)}`,
    dob: "1995-02-11",
    employment_type: "SALARIED",
    annual_income: 950000,
    credit_score: 742
  };
  const data = await api(`${endpoints.onboarding}/customers`, { method: "POST", body: JSON.stringify(payload) });
  state.customerId = data.id;
  markDone("customer");
  logEvent("Customer created", data);
}

async function uploadKyc() {
  const data = await api(`${endpoints.kyc}/kyc`, {
    method: "POST",
    body: JSON.stringify({
      customer_id: state.customerId,
      document_type: "PAN",
      document_number: `ABCDE${Math.floor(Math.random() * 9000) + 1000}F`,
      document_url: "https://example.com/pan.pdf"
    })
  });
  state.kycId = data.id;
  markDone("kycUpload");
  logEvent("KYC uploaded", data);
}

async function reviewKyc() {
  const data = await api(`${endpoints.kyc}/kyc/${state.kycId}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "VERIFIED", reviewer_notes: "Documents valid" })
  });
  markDone("kycVerify");
  logEvent("KYC verified", data);
}

async function createLoan() {
  const data = await api(`${endpoints.loan}/loans`, {
    method: "POST",
    body: JSON.stringify({ customer_id: state.customerId, loan_type: "PERSONAL", requested_amount: 600000, tenure_months: 24 })
  });
  state.loanId = data.id;
  markDone("loan");
  logEvent("Loan created", data);
}

async function approveDisburse() {
  await api(`${endpoints.loan}/loans/${state.loanId}/approve`, {
    method: "PATCH",
    body: JSON.stringify({ approved_amount: 550000, interest_rate: 11.25, sanction_notes: "Approved by risk policy" })
  });
  const data = await api(`${endpoints.loan}/loans/${state.loanId}/disburse`, {
    method: "POST",
    body: JSON.stringify({ disbursed_amount: 550000, mode: "NEFT" })
  });
  markDone("disbursement");
  logEvent("Loan disbursed", data);
}

async function generateEmi() {
  const gen = await api(`${endpoints.repayment}/emis/generate`, {
    method: "POST",
    body: JSON.stringify({ loan_id: state.loanId })
  });
  markDone("emi");
  logEvent("EMI schedule generated", gen);
}

const actions = { createCustomer, uploadKyc, reviewKyc, createLoan, approveDisburse, generateEmi };

async function runAction(action) {
  setLoading(true);
  try {
    if ((action === "uploadKyc" || action === "createLoan") && !state.customerId) throw new Error("Create customer first");
    if (action === "reviewKyc" && !state.kycId) throw new Error("Upload KYC first");
    if ((action === "approveDisburse" || action === "generateEmi") && !state.loanId) throw new Error("Create loan first");

    await actions[action]();
    await refreshMetrics();
  } catch (e) {
    logEvent("Action failed", { action, error: e.message });
  } finally {
    setLoading(false);
  }
}

async function runFullJourney() {
  for (const action of ["createCustomer", "uploadKyc", "reviewKyc", "createLoan", "approveDisburse", "generateEmi"]) {
    await runAction(action);
  }
}

document.querySelectorAll("[data-action]").forEach((b) => b.addEventListener("click", () => runAction(b.dataset.action)));
document.getElementById("refreshBtn").addEventListener("click", async () => {
  await healthCheck();
  await refreshMetrics();
  logEvent("Dashboard refresh", { status: "completed" });
});
document.getElementById("runJourneyBtn").addEventListener("click", runFullJourney);

(async function boot() {
  renderPipeline();
  await healthCheck();
  await refreshMetrics();
  logEvent("Platform initialized", { mode: "QA sandbox" });
})();
