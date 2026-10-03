"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import PatientDashboard from "./patient/page";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      router.push("/auth");
    }
  }, [router]);

  return <PatientDashboard />;
}
