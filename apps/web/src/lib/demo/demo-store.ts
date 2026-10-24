"use client";

export const DEMO_STORAGE_KEY = "skyrict:demo:v3";

export interface DemoLead {
  id: string;
  name: string;
  company: string;
  email: string;
  phone: string;
  source: string;
  status: "new" | "contacted" | "qualified" | "disqualified";
  createdAt: string;
}

export interface DemoOpportunity {
  id: string;
  name: string;
  amount: number;
  currency: string;
  stage: "prospecting" | "qualified" | "proposal" | "negotiation" | "won" | "lost";
  probability: number;
  expectedCloseDate: string;
}

export interface DemoCustomer {
  id: string;
  name: string;
  customerCode: string;
  email: string;
  phone: string;
  creditLimit: number;
  currency: string;
  isActive: boolean;
  createdAt: string;
}

export interface DemoOrder {
  id: string;
  orderNumber: string;
  customerName: string;
  status: "draft" | "confirmed" | "fulfilled" | "cancelled";
  creditCheck: "passed" | "pending" | "failed";
  total: number;
  currency: string;
  createdAt: string;
}

export interface DemoProduct {
  id: string;
  sku: string;
  name: string;
  category: string;
  costPrice: number;
  sellPrice: number;
  reorderPoint: number;
  qtyOnHand: number;
  warehouse: string;
  isActive: boolean;
}

export interface DemoEmployee {
  id: string;
  employeeNumber: string;
  firstName: string;
  lastName: string;
  jobTitle: string;
  department: string;
  employmentStatus: "active" | "on_leave" | "terminated";
  monthlySalary: number;
  currency: string;
  hireDate: string;
}

export interface DemoJournalEntry {
  id: string;
  entryNumber: string;
  description: string;
  date: string;
  debitAccount: string;
  creditAccount: string;
  amount: number;
  status: "posted" | "draft";
}

export interface DemoInvoice {
  id: string;
  invoiceNumber: string;
  customerName: string;
  amount: number;
  dueDate: string;
  status: "paid" | "issued" | "overdue";
}

export interface DemoState {
  version: 3;
  leads: DemoLead[];
  opportunities: DemoOpportunity[];
  customers: DemoCustomer[];
  orders: DemoOrder[];
  products: DemoProduct[];
  employees: DemoEmployee[];
  journalEntries: DemoJournalEntry[];
  invoices: DemoInvoice[];
  updatedAt: string;
}

const SEED_DATA: DemoState = {
  version: 3,
  leads: [
    { id: "lead-1", name: "Aarav Sharma", company: "Sharma Logistics Ltd", email: "aarav@sharma.demo", phone: "+91 98765 43210", source: "Website", status: "new", createdAt: "2026-10-18" },
    { id: "lead-2", name: "Pooja Hegde", company: "Deccan Infra Group", email: "pooja@deccan.demo", phone: "+91 98220 11223", source: "Referral", status: "contacted", createdAt: "2026-10-19" },
    { id: "lead-3", name: "Vikram Malhotra", company: "Horizon Retailers", email: "vikram@horizon.demo", phone: "+91 94450 88990", source: "LinkedIn", status: "qualified", createdAt: "2026-10-21" },
    { id: "lead-4", name: "Ananya Iyer", company: "Southern Textiles", email: "ananya@southern.demo", phone: "+91 97780 44556", source: "Trade Show", status: "disqualified", createdAt: "2026-10-14" },
  ],
  opportunities: [
    { id: "opp-1", name: "Supply Chain Modernization", amount: 1450000, currency: "INR", stage: "proposal", probability: 65, expectedCloseDate: "2026-11-15" },
    { id: "opp-2", name: "Regional ERP Enterprise License", amount: 3800000, currency: "INR", stage: "negotiation", probability: 80, expectedCloseDate: "2026-11-05" },
    { id: "opp-3", name: "Warehouse IoT Integration", amount: 920000, currency: "INR", stage: "qualified", probability: 40, expectedCloseDate: "2026-12-01" },
    { id: "opp-4", name: "Procurement Automated Audit", amount: 550000, currency: "INR", stage: "won", probability: 100, expectedCloseDate: "2026-10-10" },
    { id: "opp-5", name: "Raw Material Logistics Contract", amount: 720000, currency: "INR", stage: "prospecting", probability: 25, expectedCloseDate: "2026-12-20" },
  ],
  customers: [
    { id: "cust-1", name: "Vastraline Industries Ltd", customerCode: "CUST-001", email: "procurement@vastraline.demo", phone: "+91 22 4567 8900", creditLimit: 5000000, currency: "INR", isActive: true, createdAt: "2026-01-10" },
    { id: "cust-2", name: "Apex Distribution Hub", customerCode: "CUST-002", email: "billing@apex-dist.demo", phone: "+91 22 2345 6789", creditLimit: 10000000, currency: "INR", isActive: true, createdAt: "2026-03-14" },
    { id: "cust-3", name: "Global TransLogix", customerCode: "CUST-003", email: "accounts@translogix.demo", phone: "+91 20 8901 2345", creditLimit: 7500000, currency: "INR", isActive: true, createdAt: "2026-05-22" },
  ],
  orders: [
    { id: "ord-1", orderNumber: "SO-2026-089", customerName: "Vastraline Industries Ltd", status: "confirmed", creditCheck: "passed", total: 425000, currency: "INR", createdAt: "2026-10-20" },
    { id: "ord-2", orderNumber: "SO-2026-090", customerName: "Apex Distribution Hub", status: "fulfilled", creditCheck: "passed", total: 1180000, currency: "INR", createdAt: "2026-10-18" },
    { id: "ord-3", orderNumber: "SO-2026-091", customerName: "Global TransLogix", status: "draft", creditCheck: "pending", total: 290000, currency: "INR", createdAt: "2026-10-23" },
    { id: "ord-4", orderNumber: "SO-2026-092", customerName: "Vastraline Industries Ltd", status: "draft", creditCheck: "pending", total: 185000, currency: "INR", createdAt: "2026-10-24" },
  ],
  products: [
    { id: "prod-1", sku: "IND-SKU-1001", name: "Heavy Duty Conveyor Belt", category: "Machinery", costPrice: 45000, sellPrice: 62000, reorderPoint: 5, qtyOnHand: 18, warehouse: "Central DC", isActive: true },
    { id: "prod-2", sku: "IND-SKU-1002", name: "Industrial Servo Motor 15kW", category: "Electrical", costPrice: 28000, sellPrice: 39500, reorderPoint: 8, qtyOnHand: 4, warehouse: "East Warehouse", isActive: true },
    { id: "prod-3", sku: "IND-SKU-1003", name: "Pneumatic Control Valve 2-inch", category: "Pneumatics", costPrice: 4200, sellPrice: 6800, reorderPoint: 20, qtyOnHand: 0, warehouse: "Central DC", isActive: true },
    { id: "prod-4", sku: "IND-SKU-1004", name: "Cast Iron Flange Bearings", category: "Hardware", costPrice: 1200, sellPrice: 1950, reorderPoint: 50, qtyOnHand: 142, warehouse: "West Hub", isActive: true },
  ],
  employees: [
    { id: "emp-1", employeeNumber: "EMP-001", firstName: "Priya", lastName: "Sharma", jobTitle: "VP of Operations", department: "Executive", employmentStatus: "active", monthlySalary: 285000, currency: "INR", hireDate: "2024-02-01" },
    { id: "emp-2", employeeNumber: "EMP-002", firstName: "Arjun", lastName: "Patel", jobTitle: "Chief Accountant", department: "Finance", employmentStatus: "active", monthlySalary: 165000, currency: "INR", hireDate: "2024-05-15" },
    { id: "emp-3", employeeNumber: "EMP-003", firstName: "Sneha", lastName: "Reddy", jobTitle: "Warehouse Supervisor", department: "Inventory", employmentStatus: "active", monthlySalary: 95000, currency: "INR", hireDate: "2025-01-10" },
    { id: "emp-4", employeeNumber: "EMP-004", firstName: "Rohan", lastName: "Mehta", jobTitle: "Lead Account Executive", department: "Sales", employmentStatus: "active", monthlySalary: 125000, currency: "INR", hireDate: "2025-03-20" },
  ],
  journalEntries: [
    { id: "je-1", entryNumber: "JE-2026-104", description: "Accrued Payroll Liability - Oct 2026", date: "2026-10-24", debitAccount: "5010 Salaries Expense", creditAccount: "2010 Payroll Payable", amount: 670000, status: "posted" },
    { id: "je-2", entryNumber: "JE-2026-103", description: "Inventory COGS Recognition", date: "2026-10-22", debitAccount: "5000 Cost of Goods Sold", creditAccount: "1300 Inventory Asset", amount: 485000, status: "posted" },
    { id: "je-3", entryNumber: "JE-2026-102", description: "Customer Receipt - Apex Distribution", date: "2026-10-20", debitAccount: "1100 Operating Cash", creditAccount: "1200 Accounts Receivable", amount: 1180000, status: "posted" },
  ],
  invoices: [
    { id: "inv-1", invoiceNumber: "INV-2026-044", customerName: "Vastraline Industries Ltd", amount: 425000, dueDate: "2026-11-15", status: "issued" },
    { id: "inv-2", invoiceNumber: "INV-2026-043", customerName: "Apex Distribution Hub", amount: 1180000, dueDate: "2026-10-20", status: "paid" },
    { id: "inv-3", invoiceNumber: "INV-2026-042", customerName: "Global TransLogix", amount: 340000, dueDate: "2026-10-10", status: "overdue" },
  ],
  updatedAt: new Date().toISOString(),
};

export function getDemoState(): DemoState {
  if (typeof window === "undefined") return SEED_DATA;
  try {
    const raw = window.localStorage.getItem(DEMO_STORAGE_KEY);
    if (!raw) {
      window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(SEED_DATA));
      return SEED_DATA;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.version !== 3) {
      window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(SEED_DATA));
      return SEED_DATA;
    }
    // Defensive merge: always provide fallback arrays to avoid .filter crashes
    return {
      ...SEED_DATA,
      ...parsed,
      leads: Array.isArray(parsed.leads) ? parsed.leads : SEED_DATA.leads,
      opportunities: Array.isArray(parsed.opportunities) ? parsed.opportunities : SEED_DATA.opportunities,
      customers: Array.isArray(parsed.customers) ? parsed.customers : SEED_DATA.customers,
      orders: Array.isArray(parsed.orders) ? parsed.orders : SEED_DATA.orders,
      products: Array.isArray(parsed.products) ? parsed.products : SEED_DATA.products,
      employees: Array.isArray(parsed.employees) ? parsed.employees : SEED_DATA.employees,
      journalEntries: Array.isArray(parsed.journalEntries) ? parsed.journalEntries : SEED_DATA.journalEntries,
      invoices: Array.isArray(parsed.invoices) ? parsed.invoices : SEED_DATA.invoices,
    };
  } catch {
    return SEED_DATA;
  }
}

export function setDemoState(state: DemoState): void {
  if (typeof window === "undefined") return;
  try {
    state.updatedAt = new Date().toISOString();
    window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(state));
    window.dispatchEvent(new Event("skyrict:demo-storage-changed"));
  } catch {
    // Quota fallback
  }
}

export function resetDemoState(): DemoState {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(SEED_DATA));
    window.dispatchEvent(new Event("skyrict:demo-storage-changed"));
  }
  return SEED_DATA;
}