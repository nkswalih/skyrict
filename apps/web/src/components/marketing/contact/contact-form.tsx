"use client";

import { useMemo, useState } from "react";
import { CircleCheck, Mail } from "lucide-react";

import { ContactFormFields } from "@/components/marketing/contact/contact-form-fields";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { contactEmail } from "@/config";

interface FormValues {
    name: string;
    email: string;
    company: string;
    companySize: string;
    message: string;
}

interface FormErrors {
    name?: string;
    email?: string;
    company?: string;
    companySize?: string;
    message?: string;
}

const initialValues: FormValues = {
    name: "",
    email: "",
    company: "",
    companySize: "",
    message: "",
};

const companySizes = ["1-10", "11-50", "51-200", "201-500", "500+"];

function validate(values: FormValues): FormErrors {
    const errors: FormErrors = {};
    if (!values.name.trim()) {
        errors.name = "Enter your name.";
    }
    if (!values.email.trim()) {
        errors.email = "Enter your work email.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
        errors.email = "Enter a valid email address.";
    }
    if (!values.company.trim()) {
        errors.company = "Enter your company name.";
    }
    if (!values.companySize) {
        errors.companySize = "Select your company size.";
    }
    if (!values.message.trim()) {
        errors.message = "Enter a message.";
    } else if (values.message.trim().length < 10) {
        errors.message = "Add a little more detail, at least 10 characters.";
    }
    return errors;
}

function ContactForm() {
    const [values, setValues] = useState<FormValues>(initialValues);
    const [errors, setErrors] = useState<FormErrors>({});
    const [submitting, setSubmitting] = useState(false);
    const [sent, setSent] = useState(false);

    const mailtoHref = useMemo(() => {
        const subject = `Skyrict: ${values.company.trim() || "evaluation"}`;
        const body = [
            `Name: ${values.name.trim()}`,
            `Work email: ${values.email.trim()}`,
            `Company: ${values.company.trim()}`,
            `Company size: ${values.companySize}`,
            "",
            values.message.trim(),
        ].join("\n");
        return `mailto:${contactEmail}?subject=${encodeURIComponent(
            subject,
        )}&body=${encodeURIComponent(body)}`;
    }, [values]);

    const handleChange = (field: keyof FormValues, value: string) => {
        setValues((current) => ({ ...current, [field]: value }));
        if (errors[field]) {
            setErrors((current) => ({ ...current, [field]: undefined }));
        }
    };

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const nextErrors = validate(values);
        setErrors(nextErrors);
        if (Object.keys(nextErrors).length > 0) {
            const firstError = document.querySelector<HTMLElement>(
                "[aria-invalid='true']",
            );
            firstError?.focus();
            return;
        }
        setSubmitting(true);
        await new Promise((resolve) => setTimeout(resolve, 600));
        setSubmitting(false);
        setSent(true);
    };

    if (sent) {
        return (
            <div
                role="status"
                className="flex h-full flex-col items-center justify-center rounded-2xl border border-border bg-card p-8 text-center sm:p-10"
            >
                <span className="flex size-12 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-primary">
                    <CircleCheck aria-hidden="true" className="size-6" />
                </span>
                <h2 className="mt-5 font-display text-2xl font-semibold tracking-tight text-foreground">
                    Your message is ready.
                </h2>
                <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
                    It is composed below and will be sent from your email app to{" "}
                    <span className="font-mono text-foreground">
                        {contactEmail}
                    </span>
                    . We reply from the same address.
                </p>
                <div className="mt-6 w-full max-w-md rounded-xl border border-border bg-muted/30 p-4 text-left">
                    <p className="text-xs font-medium text-foreground">
                        {values.company.trim() || "Skyrict evaluation"}
                    </p>
                    <p className="mt-1.5 line-clamp-4 whitespace-pre-line text-left text-xs leading-relaxed text-muted-foreground">
                        {values.message.trim()}
                    </p>
                </div>
                <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                    <Button asChild variant="brand" size="pill-lg">
                        <a href={mailtoHref}>
                            <Mail aria-hidden="true" className="size-4" />
                            Open your email app
                        </a>
                    </Button>
                    <Button
                        variant="outline"
                        size="pill-lg"
                        className="border-marketing-ink/15 bg-transparent text-marketing-ink hover:bg-marketing-ink/[0.04] hover:text-marketing-ink"
                        onClick={() => setSent(false)}
                    >
                        Edit message
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <form
            onSubmit={handleSubmit}
            noValidate
            className="rounded-2xl border border-border bg-card p-6 sm:p-8"
        >
            <ContactFormFields
                values={values}
                errors={errors}
                companySizes={companySizes}
                loading={submitting}
                onChange={handleChange}
            />
            <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-muted-foreground">
                    We use your details only to answer your message.
                </p>
                <Button
                    type="submit"
                    variant="brand"
                    size="pill-lg"
                    disabled={submitting}
                >
                    {submitting ? (
                        <>
                            <Spinner aria-hidden="true" className="size-4" />
                            Preparing message
                        </>
                    ) : (
                        "Send message"
                    )}
                </Button>
            </div>
        </form>
    );
}

export { ContactForm };
