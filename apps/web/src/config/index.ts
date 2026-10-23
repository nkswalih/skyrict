export const site = {
    name: "Skyrict",
    tagline: "AI Business Operating System",
    title: "Skyrict: AI Business Operating System",
    description:
        "Skyrict is the AI business operating system for inventory, sales, cash, orders, CRM, and HR. AI agents turn live records into decisions your team can act on.",
    url: "https://skyrict.in",
};

export const contactEmail = "sales@skyrict.in";

export const navLinks = [
    { label: "Product", href: "/product" },
    { label: "Pricing", href: "/pricing" },
    { label: "Docs", href: "/docs" },
    { label: "About", href: "/about" },
    { label: "Contact", href: "/contact" },
];

export interface FooterLink {
    label: string;
    href?: string;
    soon?: boolean;
}

export interface FooterColumn {
    title: string;
    links: FooterLink[];
}

export const footerColumns: FooterColumn[] = [
    {
        title: "Product",
        links: [
            { label: "Pricing", href: "/pricing" },
            { label: "Product", href: "/product" },
        ],
    },
    {
        title: "Resources",
        links: [
            { label: "Docs", href: "/docs" },
            {
                label: "Security",
                href: "/docs/security/multi-factor-authentication",
            },
        ],
    },
    {
        title: "Company",
        links: [
            { label: "About", href: "/about" },
            { label: "Contact", href: "/contact" },
            { label: "Get started", href: "/signup" },
            { label: "Book a walkthrough", href: "/contact" },
        ],
    },
];

export const footerLegalLinks: FooterLink[] = [
    { label: "Privacy", href: "/privacy" },
    { label: "Terms", href: "/terms" },
];

export const signalSources = [
    "Google Trends",
    "YouTube",
    "Reddit",
    "GitHub",
    "News APIs",
];

export interface PricingFaq {
    question: string;
    answer: string;
}

export const pricingFaq: PricingFaq[] = [
    {
        question: "Is there a free plan?",
        answer: "Yes. Starter is free forever: the core ERP, one AI agent, and one user. No credit card required.",
    },
    {
        question: "How does the 14-day trial work?",
        answer: "Paid plans start with a 14-day free trial and no credit card required. You pay only after the trial ends, and you can cancel anytime from billing.",
    },
    {
        question: "How are prices shown?",
        answer: "Prices are fixed per currency and resolved from your region. Annual billing saves roughly 17% versus monthly. Checkout always shows the exact amount in your currency.",
    },
    {
        question: "What are AI credits?",
        answer: "AI credits meter the agent work your workspace can run each month, such as questions, restock suggestions, and analysis. Each plan defines its own monthly budget, shown under Usage.",
    },
    {
        question: "Can I switch or cancel anytime?",
        answer: "Yes. Upgrade, downgrade, or cancel from billing whenever you like. You keep access to your data and can restart a paid plan at any time.",
    },
    {
        question: "Which regions is Skyrict available in?",
        answer: "The beta serves the United States, India, the United Kingdom, the European Union, Australia, Canada, Singapore, the UAE, and Saudi Arabia, with more markets on the way.",
    },
    {
        question: "How does Enterprise pricing work?",
        answer: `Enterprise is a custom contract, invoiced annually, with role-based permissions and a custom rollout. Contact ${contactEmail}.`,
    },
];
