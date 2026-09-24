import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface FieldValues {
    name: string;
    email: string;
    company: string;
    companySize: string;
    message: string;
}

interface FieldErrors {
    name?: string;
    email?: string;
    company?: string;
    companySize?: string;
    message?: string;
}

function ContactFormFields({
    values,
    errors,
    companySizes,
    loading,
    onChange,
}: {
    values: FieldValues;
    errors: FieldErrors;
    companySizes: string[];
    loading: boolean;
    onChange: (field: keyof FieldValues, value: string) => void;
}) {
    const field = (
        key: keyof FieldValues,
        error: string | undefined,
    ): { "aria-invalid": boolean; "aria-describedby": string | undefined } => ({
        "aria-invalid": Boolean(error),
        "aria-describedby": error ? `${key}-error` : undefined,
    });

    return (
        <div className="space-y-5">
            <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-1.5">
                    <Label htmlFor="name">
                        Full name
                        <span aria-hidden="true" className="text-primary">
                            {" "}
                            *
                        </span>
                    </Label>
                    <Input
                        id="name"
                        name="name"
                        autoComplete="name"
                        value={values.name}
                        disabled={loading}
                        onChange={(event) =>
                            onChange("name", event.target.value)
                        }
                        {...field("name", errors.name)}
                    />
                    {errors.name ? (
                        <p id="name-error" className="text-xs text-destructive">
                            {errors.name}
                        </p>
                    ) : null}
                </div>
                <div className="space-y-1.5">
                    <Label htmlFor="email">
                        Work email
                        <span aria-hidden="true" className="text-primary">
                            {" "}
                            *
                        </span>
                    </Label>
                    <Input
                        id="email"
                        name="email"
                        type="email"
                        autoComplete="work email"
                        value={values.email}
                        disabled={loading}
                        onChange={(event) =>
                            onChange("email", event.target.value)
                        }
                        {...field("email", errors.email)}
                    />
                    {errors.email ? (
                        <p
                            id="email-error"
                            className="text-xs text-destructive"
                        >
                            {errors.email}
                        </p>
                    ) : null}
                </div>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-1.5">
                    <Label htmlFor="company">
                        Company
                        <span aria-hidden="true" className="text-primary">
                            {" "}
                            *
                        </span>
                    </Label>
                    <Input
                        id="company"
                        name="company"
                        autoComplete="organization"
                        value={values.company}
                        disabled={loading}
                        onChange={(event) =>
                            onChange("company", event.target.value)
                        }
                        {...field("company", errors.company)}
                    />
                    {errors.company ? (
                        <p
                            id="company-error"
                            className="text-xs text-destructive"
                        >
                            {errors.company}
                        </p>
                    ) : null}
                </div>
                <div className="space-y-1.5">
                    <Label htmlFor="companySize">
                        Company size
                        <span aria-hidden="true" className="text-primary">
                            {" "}
                            *
                        </span>
                    </Label>
                    <select
                        id="companySize"
                        name="companySize"
                        value={values.companySize}
                        disabled={loading}
                        onChange={(event) =>
                            onChange("companySize", event.target.value)
                        }
                        aria-invalid={Boolean(errors.companySize)}
                        aria-describedby={
                            errors.companySize
                                ? "companySize-error"
                                : undefined
                        }
                        className={cn(
                            "h-8 w-full rounded-lg border bg-transparent px-2.5 py-1 text-sm transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20",
                            values.companySize
                                ? "text-foreground"
                                : "text-muted-foreground",
                        )}
                    >
                        <option value="" disabled>
                            Select a range
                        </option>
                        {companySizes.map((size) => (
                            <option key={size} value={size}>
                                {size} people
                            </option>
                        ))}
                    </select>
                    {errors.companySize ? (
                        <p
                            id="companySize-error"
                            className="text-xs text-destructive"
                        >
                            {errors.companySize}
                        </p>
                    ) : null}
                </div>
            </div>

            <div className="space-y-1.5">
                <Label htmlFor="message">
                    Message
                    <span aria-hidden="true" className="text-primary">
                        {" "}
                        *
                    </span>
                </Label>
                <Textarea
                    id="message"
                    name="message"
                    rows={6}
                    value={values.message}
                    disabled={loading}
                    onChange={(event) =>
                        onChange("message", event.target.value)
                    }
                    {...field("message", errors.message)}
                />
                {errors.message ? (
                    <p id="message-error" className="text-xs text-destructive">
                        {errors.message}
                    </p>
                ) : null}
            </div>
        </div>
    );
}

export { ContactFormFields };