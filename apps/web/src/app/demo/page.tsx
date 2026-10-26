import { redirect } from "next/navigation";

import { DEMO_HOME } from "@/lib/demo/demo-routes";

export default function DemoIndexPage() {
  redirect(DEMO_HOME);
}
