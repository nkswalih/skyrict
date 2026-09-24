/**
 * Documentation content for the public /docs tree.
 *
 * Every guide lives here as plain data so the whole documentation set can be
 * statically prerendered (no authentication, no API calls at read time), and
 * the same data powers the full-text search index. Keep this module free of
 * server-only imports: the search page imports it from a client component.
 */

export interface DocSection {
    /** Anchor id used by "On this page" links, e.g. "open-the-pulse". */
    id: string;
    title: string;
    paragraphs?: string[];
    bullets?: string[];
    steps?: string[];
    note?: string;
}

export interface DocRelated {
    categoryId: string;
    slug: string;
}

export interface DocArticle {
    categoryId: string;
    slug: string;
    title: string;
    description: string;
    popular?: boolean;
    /** Shows the inline "Create a Skyrict account" callout above the body. */
    cta?: boolean;
    sections: DocSection[];
    related?: DocRelated[];
}

export interface DocCategory {
    id: string;
    name: string;
    description: string;
}

export interface DocsNavLink {
    category: DocCategory;
    href: string;
    title: string;
}

export const docCategories: DocCategory[] = [
    {
        id: "getting-started",
        name: "Getting started",
        description: "From first account to first signal in one sitting.",
    },
    {
        id: "operations",
        name: "Operations",
        description: "Run stock, orders, and cash on live numbers.",
    },
    {
        id: "intelligence",
        name: "Intelligence",
        description: "Live signals from the market, read continuously.",
    },
    {
        id: "agents",
        name: "Agents",
        description: "Reasoning across operations and the market at once.",
    },
    {
        id: "security",
        name: "Security & administration",
        description: "Hard defaults, verifiable in code.",
    },
];

export const docArticles: DocArticle[] = [
    {
        categoryId: "getting-started",
        slug: "create-account",
        title: "Create your account",
        description:
            "Email verification, MFA, and a workspace in seven guided steps.",
        popular: true,
        cta: true,
        sections: [
            {
                id: "what-this-guide-covers",
                title: "What this guide covers",
                paragraphs: [
                    "This guide walks through the full signup flow: creating an account, verifying your email, setting up multi-factor authentication, and landing in your first workspace.",
                ],
            },
            {
                id: "create-your-account",
                title: "Create your account",
                steps: [
                    "Open the signup page from the marketing site, the signup subdomain, or an invite link.",
                    "Enter your name, work email, and a strong password.",
                    "Complete email verification using the link sent to your inbox.",
                ],
            },
            {
                id: "set-up-mfa",
                title: "Set up multi-factor authentication",
                paragraphs: [
                    "Skyrict uses TOTP authenticator codes for MFA. The guided step adds your account to an authenticator app and issues one-time backup codes. Store the backup codes offline before you continue.",
                ],
                note: "You can finish MFA later from workspace settings, but the guided step keeps you safe from the start.",
            },
            {
                id: "your-first-workspace",
                title: "Your first workspace",
                paragraphs: [
                    "Signup creates a private workspace for you. From there you can add team members, connect your operations, and read your first pulse.",
                ],
            },
        ],
        related: [
            { categoryId: "getting-started", slug: "connect-operations" },
            { categoryId: "security", slug: "multi-factor-authentication" },
        ],
    },
    {
        categoryId: "getting-started",
        slug: "connect-operations",
        title: "Connect your operations",
        description:
            "Inventory, sales, cash, and orders read from the live source of truth.",
        popular: true,
        cta: true,
        sections: [
            {
                id: "what-you-connect",
                title: "What you connect",
                paragraphs: [
                    "Skyrict reads from the live source of truth of your business: products and stock, sales, cash, and open orders. There is no data warehouse and no one-time migration project.",
                ],
            },
            {
                id: "start-with-inventory",
                title: "Start with inventory",
                steps: [
                    "Open Inventory from the ERP section of your workspace.",
                    "Add the products you sell, with their units and reorder points.",
                    "Add warehouse locations and settle starting stock levels.",
                    "Add suppliers so future suggestions can name the source.",
                ],
            },
            {
                id: "sales-cash-orders",
                title: "Sales, cash, and orders",
                paragraphs: [
                    "As orders come in, Skyrict tracks them against your stock and the cash they represent. Sales velocity and unfulfilled value update continuously from the numbers your team already uses.",
                ],
            },
            {
                id: "confirm-the-pulse",
                title: "Confirm the pulse",
                paragraphs: [
                    "The daily pulse starts reporting as soon as data flows. Watch points, stock anomalies, and near-reorder items appear without further setup.",
                ],
                note: "Skyrict reads your operations; it does not replace your systems of record. Keep the source updated and the platform follows.",
            },
        ],
        related: [
            { categoryId: "getting-started", slug: "read-your-first-pulse" },
            { categoryId: "operations", slug: "inventory" },
        ],
    },
    {
        categoryId: "getting-started",
        slug: "read-your-first-pulse",
        title: "Read your first pulse",
        description:
            "The daily operating picture: what is true inside your business today.",
        popular: true,
        cta: true,
        sections: [
            {
                id: "what-a-pulse-is",
                title: "What a pulse is",
                paragraphs: [
                    "The pulse is the daily operating picture. It summarizes what is true inside your business today: stock positions, orders, cash, and the few things that need your attention.",
                ],
            },
            {
                id: "open-the-pulse",
                title: "Open the pulse",
                steps: [
                    "Open your workspace home.",
                    "Review the watch points that Skyrict generated from your numbers.",
                    "Refresh the pulse to pull the latest state from your sources.",
                ],
            },
            {
                id: "source-labels",
                title: "Source labels",
                paragraphs: [
                    "Each figure carries a source label. Live means the number was read from your source at generation time. Cached means it comes from the last successful read. No new activity means nothing changed since the last read.",
                ],
            },
            {
                id: "daily-use",
                title: "Daily use",
                paragraphs: [
                    "Most days you read the pulse once and skim what changed. The market signals page adds the outside picture, and Guardian keeps watching in the background.",
                ],
            },
        ],
        related: [
            { categoryId: "intelligence", slug: "market-signals" },
            { categoryId: "agents", slug: "guardian" },
        ],
    },
    {
        categoryId: "operations",
        slug: "inventory",
        title: "Inventory",
        description: "Stock, movements, warehouses, suppliers, and low-stock alerts.",
        sections: [
            {
                id: "what-inventory-covers",
                title: "What Inventory covers",
                paragraphs: [
                    "Inventory is the operating core of the ERP. It holds your products, their units and prices, stock across warehouses, movements in and out, and the suppliers you buy from.",
                ],
            },
            {
                id: "stock-and-reorder",
                title: "Stock and reorder points",
                paragraphs: [
                    "Each product carries a current stock level and a reorder point. When live stock falls to the reorder point, the product appears in low-stock alerts and agent suggestions.",
                ],
            },
            {
                id: "movements",
                title: "Movements",
                paragraphs: [
                    "Every inbound, outbound, and adjustment is recorded as a movement. You can trace how a product reached its current level and spot patterns like overstocking or repeated shorts.",
                ],
            },
            {
                id: "abc-and-anomalies",
                title: "ABC analysis and anomalies",
                paragraphs: [
                    "Skyrict classifies products by value contribution (ABC) and flags units whose behavior deviates from their history: coverage gaps, unusual velocity, or anomaly signals that warrant a closer look.",
                ],
            },
            {
                id: "keep-it-current",
                title: "Keep it current",
                note: "Inventory mirrors your real operations. Correct stock after any physical count so suggestions and coverage stay trustworthy.",
            },
        ],
        related: [
            { categoryId: "operations", slug: "orders" },
            { categoryId: "getting-started", slug: "read-your-first-pulse" },
        ],
    },
    {
        categoryId: "operations",
        slug: "orders",
        title: "Orders",
        description: "Open orders, fulfillment, and the cash they represent.",
        sections: [
            {
                id: "what-orders-shows",
                title: "What Orders shows",
                paragraphs: [
                    "Orders tracks the pipeline between a customer decision and fulfilled value: open orders, fulfillment status, and the cash represented by each order.",
                ],
            },
            {
                id: "open-orders",
                title: "Open orders",
                paragraphs: [
                    "An open order is one that has not been fully fulfilled. The list shows its total value, what remains unfulfilled, and how long it has been open.",
                ],
            },
            {
                id: "fulfillment-status",
                title: "Fulfillment status",
                paragraphs: [
                    "Each order carries a status that moves from open toward fulfilled as the work is done. Orders that stall are visible at a glance so you can act before they age.",
                ],
            },
            {
                id: "cash-position",
                title: "Cash position",
                paragraphs: [
                    "The cash represented by orders is tracked separately from sales so you can see committed revenue that has not yet arrived.",
                ],
            },
        ],
        related: [
            { categoryId: "operations", slug: "sales" },
            { categoryId: "operations", slug: "inventory" },
        ],
    },
    {
        categoryId: "operations",
        slug: "sales",
        title: "Sales",
        description: "Revenue, unfulfilled value, and velocity at a glance.",
        sections: [
            {
                id: "what-sales-shows",
                title: "What Sales shows",
                paragraphs: [
                    "Sales is the revenue picture of your operations: what you have sold, the value still waiting to be fulfilled, and how fast it is moving.",
                ],
            },
            {
                id: "velocity",
                title: "Velocity",
                paragraphs: [
                    "Velocity measures how quickly sales turn over. Slowing velocity on a product is often the first signal of a demand shift that the market pages can explain.",
                ],
            },
            {
                id: "unfulfilled-value",
                title: "Unfulfilled value",
                paragraphs: [
                    "Unfulfilled value is the amount of committed sales not yet delivered. Keeping it low means your inventory and orders are in step with demand.",
                ],
            },
        ],
        related: [
            { categoryId: "operations", slug: "orders" },
            { categoryId: "operations", slug: "reports" },
        ],
    },
    {
        categoryId: "operations",
        slug: "reports",
        title: "Reports",
        description: "Period analysis across the ERP, narrowed by date range.",
        sections: [
            {
                id: "what-reports-covers",
                title: "What Reports covers",
                paragraphs: [
                    "Reports aggregates the ERP across a period you choose: revenue, order behavior, inventory movement, and the ratios that tie them together.",
                ],
            },
            {
                id: "choose-a-range",
                title: "Choose a range",
                steps: [
                    "Open Reports from the ERP section.",
                    "Pick a date range, from a single day to a full quarter.",
                    "Read the period totals and the comparison against the previous period.",
                ],
            },
            {
                id: "use-the-analysis",
                title: "Use the analysis",
                paragraphs: [
                    "Reports are read views. Use them for reviews and planning, and keep the live pulse for day-to-day operations.",
                ],
            },
        ],
        related: [
            { categoryId: "operations", slug: "sales" },
            { categoryId: "operations", slug: "inventory" },
        ],
    },
    {
        categoryId: "operations",
        slug: "approvals",
        title: "Approvals",
        description: "Review-only routing for the actions that need a human.",
        sections: [
            {
                id: "what-approvals-is-for",
                title: "What Approvals is for",
                paragraphs: [
                    "Approvals routes high-impact actions through a human review before anything changes. It is review-only: nothing is executed until a person approves it.",
                ],
            },
            {
                id: "how-routing-works",
                title: "How routing works",
                paragraphs: [
                    "When an agent or a process proposes an action that needs consent, it appears here with the reasoning attached. The reviewer sees what would change and why before deciding.",
                ],
            },
            {
                id: "approve-or-reject",
                title: "Approve or reject",
                steps: [
                    "Open the pending item and read the proposal and its reasoning.",
                    "Record a decision against the proposal.",
                    "Follow up on the outcome in the relevant surface.",
                ],
                note: "Approvals never auto-execute. If a step is missing, the proposal stays pending until a reviewer acts.",
            },
        ],
        related: [
            { categoryId: "security", slug: "roles-permissions" },
            { categoryId: "operations", slug: "reports" },
        ],
    },
    {
        categoryId: "operations",
        slug: "payroll-hr",
        title: "Payroll & HR",
        description: "Payroll, leave, planning, and attrition workflows.",
        sections: [
            {
                id: "what-payroll-hr-covers",
                title: "What Payroll & HR covers",
                paragraphs: [
                    "Payroll & HR handles the people side of operations: payroll records, leave and attendance, headcount planning, and attrition trends across departments.",
                ],
            },
            {
                id: "leave-and-attendance",
                title: "Leave and attendance",
                paragraphs: [
                    "Leave and attendance are tracked per employee so coverage gaps are visible before they hit operations. Approvals apply to the people workflows the same way they do to stock actions.",
                ],
            },
            {
                id: "planning-and-attrition",
                title: "Planning and attrition",
                paragraphs: [
                    "Headcount planning and attrition reports show how your team is changing, department by department, so staffing decisions sit on current numbers.",
                ],
            },
        ],
        related: [
            { categoryId: "operations", slug: "approvals" },
            { categoryId: "security", slug: "roles-permissions" },
        ],
    },
    {
        categoryId: "intelligence",
        slug: "market-signals",
        title: "Market signals",
        description:
            "Google Trends, YouTube, Reddit, GitHub, and news, watched continuously.",
        popular: true,
        cta: true,
        sections: [
            {
                id: "what-market-signals-are",
                title: "What market signals are",
                paragraphs: [
                    "Market signals are continuous reads of public demand data. Skyrict watches them against your categories and surfaces changes the week they happen.",
                ],
            },
            {
                id: "sources",
                title: "Sources",
                bullets: [
                    "Google Trends for search demand.",
                    "YouTube for video interest.",
                    "Reddit for conversation and community signals.",
                    "GitHub for developer and ecosystem signals.",
                    "News APIs for coverage and events.",
                ],
            },
            {
                id: "how-often-they-are-read",
                title: "How often they are read",
                paragraphs: [
                    "Each source is watched on a recurring schedule. A read that succeeds carries a live label; older reads fall back to cache so you always see the last known state.",
                ],
            },
            {
                id: "read-a-signal",
                title: "Read a signal",
                steps: [
                    "Open Market signals and check the source status for your categories.",
                    "Skim the watch points for anything above your normal noise.",
                    "Follow a change into Trending or Explore for the full shape of the move.",
                ],
                note: "A signal is a measurement, not a verdict. Treat sharp moves as a lead to investigate, not an instruction to act.",
            },
        ],
        related: [
            { categoryId: "intelligence", slug: "trending" },
            { categoryId: "intelligence", slug: "results" },
        ],
    },
    {
        categoryId: "intelligence",
        slug: "trending",
        title: "Trending",
        description: "What is rising across your signal sources this week.",
        sections: [
            {
                id: "what-trending-shows",
                title: "What Trending shows",
                paragraphs: [
                    "Trending ranks what is rising across your signal sources over the recent window, so the week's movers are one list instead of a wall of feeds.",
                ],
            },
            {
                id: "how-it-ranks",
                title: "How it ranks",
                paragraphs: [
                    "Terms are scored by how far they have moved from their own baseline, not by raw volume. A small term doubling matters as much as a large one growing steadily.",
                ],
            },
            {
                id: "use-it",
                title: "Use it",
                paragraphs: [
                    "Use Trending to scan for demand shifts in your categories, then open Explore to see detail or Results when the synthesis suggests an action.",
                ],
            },
        ],
        related: [
            { categoryId: "intelligence", slug: "market-signals" },
            { categoryId: "intelligence", slug: "explore" },
        ],
    },
    {
        categoryId: "intelligence",
        slug: "explore",
        title: "Explore",
        description: "Drill into a category and watch demand move.",
        sections: [
            {
                id: "what-explore-is-for",
                title: "What Explore is for",
                paragraphs: [
                    "Explore lets you pick a category and watch its demand shape over time, across sources, so a Trending blip becomes a story you can read.",
                ],
            },
            {
                id: "pick-a-category",
                title: "Pick a category",
                steps: [
                    "Open Explore and choose a category.",
                    "Switch between sources to compare search, video, and conversation.",
                    "Zoom through the window to see when the move started.",
                ],
            },
            {
                id: "read-the-shape",
                title: "Read the shape",
                paragraphs: [
                    "A steady rise, a spike, or a fade each mean something different. Compare the shape against your own sales velocity before you treat it as opportunity.",
                ],
            },
        ],
        related: [
            { categoryId: "intelligence", slug: "trending" },
            { categoryId: "intelligence", slug: "results" },
        ],
    },
    {
        categoryId: "intelligence",
        slug: "results",
        title: "Results",
        description: "The synthesis: what the market is telling you to do.",
        sections: [
            {
                id: "what-results-are",
                title: "What Results are",
                paragraphs: [
                    "Results is the synthesis layer of intelligence. It combines your signal reads into a small set of statements about what the market is telling you, with the evidence attached.",
                ],
            },
            {
                id: "how-they-are-built",
                title: "How they are built",
                paragraphs: [
                    "Each result cites the sources and the window it came from, so you can trace any claim back to the underlying signal instead of trusting a headline.",
                ],
            },
            {
                id: "act-on-a-result",
                title: "Act on a result",
                steps: [
                    "Open the result and read the claim and its evidence.",
                    "Check the related signal detail in Explore.",
                    "Decide, or let an agent take the proposal through Approvals.",
                ],
                note: "Results express likelihood, not certainty. The reasoning is attached so you can disagree with it and still make the call.",
            },
        ],
        related: [
            { categoryId: "intelligence", slug: "market-signals" },
            { categoryId: "agents", slug: "guardian" },
        ],
    },
    {
        categoryId: "agents",
        slug: "guardian",
        title: "Guardian",
        description: "Background watch over your operations, surfacing what needs you.",
        cta: true,
        sections: [
            {
                id: "what-guardian-does",
                title: "What Guardian does",
                paragraphs: [
                    "Guardian watches your operations in the background and reports what needs you: stock nearing reorder, anomalies in movement, and coverage gaps.",
                ],
            },
            {
                id: "what-it-surfaces",
                title: "What it surfaces",
                bullets: [
                    "Low stock against live coverage.",
                    "Units behaving outside their history.",
                    "Order flow that is drifting from sales velocity.",
                ],
            },
            {
                id: "read-a-report",
                title: "Read a report",
                steps: [
                    "Open Guardian and pick the latest report.",
                    "Read the watch items, each with the reasoning and the numbers behind it.",
                    "Act on the item or mark it to acknowledge.",
                ],
            },
            {
                id: "keep-it-honest",
                title: "Keep it honest",
                note: "Guardian proposes; it does not execute. Anything that changes your operations still goes through Approvals.",
            },
        ],
        related: [
            { categoryId: "agents", slug: "coaching" },
            { categoryId: "intelligence", slug: "results" },
        ],
    },
    {
        categoryId: "agents",
        slug: "coaching",
        title: "Coaching",
        description: "Operational guidance based on your live numbers.",
        cta: true,
        sections: [
            {
                id: "what-coaching-does",
                title: "What Coaching does",
                paragraphs: [
                    "Coaching turns your live numbers into operational guidance: what to restock, what to hold, and what to reconsider, with the reasoning attached.",
                ],
            },
            {
                id: "when-to-use-it",
                title: "When to use it",
                paragraphs: [
                    "Use Coaching when you want a second read on a decision: a restock call, a price question, or a priority conflict between orders and stock.",
                ],
            },
            {
                id: "ask-and-read",
                title: "Ask and read",
                steps: [
                    "Open Coaching and ask your question in plain language.",
                    "Read the answer alongside the numbers it cites.",
                    "Verify one cited number before you act; the reasoning is meant to be checked.",
                ],
            },
        ],
        related: [
            { categoryId: "agents", slug: "guardian" },
            { categoryId: "getting-started", slug: "read-your-first-pulse" },
        ],
    },
    {
        categoryId: "agents",
        slug: "your-agents",
        title: "Your agents",
        description: "The agents your workspace runs and how they are configured.",
        cta: true,
        sections: [
            {
                id: "what-you-see",
                title: "What you see",
                paragraphs: [
                    "Your agents lists the agents configured for your workspace: the ones that run continuously, like Guardian, and the ones you call on demand, like Coaching.",
                ],
            },
            {
                id: "configuration",
                title: "Configuration",
                paragraphs: [
                    "Each agent exposes the settings that matter for your operation: the surfaces it reads, the thresholds that decide what it surfaces, and whether actions require approval.",
                ],
            },
            {
                id: "credits",
                title: "Credits",
                paragraphs: [
                    "Agent work is metered against your plan's monthly AI credit budget. Usage is shown at any time under the plan, so you can see what the background work is costing before you tune it.",
                ],
                note: "Turn off the agents you do not use. Continuous watching you do not read still spends credits.",
            },
        ],
        related: [
            { categoryId: "agents", slug: "guardian" },
            { categoryId: "agents", slug: "coaching" },
        ],
    },
    {
        categoryId: "security",
        slug: "multi-factor-authentication",
        title: "Multi-factor authentication",
        description: "TOTP authenticator codes and one-time backup codes.",
        sections: [
            {
                id: "what-mfa-is",
                title: "What MFA is",
                paragraphs: [
                    "Multi-factor authentication adds a second proof of identity: a TOTP code from an authenticator app, in addition to your password.",
                ],
            },
            {
                id: "set-it-up",
                title: "Set it up",
                steps: [
                    "Open workspace settings and choose Security.",
                    "Scan the QR code with an authenticator app.",
                    "Confirm a generated code to finish enrollment.",
                ],
            },
            {
                id: "backup-codes",
                title: "Backup codes",
                paragraphs: [
                    "Skyrict issues one-time backup codes at enrollment. Store them offline; each works once if you lose access to your authenticator app.",
                ],
            },
            {
                id: "lost-access",
                title: "Lost access",
                bullets: [
                    "Use a backup code to sign in, then re-enroll MFA from settings.",
                    "If you are out of backup codes, contact support through GitHub.",
                ],
            },
        ],
        related: [
            { categoryId: "security", slug: "roles-permissions" },
            { categoryId: "getting-started", slug: "create-account" },
        ],
    },
    {
        categoryId: "security",
        slug: "roles-permissions",
        title: "Roles & permissions",
        description: "Role-based access across the workspace.",
        sections: [
            {
                id: "what-roles-control",
                title: "What roles control",
                paragraphs: [
                    "Roles decide what each member of the workspace can see and do, from read-only views to full administration.",
                ],
            },
            {
                id: "available-roles",
                title: "Available roles",
                paragraphs: [
                    "The workspace ships with a small set of roles covering ownership, administration, and operations. Permissions attach to surfaces and actions, so a role can read reports without approving changes, for example.",
                ],
            },
            {
                id: "change-a-role",
                title: "Change a role",
                steps: [
                    "Open the roles surface in settings.",
                    "Pick a member and assign a role.",
                    "Saved changes apply on the member's next action.",
                ],
                note: "The owner role is never removed. Keep at least one owner contact current in case of handover.",
            },
        ],
        related: [
            { categoryId: "security", slug: "multi-factor-authentication" },
            { categoryId: "operations", slug: "approvals" },
        ],
    },
    {
        categoryId: "security",
        slug: "source-code",
        title: "Source code",
        description: "Skyrict is open source. Audit the security story yourself.",
        sections: [
            {
                id: "open-source",
                title: "Open source",
                paragraphs: [
                    "Skyrict is open source under the MIT license. The repository is public on GitHub, including this documentation and its commit history.",
                ],
            },
            {
                id: "audit-it",
                title: "Audit it",
                paragraphs: [
                    "The codebase is small enough to read end to end. Security-relevant code lives beside the features it protects: authentication, sessions, MFA, and roles are verifiable in code.",
                ],
            },
            {
                id: "contribute",
                title: "Contribute",
                paragraphs: [
                    "Found a bug or a gap in the docs? Open an issue or send a pull request. Everything is answered in the open.",
                ],
            },
        ],
        related: [
            { categoryId: "security", slug: "multi-factor-authentication" },
            { categoryId: "security", slug: "roles-permissions" },
        ],
    },
];

const categoryById = new Map(
    docCategories.map((category) => [category.id, category]),
);

const articleKey = (categoryId: string, slug: string) =>
    `${categoryId}/${slug}`;

const articleByKey = new Map(
    docArticles.map((article) => [
        articleKey(article.categoryId, article.slug),
        article,
    ]),
);

/** Public route for a guide, e.g. /docs/getting-started/create-account. */
export function pathFor(categoryId: string, slug: string): string {
    return `/docs/${categoryId}/${slug}`;
}

/**
 * Canonical docs-surface route for a guide, e.g. /getting-started/create-account.
 *
 * The docs.skyrict.in surface serves the /docs tree without the /docs prefix
 * in the browser URL, so metadata canonicals must omit it. The docs layout's
 * metadataBase (https://docs.skyrict.in) resolves it to the public docs
 * hostname on every surface, including the Vercel deployment fallback.
 */
export function surfacePathFor(categoryId: string, slug: string): string {
    return `/${categoryId}/${slug}`;
}

/**
 * Docs nav href (the public /docs route) for a browser pathname.
 *
 * The middleware serves the docs.skyrict.in surface at the /docs tree without
 * exposing /docs in the URL, so there usePathname() reports the public form
 * (/getting-started), while docs nav hrefs and the fallback host
 * (skyrict.vercel.app/docs) use the /docs form. Normalize both sides so the
 * sidebar highlights the current article on every surface.
 */
export function docsActiveHref(pathname: string): string {
    if (pathname.startsWith("/docs")) return pathname;
    if (pathname === "/") return "/docs";
    return `/docs${pathname}`;
}

export function getCategory(categoryId: string): DocCategory | undefined {
    return categoryById.get(categoryId);
}

export function getArticle(
    categoryId: string,
    slug: string,
): DocArticle | undefined {
    return articleByKey.get(articleKey(categoryId, slug));
}

/** Every guide in sidebar order, flattened across categories. */
export function orderedArticles(): DocArticle[] {
    const byCategory = new Map<string, DocArticle[]>();
    for (const article of docArticles) {
        const list = byCategory.get(article.categoryId) ?? [];
        list.push(article);
        byCategory.set(article.categoryId, list);
    }
    const ordered: DocArticle[] = [];
    for (const category of docCategories) {
        ordered.push(...(byCategory.get(category.id) ?? []));
    }
    return ordered;
}

/** Sidebar navigation grouped by category, in sidebar order. */
export function docsNav(): DocsNavLink[] {
    const links: DocsNavLink[] = [];
    for (const category of docCategories) {
        for (const article of docArticles) {
            if (article.categoryId !== category.id) continue;
            links.push({
                category,
                href: pathFor(article.categoryId, article.slug),
                title: article.title,
            });
        }
    }
    return links;
}

/** Resolves an article's related references to public routes and titles. */
export function relatedFor(
    article: DocArticle,
): Array<{ title: string; href: string }> {
    if (!article.related) return [];
    return article.related
        .map((ref) => {
            const target = getArticle(ref.categoryId, ref.slug);
            return target
                ? {
                      title: target.title,
                      href: pathFor(target.categoryId, target.slug),
                  }
                : null;
        })
        .filter((entry): entry is { title: string; href: string } => entry !== null);
}

/** Plain text of a guide used by the search index. */
export function articleText(article: DocArticle): string {
    const parts: string[] = [article.title, article.description];
    for (const section of article.sections) {
        parts.push(section.title);
        parts.push(...(section.paragraphs ?? []));
        parts.push(...(section.bullets ?? []));
        parts.push(...(section.steps ?? []));
        if (section.note) parts.push(section.note);
    }
    return parts.join(" ");
}

export interface DocsSearchHit {
    title: string;
    description: string;
    href: string;
    category: string;
    snippet: string | null;
}

/** Full-text search over titles, descriptions, and guide bodies. */
export function searchDocs(query: string): DocsSearchHit[] {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];

    const scored: Array<{ hit: DocsSearchHit; score: number }> = [];

    for (const article of docArticles) {
        const category = getCategory(article.categoryId);
        const titleMatch = article.title.toLowerCase().includes(needle);
        const descriptionMatch =
            article.description.toLowerCase().includes(needle);
        const body = articleText(article);
        const bodyMatch = body.toLowerCase().includes(needle);

        if (!titleMatch && !descriptionMatch && !bodyMatch) continue;

        const score = (titleMatch ? 3 : 0) + (descriptionMatch ? 2 : 0) + 1;
        scored.push({
            score,
            hit: {
                title: article.title,
                description: article.description,
                href: pathFor(article.categoryId, article.slug),
                category: category?.name ?? "",
                snippet: snippetFor(article, needle),
            },
        });
    }

    return scored
        .sort((a, b) => b.score - a.score || a.hit.title.localeCompare(b.hit.title))
        .map((entry) => entry.hit);
}

function snippetFor(article: DocArticle, needle: string): string | null {
    for (const section of article.sections) {
        const candidates = [
            ...(section.paragraphs ?? []),
            ...(section.bullets ?? []),
            ...(section.steps ?? []),
        ];
        for (const text of candidates) {
            const index = text.toLowerCase().indexOf(needle);
            if (index !== -1) {
                const start = Math.max(0, index - 40);
                const end = Math.min(text.length, index + needle.length + 80);
                const prefix = start > 0 ? "..." : "";
                const suffix = end < text.length ? "..." : "";
                return `${prefix}${text.slice(start, end).trim()}${suffix}`;
            }
        }
        if (section.note?.toLowerCase().includes(needle)) {
            return section.note;
        }
    }
    return null;
}

export const popularArticles = docArticles.filter((article) => article.popular);