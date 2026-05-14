"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredToken } from "./lib/client";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getStoredToken() ? "/dashboard" : "/auth");
  }, [router]);

  return (
    <main className="routeLoaderShell">
      <section className="routeLoaderCard">
        <div className="sectionBadge">Interview Pro</div>
        <h1>Preparing your workspace</h1>
        <p>Checking your secure session and opening the right page.</p>
      </section>
    </main>
  );
}
