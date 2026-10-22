import Link from "next/link";

import { Button } from "@/components/ui/button";

function AuthAwareCta() {
    return (
        <Button variant="brand" size="pill-lg" asChild>
            <Link href="/signup">Create your account</Link>
        </Button>
    );
}

export { AuthAwareCta };
