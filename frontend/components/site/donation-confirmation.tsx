"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type DonationStatus = {
  payment_reference: string;
  status: "pending"|"paid"|"failed"|"cancelled";
  amount: string;
  currency: string;
  verified_at: string|null;
};
const statuses:Record<string,string>={
  pending:"We are waiting for verified PayFast confirmation. Please do not pay again until you have checked your bank and the payment reference.",
  paid:"Your contribution has been verified by PayFast. Thank you for supporting Amaris Mathematics Academy.",
  failed:"The payment could not be confirmed. Please contact the Amaris team before trying again.",
  cancelled:"This checkout was cancelled or did not complete. No successful contribution is recorded.",
};

export function DonationConfirmation({reference}:{reference:string}) {
  const [status,setStatus]=useState<DonationStatus|null>(null);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  async function refresh(){
    try{
      const response=await fetch("/api/donations/"+encodeURIComponent(reference),{cache:"no-store"});
      if(!response.ok)throw new Error("Payment status is temporarily unavailable.");
      const data=await response.json() as DonationStatus;
      if(data.payment_reference!==reference)throw new Error("Payment reference mismatch.");
      setStatus(data);setError("");
    }catch(cause){setError(cause instanceof Error?cause.message:"Could not load payment status.");}
    finally{setLoading(false);}
  }
  useEffect(()=>{
    void refresh();
    const interval=window.setInterval(()=>void refresh(),15000);
    return ()=>window.clearInterval(interval);
  },[reference]);
  return (
    <section className="mx-auto max-w-2xl rounded-[2rem] border border-[#dce4ef] bg-white p-8 shadow-sm" aria-live="polite">
      <h1 className="text-3xl font-semibold text-[#07152d]">Contribution status</h1>
      <p className="mt-4 break-all text-xs font-mono text-[#526781]">Reference: {reference}</p>
      {loading?<p className="mt-5">Checking payment verification…</p>:null}
      {status?<div className="mt-6 rounded-xl bg-[#f3f7fc] p-5">
        <p className="font-semibold capitalize">{status.status}</p>
        <p className="mt-2 text-lg font-bold">R{status.amount} {status.currency}</p>
        <p className="mt-3 text-sm leading-7">{statuses[status.status]||statuses.pending}</p>
      </div>:null}
      {error?<p role="alert" className="mt-5 text-sm text-red-700">{error}</p>:null}
      <button onClick={()=>void refresh()} type="button" className="mt-5 min-h-11 rounded-full border border-[#0b2a5b] px-5 font-semibold text-[#0b2a5b]">Refresh payment status</button>
      <p className="mt-5 text-xs leading-6 text-[#526781]">The PayFast browser return does not prove payment. Only a server-verified notification can mark a contribution paid. A payment acknowledgement is not a Section 18A tax receipt.</p>
      <Link className="mt-4 inline-block font-semibold text-[#1f5bbd] underline" href="/support-our-project">Return to Support Our Project</Link>
    </section>
  );
}
