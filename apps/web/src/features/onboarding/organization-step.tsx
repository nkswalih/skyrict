"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, CheckCircle2, LoaderCircle } from "lucide-react";

import { PolicyDialog } from "@/components/onboarding/policy-dialog";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { countries, industries } from "@/config/onboarding";
import { checkWorkspaceSlug, createOrganization } from "@/lib/api/auth-api";
import { AuthButton } from "@/lib/auth/AuthButton";
import { AuthInput } from "@/lib/auth/AuthInput";
import { ProvisioningScreen } from "@/features/onboarding/provisioning-screen";

const orgSchema = z.object({
  companyName: z.string().trim().min(2, "Enter your company name"),
  industry: z.string().min(1, "Select your industry"),
  workspaceSlug: z
    .string()
    .trim()
    .min(2, "Enter a workspace URL")
    .regex(/^[a-z0-9][a-z0-9-]*$/, "Lowercase letters, numbers, and hyphens only"),
  ownerFullName: z.string().trim().min(2, "Enter the owner's full name"),
  phoneCountry: z.string().min(1, "Select a country code"),
  phoneNumber: z
    .string()
    .trim()
    .min(7, "Enter a valid phone number")
    .regex(/^[0-9+\-() ]+$/, "Numbers, +, -, and spaces only"),
  addressCountry: z.string().min(1, "Select a country"),
  addressLine1: z.string().trim().min(2, "Enter your street address"),
  addressLine2: z.string().trim().optional(),
  city: z.string().trim().min(2, "Enter your city"),
  state: z.string().trim().min(1, "Enter your state or province"),
  postalCode: z.string().trim().min(2, "Enter your postal code"),
  acceptTerms: z.boolean().refine((value) => value === true, {
    message: "Accept the Terms of Service and Privacy Policy to continue",
  }),
  orgAuthorized: z.boolean().refine((value) => value === true, {
    message: "Confirm you're authorized to set up this organization",
  }),
});

type OrganizationValues = z.infer<typeof orgSchema>;

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
}

/** Detect country from the browser's timezone (no permission prompt). */
function detectCountry(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const map: Record<string, string> = {
      "America/New_York": "US",
      "America/Chicago": "US",
      "America/Denver": "US",
      "America/Los_Angeles": "US",
      "America/Anchorage": "US",
      "America/Phoenix": "US",
      "America/Indiana/Indianapolis": "US",
      "America/Detroit": "US",
      "America/Toronto": "CA",
      "America/Vancouver": "CA",
      "America/Edmonton": "CA",
      "America/Winnipeg": "CA",
      "America/Halifax": "CA",
      "America/St_Johns": "CA",
      "Europe/London": "GB",
      "Europe/Paris": "FR",
      "Europe/Berlin": "DE",
      "Europe/Madrid": "ES",
      "Europe/Rome": "IT",
      "Europe/Lisbon": "PT",
      "Europe/Amsterdam": "NL",
      "Europe/Brussels": "BE",
      "Europe/Zurich": "CH",
      "Europe/Vienna": "AT",
      "Europe/Stockholm": "SE",
      "Europe/Oslo": "NO",
      "Europe/Copenhagen": "DK",
      "Europe/Helsinki": "FI",
      "Europe/Dublin": "IE",
      "Europe/Warsaw": "PL",
      "Europe/Prague": "CZ",
      "Europe/Bucharest": "RO",
      "Europe/Athens": "GR",
      "Europe/Istanbul": "TR",
      "Europe/Kiev": "UA",
      "Europe/Belgrade": "RS",
      "Europe/Luxembourg": "LU",
      "Europe/Zagreb": "HR",
      "Europe/Ljubljana": "SI",
      "Europe/Sofia": "BG",
      "Europe/Reykjavik": "IS",
      "Asia/Kolkata": "IN",
      "Asia/Calcutta": "IN",
      "Asia/Singapore": "SG",
      "Asia/Tokyo": "JP",
      "Asia/Seoul": "KR",
      "Asia/Shanghai": "CN",
      "Asia/Hong_Kong": "HK",
      "Asia/Taipei": "TW",
      "Asia/Kuala_Lumpur": "MY",
      "Asia/Manila": "PH",
      "Asia/Jakarta": "ID",
      "Asia/Bangkok": "TH",
      "Asia/Ho_Chi_Minh": "VN",
      "Asia/Dubai": "AE",
      "Asia/Riyadh": "SA",
      "Asia/Jerusalem": "IL",
      "Asia/Karachi": "PK",
      "Asia/Dhaka": "BD",
      "Asia/Colombo": "LK",
      "Australia/Sydney": "AU",
      "Australia/Melbourne": "AU",
      "Australia/Brisbane": "AU",
      "Australia/Perth": "AU",
      "Australia/Adelaide": "AU",
      "Pacific/Auckland": "NZ",
      "America/Sao_Paulo": "BR",
      "America/Mexico_City": "MX",
      "America/Argentina/Buenos_Aires": "AR",
      "America/Santiago": "CL",
      "America/Bogota": "CO",
      "America/Lima": "PE",
      "Africa/Cairo": "EG",
      "Africa/Casablanca": "MA",
      "Africa/Lagos": "NG",
      "Africa/Nairobi": "KE",
      "Africa/Johannesburg": "ZA",
    };
    return map[tz] || "US";
  } catch {
    return "US";
  }
}

function OrganizationStep({
  email,
  vt,
  plan,
}: {
  email: string;
  vt: string;
  plan: string;
}) {
  const [provisioning, setProvisioning] = useState(false);
  const [createdSlug, setCreatedSlug] = useState<string>();
  const slugTouched = useRef(false);
  const [slugAvailability, setSlugAvailability] = useState<
    "idle" | "checking" | "available" | "taken"
  >("idle");
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    setError,
    clearErrors,
    formState: { errors, isSubmitting },
  } = useForm<OrganizationValues>({
    resolver: zodResolver(orgSchema),
    defaultValues: {
      companyName: "",
      industry: "",
      workspaceSlug: "",
      ownerFullName: "",
      phoneCountry: detectCountry(),
      phoneNumber: "",
      addressCountry: detectCountry(),
      addressLine1: "",
      addressLine2: "",
      city: "",
      state: "",
      postalCode: "",
      acceptTerms: false,
      orgAuthorized: false,
    },
  });

  const companyName = watch("companyName");
  const workspaceSlug = watch("workspaceSlug");
  const phoneCountries = useMemo(
    () =>
      countries
        .filter((country) => Boolean(country.dialCode))
        .sort((a, b) => a.name.localeCompare(b.name)),
    [],
  );
  const addressCountries = useMemo(
    () => [...countries].sort((a, b) => a.name.localeCompare(b.name)),
    [],
  );
  const phoneCountryValue = watch("phoneCountry");
  const addressCountryValue = watch("addressCountry");
  const selectedPhoneCountry = phoneCountries.find(
    (country) => country.code === phoneCountryValue,
  );

  useEffect(() => {
    if (slugTouched.current) return;
    const slug = slugify(companyName);
    if (slug) {
      setValue("workspaceSlug", slug, { shouldValidate: false });
    }
  }, [companyName, setValue]);

  useEffect(() => {
    let cancelled = false;
    const parsed = orgSchema.shape.workspaceSlug.safeParse(workspaceSlug);
    if (!parsed.success) {
      setSlugAvailability("idle");
      return;
    }
    setSlugAvailability("checking");
    const timer = setTimeout(async () => {
      try {
        const result = await checkWorkspaceSlug({ slug: parsed.data });
        if (!cancelled) {
          setSlugAvailability(result.available ? "available" : "taken");
        }
      } catch {
        // Backend unreachable / transient failure - stay neutral so the user
        // can proceed; the submit handler re-checks and surfaces errors.
        if (!cancelled) {
          setSlugAvailability("idle");
        }
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [workspaceSlug]);

  function handleCompleteProvisioning() {
    if (!createdSlug) return;
    const { protocol, hostname, port } = window.location;
    const apex = hostname.split(".").slice(1).join(".") || hostname;
    const target = `${protocol}//${createdSlug}.signin.${apex}${
      port ? `:${port}` : ""
    }/signin?email=${encodeURIComponent(email)}`;
    window.location.assign(target);
  }

  async function onSubmit(values: OrganizationValues) {
    let slugAvailable: boolean;
    try {
      slugAvailable = (await checkWorkspaceSlug({ slug: values.workspaceSlug })).available;
    } catch (err) {
      setError("root", {
        type: "manual",
        message:
          err instanceof Error
            ? err.message
            : "Could not check the workspace URL. Try again.",
      });
      return;
    }
    if (!slugAvailable) {
      setError("workspaceSlug", {
        type: "manual",
        message: "This workspace URL is taken. Pick another one.",
      });
      return;
    }
    try {
      const result = await createOrganization({
        email,
        verificationToken: vt,
        planId: plan,
        companyName: values.companyName,
        industry: values.industry,
        workspaceSlug: values.workspaceSlug,
        ownerFullName: values.ownerFullName,
        phoneCountry: values.phoneCountry,
        phoneNumber: values.phoneNumber,
        address: {
          country: values.addressCountry,
          addressLine1: values.addressLine1,
          addressLine2: values.addressLine2 || undefined,
          city: values.city,
          state: values.state,
          postalCode: values.postalCode,
        },
      });
      setCreatedSlug(result.tenantSlug);
    } catch (err) {
      setError("root", {
        type: "manual",
        message:
          err instanceof Error
            ? err.message
            : "Could not create your workspace. Please try again.",
      });
      return;
    }
    setProvisioning(true);
  }

  if (provisioning) {
    return <ProvisioningScreen onComplete={handleCompleteProvisioning} />;
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <div className="rounded-lg border border-border bg-muted/40 p-3">
        <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <Building2 aria-hidden="true" className="size-3.5 text-primary" />
          Plan selected:{" "}
          <span className="font-semibold capitalize">{plan}</span>
        </p>
      </div>

      <AuthInput
        label="Company name"
        id="companyName"
        type="text"
        autoComplete="organization"
        placeholder="e.g. Acme Corp"
        error={errors.companyName?.message}
        {...register("companyName")}
      />

      <div className="space-y-1.5">
        <label
          htmlFor="industry"
          className="text-sm font-medium text-foreground"
        >
          Industry
        </label>
        <Select
          value={watch("industry")}
          onValueChange={(value) => {
            setValue("industry", value, { shouldValidate: true });
            clearErrors("industry");
          }}
        >
          <SelectTrigger id="industry" className="h-10">
            <SelectValue placeholder="Select your industry" />
          </SelectTrigger>
          <SelectContent position="popper">
            {industries.map((industry) => (
              <SelectItem key={industry} value={industry}>
                {industry}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errors.industry ? (
          <p className="text-xs font-medium text-destructive">
            {errors.industry.message}
          </p>
        ) : null}
      </div>

      <AuthInput
        label="Workspace URL"
        id="workspaceSlug"
        type="text"
        autoComplete="off"
        hint={
          slugAvailability === "checking"
            ? "Checking availability\n"
            : slugAvailability === "available"
              ? "This URL is available."
              : workspaceSlug
                ? `Your workspace will live at ${workspaceSlug}.signin.${typeof window !== "undefined" ? (window.location.hostname.split(".").slice(1).join(".") || "skyrict.com") : "skyrict.com"}`
                : "Your workspace will live at your-slug.signin.skyrict.com"
        }
        error={
          errors.workspaceSlug?.message ??
          (slugAvailability === "taken" ? "This workspace URL is taken." : undefined)
        }
        trailing={
          slugAvailability === "checking" ? (
            <LoaderCircle
              aria-hidden="true"
              className="mr-1 size-4 animate-spin text-muted-foreground"
            />
          ) : slugAvailability === "available" ? (
            <CheckCircle2 aria-hidden="true" className="mr-1 size-4 text-primary" />
          ) : null
        }
        {...register("workspaceSlug", {
          onChange: () => {
            slugTouched.current = true;
          },
        })}
      />

      <AuthInput
        label="Owner full name"
        id="ownerFullName"
        type="text"
        autoComplete="name"
        placeholder="First and last name"
        error={errors.ownerFullName?.message}
        {...register("ownerFullName")}
      />

      <div className="space-y-1.5">
        <label
          htmlFor="phoneCountry"
          className="text-sm font-medium text-foreground"
        >
          Phone
        </label>
        <div className="grid grid-cols-[7rem_1fr] gap-2">
          <Select
            value={phoneCountryValue}
            onValueChange={(value) => {
              setValue("phoneCountry", value, { shouldValidate: true });
              setValue("addressCountry", value, { shouldValidate: true });
            }}
          >
            <SelectTrigger id="phoneCountry" className="h-10">
              <span className="flex items-center gap-1.5">
                {selectedPhoneCountry ? (
                  <span className={`fi fi-${selectedPhoneCountry.code.toLowerCase()}`} />
                ) : null}
                <span>
                  {selectedPhoneCountry
                    ? `+${selectedPhoneCountry.dialCode}`
                    : "Code"}
                </span>
              </span>
            </SelectTrigger>
            <SelectContent position="popper" className="max-h-72 min-w-64">
              {phoneCountries.map((country) => (
                <SelectItem key={country.code} value={country.code}>
                  <span className="flex items-center gap-1.5">
                    <span className={`fi fi-${country.code.toLowerCase()}`} />
                    <span>+{country.dialCode} · {country.name}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <AuthInput
            id="phoneNumber"
            label="Phone number"
            hideLabel
            type="tel"
            autoComplete="tel"
            placeholder="10-digit phone number"
            error={errors.phoneNumber?.message}
            {...register("phoneNumber")}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <label
          htmlFor="addressCountry"
          className="text-sm font-medium text-foreground"
        >
          Business location
        </label>
        <Select
          value={addressCountryValue}
          onValueChange={(value) =>
            setValue("addressCountry", value, { shouldValidate: true })
          }
        >
          <SelectTrigger id="addressCountry" className="h-10">
            <span className="flex items-center gap-1.5">
              {addressCountryValue ? (
                <span className={`fi fi-${addressCountryValue.toLowerCase()}`} />
              ) : null}
              <span>{addressCountries.find((c) => c.code === addressCountryValue)?.name || "Select a country"}</span>
            </span>
          </SelectTrigger>
          <SelectContent position="popper" className="max-h-72 min-w-64">
            {addressCountries.map((country) => (
              <SelectItem key={country.code} value={country.code}>
                <span className="flex items-center gap-1.5">
                  <span className={`fi fi-${country.code.toLowerCase()}`} />
                  <span>{country.name}</span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errors.addressCountry ? (
          <p className="text-xs font-medium text-destructive">
            {errors.addressCountry.message}
          </p>
        ) : null}
      </div>

      <AuthInput
        label="Street address"
        id="addressLine1"
        type="text"
        autoComplete="address-line1"
        placeholder="Street name and number"
        error={errors.addressLine1?.message}
        {...register("addressLine1")}
      />

      <AuthInput
        label="Unit, floor, or suite (optional)"
        id="addressLine2"
        type="text"
        autoComplete="address-line2"
        placeholder="e.g. Apt 4B, Floor 2, or Suite 100"
        error={errors.addressLine2?.message}
        {...register("addressLine2")}
      />

      <div className="grid grid-cols-2 gap-3">
        <AuthInput
          label="City"
          id="city"
          type="text"
          autoComplete="address-level2"
          placeholder="City name"
          error={errors.city?.message}
          {...register("city")}
        />
        <AuthInput
          label="State / Province"
          id="state"
          type="text"
          autoComplete="address-level1"
          placeholder="State or Province"
          error={errors.state?.message}
          {...register("state")}
        />
      </div>

      <AuthInput
        label="Postal code"
        id="postalCode"
        type="text"
        autoComplete="postal-code"
        placeholder="Zip or postal code"
        error={errors.postalCode?.message}
        {...register("postalCode")}
      />

      <CheckboxRow
        id="acceptTerms"
        checked={Boolean(watch("acceptTerms"))}
        error={errors.acceptTerms?.message}
        onChange={(checked) =>
          setValue("acceptTerms", checked, { shouldValidate: true })
        }
        policyLink={<PolicyDialog />}
      >
        I agree to Skyrict&apos;s Terms of Service and Privacy Policy.
      </CheckboxRow>

      <CheckboxRow
        id="orgAuthorized"
        checked={Boolean(watch("orgAuthorized"))}
        error={errors.orgAuthorized?.message}
        onChange={(checked) =>
          setValue("orgAuthorized", checked, { shouldValidate: true })
        }
      >
        I&apos;m authorized to set up this organization and make billing decisions
        on its behalf.
      </CheckboxRow>

      {errors.root ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {errors.root.message}
        </div>
      ) : null}

      <AuthButton type="submit" className="w-full" loading={isSubmitting}>
        Create my workspace
      </AuthButton>
    </form>
  );
}

function CheckboxRow({
  id,
  checked,
  error,
  onChange,
  policyLink,
  children,
}: {
  id: string;
  checked: boolean;
  error?: string;
  onChange: (checked: boolean) => void;
  policyLink?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-start gap-2.5">
        <Checkbox
          id={id}
          checked={checked}
          onCheckedChange={(value) => onChange(value === true)}
          aria-describedby={error ? `${id}-error` : undefined}
          aria-invalid={error ? true : undefined}
        />
        <label
          htmlFor={id}
          className="select-none text-sm leading-5 text-muted-foreground"
        >
          {children}
        </label>
      </div>
      {policyLink ? <div className="mt-0.5 pl-6">{policyLink}</div> : null}
      {error ? (
        <p
          id={`${id}-error`}
          className="mt-1 pl-6 text-xs font-medium text-destructive"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

export { OrganizationStep };
