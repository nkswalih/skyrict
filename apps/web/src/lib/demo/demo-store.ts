"use client";

export const DEMO_STORAGE_KEY = "skyrict:demo:v3";

/**
 * Deterministic timestamp for the seed snapshot. The server and the first
 * client render must produce byte-identical HTML, so the seed can never call
 * `new Date()` at module scope.
 */
const SEED_UPDATED_AT = "2026-10-25T00:00:00.000Z";
const DEMO_STORAGE_EVENT = "skyrict:demo-storage-changed";

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

export interface DemoProfile {
  fullName: string;
  email: string;
  jobTitle: string;
  department: string;
  phone: string;
  timezone: string;
  location: string;
  pronouns: string;
  bio: string;
  memberSince: string;
}

export interface DemoWorkspacePreferences {
  name: string;
  slug: string;
  industry: string;
  fiscalYearStart: string;
  currency: string;
  timezone: string;
  locale: string;
  dateFormat: string;
  weekStart: "monday" | "sunday";
  aiAssist: boolean;
}

export interface DemoNotificationPreference {
  id: string;
  label: string;
  description: string;
  inApp: boolean;
  email: boolean;
  push: boolean;
  /** Security rows cannot be muted in-app. */
  locked?: boolean;
}

export interface DemoNotificationPreferences {
  categories: DemoNotificationPreference[];
  digestFrequency: "realtime" | "hourly" | "daily";
  quietHoursEnabled: boolean;
  quietHoursStart: string;
  quietHoursEnd: string;
}

export interface DemoIntegration {
  id: string;
  name: string;
  category: "Finance" | "CRM" | "Communication" | "Data" | "AI";
  description: string;
  logo: string;
  logoWidth: number;
  logoHeight: number;
  logoInvertOnDark?: boolean;
  connected: boolean;
  lastSync: string;
}

export interface DemoPasskey {
  id: string;
  name: string;
  addedAt: string;
  lastUsed: string;
}

export interface DemoSecuritySession {
  id: string;
  device: string;
  browser: string;
  location: string;
  lastActive: string;
  current: boolean;
}

export interface DemoSecurity {
  twoFactorEnabled: boolean;
  loginAlerts: boolean;
  passkeys: DemoPasskey[];
  sessions: DemoSecuritySession[];
}

export interface DemoAppearance {
  theme: "light" | "dark" | "system";
  density: "comfortable" | "compact";
  reduceMotion: boolean;
}

export interface DemoPreferences {
  workspace: DemoWorkspacePreferences;
  notifications: DemoNotificationPreferences;
  appearance: DemoAppearance;
}

export interface DemoState {
  version: 3;
  profile: DemoProfile;
  preferences: DemoPreferences;
  integrations: DemoIntegration[];
  security: DemoSecurity;
  notificationsReadIds: string[];
  notificationsSnoozedIds: string[];
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
  profile: {
    fullName: "Priya Sharma",
    email: "priya@skyrict.demo",
    jobTitle: "VP of Operations",
    department: "Executive",
    phone: "+91 98450 22118",
    timezone: "Asia/Kolkata",
    location: "Bengaluru, India",
    pronouns: "She / Her",
    bio: "Runs global operations across 12 distribution hubs. Obsessed with shortening the gap between a signed order and a stocked shelf — and with giving every team the same number to argue about.",
    memberSince: "2024-02-01",
  },
  preferences: {
    workspace: {
      name: "Skyrict Industrial Group",
      slug: "skyrict-industrial",
      industry: "Industrial Manufacturing",
      fiscalYearStart: "April",
      currency: "INR (₹)",
      timezone: "Asia/Kolkata",
      locale: "en-IN",
      dateFormat: "DD MMM YYYY",
      weekStart: "monday",
      aiAssist: true,
    },
    notifications: {
      categories: [
        {
          id: "deals",
          label: "Deal movement",
          description: "Stage changes, wins, and stalled opportunities.",
          inApp: true,
          email: true,
          push: true,
        },
        {
          id: "inventory",
          label: "Inventory risk",
          description: "Stock-outs, reorder thresholds, and warehouse anomalies.",
          inApp: true,
          email: true,
          push: true,
        },
        {
          id: "finance",
          label: "Finance & approvals",
          description: "Credit holds, overdue invoices, and journal approvals.",
          inApp: true,
          email: true,
          push: false,
        },
        {
          id: "people",
          label: "People operations",
          description: "Leave requests, onboarding tasks, and roster changes.",
          inApp: true,
          email: false,
          push: false,
        },
        {
          id: "payroll",
          label: "Payroll & compliance",
          description: "Run readiness, statutory filings, and payout confirmations.",
          inApp: true,
          email: true,
          push: false,
        },
        {
          id: "system",
          label: "Platform & security",
          description: "New sign-ins, permission changes, and service health.",
          inApp: true,
          email: true,
          push: true,
          locked: true,
        },
      ],
      digestFrequency: "daily",
      quietHoursEnabled: true,
      quietHoursStart: "19:00",
      quietHoursEnd: "08:00",
    },
    appearance: {
      theme: "light",
      density: "comfortable",
      reduceMotion: false,
    },
  },
  integrations: [
    {
      id: "tally",
      name: "Tally Prime",
      category: "Finance",
      description: "Two-way ledger sync for statutory books and GST filings.",
      logo: "/integrations/tally.svg",
      logoWidth: 235,
      logoHeight: 105,
      logoInvertOnDark: true,
      connected: true,
      lastSync: "4 min ago",
    },
    {
      id: "razorpay",
      name: "Razorpay",
      category: "Finance",
      description: "Collect customer payments and reconcile settlements automatically.",
      logo: "/integrations/razorpay.svg",
      logoWidth: 24,
      logoHeight: 24,
      logoInvertOnDark: true,
      connected: true,
      lastSync: "12 min ago",
    },
    {
      id: "zoho",
      name: "Zoho CRM",
      category: "CRM",
      description: "Mirror leads and deal stages between Zoho and Skyrict CRM.",
      logo: "/integrations/zoho.svg",
      logoWidth: 1024,
      logoHeight: 450,
      logoInvertOnDark: true,
      connected: false,
      lastSync: "Never",
    },
    {
      id: "slack",
      name: "Slack",
      category: "Communication",
      description: "Route approvals and stock alerts into the right channel.",
      logo: "/integrations/slack.svg",
      logoWidth: 127,
      logoHeight: 127,
      connected: true,
      lastSync: "1 min ago",
    },
    {
      id: "google",
      name: "Google Workspace",
      category: "Communication",
      description: "Single sign-on, shared calendars, and document hand-off.",
      logo: "/integrations/google.svg",
      logoWidth: 24,
      logoHeight: 24,
      connected: true,
      lastSync: "6 min ago",
    },
    {
      id: "whatsapp",
      name: "WhatsApp Business",
      category: "Communication",
      description: "Send order updates and payment reminders to customers.",
      logo: "/integrations/whatsapp.svg",
      logoWidth: 512,
      logoHeight: 512,
      connected: true,
      lastSync: "22 min ago",
    },
    {
      id: "snowflake",
      name: "Snowflake",
      category: "Data",
      description: "Nightly warehouse export for BI and board reporting.",
      logo: "/integrations/snowflake.svg",
      logoWidth: 24,
      logoHeight: 24,
      connected: false,
      lastSync: "Never",
    },
    {
      id: "skyagent",
      name: "SkyAgent",
      category: "AI",
      description: "Autonomous reconciliation, anomaly scans, and forecasting.",
      logo: "/integrations/skyagent.svg",
      logoWidth: 32,
      logoHeight: 32,
      connected: true,
      lastSync: "Live",
    },
  ],
  security: {
    twoFactorEnabled: true,
    loginAlerts: true,
    passkeys: [
      {
        id: "pk-1",
        name: "MacBook Pro · Touch ID",
        addedAt: "2026-02-14",
        lastUsed: "2 minutes ago",
      },
      {
        id: "pk-2",
        name: "iPhone 15 Pro · Face ID",
        addedAt: "2026-06-03",
        lastUsed: "Yesterday",
      },
    ],
    sessions: [
      {
        id: "sess-current",
        device: "MacBook Pro 16″",
        browser: "Chrome 141 · macOS",
        location: "Bengaluru, India",
        lastActive: "Active now",
        current: true,
      },
      {
        id: "sess-windows",
        device: "Surface Laptop 7",
        browser: "Edge 141 · Windows 11",
        location: "Mumbai, India",
        lastActive: "2 hours ago",
        current: false,
      },
      {
        id: "sess-mobile",
        device: "iPhone 15 Pro",
        browser: "Safari · iOS 18",
        location: "Bengaluru, India",
        lastActive: "Yesterday",
        current: false,
      },
    ],
  },
  notificationsReadIds: ["ntf-3", "ntf-5"],
  notificationsSnoozedIds: [],
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
  updatedAt: SEED_UPDATED_AT,
};

/** Fresh copy of the seed; safe to mutate without touching the module constant. */
export function createDemoSeedState(): DemoState {
  return structuredClone(SEED_DATA);
}

function mergeRecord<T extends object>(seed: T, stored: unknown): T {
  if (!stored || typeof stored !== "object" || Array.isArray(stored)) return seed;
  return { ...seed, ...(stored as Partial<T>) };
}

/** Keep newly shipped integrations visible even for older v3 snapshots. */
function mergeIntegrations(
  seed: DemoIntegration[],
  stored: unknown,
): DemoIntegration[] {
  if (!Array.isArray(stored)) return seed;
  return seed.map((integration) => {
    const saved = stored.find(
      (candidate) =>
        candidate &&
        typeof candidate === "object" &&
        (candidate as { id?: string }).id === integration.id,
    );
    return saved ? { ...integration, ...saved } : integration;
  });
}

function mergePreferences(stored: unknown): DemoPreferences {
  const seed = createDemoSeedState().preferences;
  const parsed =
    stored && typeof stored === "object"
      ? (stored as Partial<DemoPreferences>)
      : {};
  const notifications =
    parsed.notifications && typeof parsed.notifications === "object"
      ? (parsed.notifications as Partial<DemoNotificationPreferences>)
      : {};

  return {
    workspace: mergeRecord(seed.workspace, parsed.workspace),
    notifications: {
      ...seed.notifications,
      ...notifications,
      categories:
        Array.isArray(notifications.categories) &&
        notifications.categories.length > 0
          ? notifications.categories
          : seed.notifications.categories,
    },
    appearance: mergeRecord(seed.appearance, parsed.appearance),
  };
}

function mergeSecurity(stored: unknown): DemoSecurity {
  const seed = createDemoSeedState().security;
  const parsed =
    stored && typeof stored === "object"
      ? (stored as Partial<DemoSecurity>)
      : {};
  return {
    ...seed,
    ...parsed,
    passkeys: Array.isArray(parsed.passkeys)
      ? parsed.passkeys
      : seed.passkeys,
    sessions: Array.isArray(parsed.sessions)
      ? parsed.sessions
      : seed.sessions,
  };
}

/**
 * Read the visitor's demo snapshot. Pure: never writes to storage, so it is safe
 * to call during render (e.g. in an event handler / update callback).
 */
export function getDemoState(): DemoState {
  if (typeof window === "undefined") return createDemoSeedState();
  try {
    const raw = window.localStorage.getItem(DEMO_STORAGE_KEY);
    if (!raw) return createDemoSeedState();
    const parsed = JSON.parse(raw) as Partial<DemoState> | null;
    if (!parsed || parsed.version !== 3) return createDemoSeedState();
    const seed = createDemoSeedState();
    // Defensive merge: always provide fallback arrays/objects to avoid crashes
    // when a stored v3 snapshot predates a newly added slice.
    return {
      ...seed,
      ...parsed,
      profile: mergeRecord(seed.profile, parsed.profile),
      preferences: mergePreferences(parsed.preferences),
      integrations: mergeIntegrations(seed.integrations, parsed.integrations),
      security: mergeSecurity(parsed.security),
      notificationsReadIds: Array.isArray(parsed.notificationsReadIds)
        ? parsed.notificationsReadIds
        : seed.notificationsReadIds,
      notificationsSnoozedIds: Array.isArray(parsed.notificationsSnoozedIds)
        ? parsed.notificationsSnoozedIds
        : seed.notificationsSnoozedIds,
      leads: Array.isArray(parsed.leads) ? parsed.leads : seed.leads,
      opportunities: Array.isArray(parsed.opportunities) ? parsed.opportunities : seed.opportunities,
      customers: Array.isArray(parsed.customers) ? parsed.customers : seed.customers,
      orders: Array.isArray(parsed.orders) ? parsed.orders : seed.orders,
      products: Array.isArray(parsed.products) ? parsed.products : seed.products,
      employees: Array.isArray(parsed.employees) ? parsed.employees : seed.employees,
      journalEntries: Array.isArray(parsed.journalEntries) ? parsed.journalEntries : seed.journalEntries,
      invoices: Array.isArray(parsed.invoices) ? parsed.invoices : seed.invoices,
    };
  } catch {
    return createDemoSeedState();
  }
}

/** Seed storage once, on mount. Never call from render. */
export function ensureDemoStorage(): void {
  if (typeof window === "undefined") return;
  try {
    if (!window.localStorage.getItem(DEMO_STORAGE_KEY)) {
      window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(createDemoSeedState()));
    }
  } catch {
    // Quota / private-mode fallback: the in-memory seed still works.
  }
}

/**
 * Persist a snapshot and return the stamped copy that was written. Never
 * mutates the caller's object (the old implementation stamped `updatedAt` on
 * the React state object).
 */
export function setDemoState(state: DemoState): DemoState {
  const next: DemoState = { ...state, updatedAt: new Date().toISOString() };
  if (typeof window === "undefined") return next;
  try {
    window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(new Event(DEMO_STORAGE_EVENT));
  } catch {
    // Quota fallback: keep the in-memory state in the provider.
  }
  return next;
}

export function resetDemoState(): DemoState {
  const fresh = createDemoSeedState();
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(fresh));
      window.dispatchEvent(new Event(DEMO_STORAGE_EVENT));
    } catch {
      // Quota fallback.
    }
  }
  return fresh;
}

/**
 * Subscribe to same-tab writes (custom event) and other-tab writes (`storage`).
 * Returns an unsubscribe function.
 */
export function subscribeDemoState(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onCustom = () => listener();
  const onStorage = (event: StorageEvent) => {
    if (event.key === DEMO_STORAGE_KEY) listener();
  };
  window.addEventListener(DEMO_STORAGE_EVENT, onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(DEMO_STORAGE_EVENT, onCustom);
    window.removeEventListener("storage", onStorage);
  };
}
