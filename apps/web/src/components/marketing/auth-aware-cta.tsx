import Link from "next/link";

import { Button } from "@/components/ui/button";

function AuthAwareCta() {
    return (
        <Button variant="brand" size="pill-lg" asChild>
            <Link href="/signup" prefetch={false}>Start for free</Link>
        </Button>
    );
}

export { AuthAwareCta };
