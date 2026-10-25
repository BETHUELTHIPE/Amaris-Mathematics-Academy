"use client";

import { useEffect, useState, type FormEvent } from "react";
import { CreditCard, HandHeart, LockKeyhole, LoaderCircle } from "lucide-react";

type Checkout = {
  payment_reference: string;
  gateway_url: string;
  fields: Record<string,string>;
};
type Availability = "loading"|"enabled"|"disabled";
const amounts = ["100","250","500","1000"];
const purposes = [
  {value:"learner",label:"Support a learner"},
  {value:"resources",label:"Contribute learning materials"},
  {value:"technology",label:"Improve accessible technology"},
  {value:"general",label:"General education project"},
];

export function DonationCheckoutForm() {
  const [availability,setAvailability] = useState<Availability>("loading");
  const [amount,setAmount] = useState("250");
  const [checkout,setCheckout] = useState<Checkout|null>(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/donations/config",{cache:"no-store",signal:controller.signal})
      .then(async response=>response.ok ? (await response.json()) as {available?:boolean} : {available:false})
      .then(body=>setAvailability(body.available===true?"enabled":"disabled"))
      .catch(()=>{if(!controller.signal.aborted)setAvailability("disabled")});
    return ()=>controller.abort();
  },[]);

  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if(availability!=="enabled"||busy)return;
    const form=new FormData(event.currentTarget);
    const value=Number(amount);
    if(!Number.isFinite(value)||value<20||value>100000||!/^\d+(?:\.\d{1,2})?$/.test(amount)){
      setError("Enter an amount from R20 to R100,000 with at most two decimal places.");
      return;
    }
    setBusy(true);setError("");
    try {
      const response=await fetch("/api/donations/checkout",{
        method:"POST",
        headers:{"Content-Type":"application/json","Accept":"application/json"},
        body:JSON.stringify({
          donor_name:String(form.get("donor_name")||""),
          donor_email:String(form.get("donor_email")||""),
          purpose:String(form.get("purpose")||"general"),
          amount:amount,
          consent:form.get("consent")==="on",
          idempotency_key:"donate-"+crypto.randomUUID().replaceAll("-",""),
        }),
      });
      const data=await response.json().catch(()=>({})) as Checkout&{detail?:string};
      if(!response.ok||!data.payment_reference||!data.fields){
        throw new Error(data.detail||"Checkout could not be prepared.");
      }
      setCheckout(data);
    }catch(cause){setError(cause instanceof Error?cause.message:"Checkout could not be prepared.");}
    finally{setBusy(false);}
  }

  if(checkout){
    return (
      <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-sm sm:p-9" aria-live="polite">
        <h3 className="text-2xl font-semibold">Confirm your contribution</h3>
        <p className="mt-3 text-sm leading-7 text-[#526781]">
          Your payment goes through PayFast. Amaris records it as received only after the payment provider verifies it.
        </p>
        <dl className="mt-5 rounded-2xl bg-[#f3f7fc] p-4 text-sm">
          <dt className="font-semibold">Amount</dt><dd className="mt-1 text-2xl font-bold text-[#0b2a5b]">R{checkout.fields.amount}</dd>
          <dt className="mt-3 font-semibold">Reference</dt><dd className="break-all font-mono text-xs">{checkout.payment_reference}</dd>
        </dl>
        <form action={checkout.gateway_url} method="post" className="mt-5">
          {Object.entries(checkout.fields).map(([key,value])=><input key={key} type="hidden" name={key} value={value}/>)}
          <button type="submit" className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 font-bold text-white">
            <CreditCard className="size-5"/> Continue securely to PayFast
          </button>
        </form>
        <button type="button" onClick={()=>setCheckout(null)} className="mt-4 min-h-11 w-full rounded-full border border-[#c9d5e5] px-4 text-sm font-semibold">Change contribution</button>
      </div>
    );
  }

  return (
    <section id="contribute-online" className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-sm sm:p-9" aria-labelledby="donate-title">
      <div className="flex items-center gap-3"><HandHeart className="size-7 text-[#1f5bbd]"/><h2 id="donate-title" className="text-2xl font-semibold">Contribute online</h2></div>
      <p className="mt-4 text-sm leading-7 text-[#526781]">
        Choose a once-off amount in South African rand. Contributions help the Amaris education project and do not purchase a student service or guarantee a particular outcome.
      </p>
      {availability==="loading"?(
        <p role="status" className="mt-6 flex items-center gap-2 text-sm"><LoaderCircle className="size-4 animate-spin"/> Checking secure checkout availability…</p>
      ):availability==="disabled"?(
        <div role="status" className="mt-6 rounded-xl border border-[#dce4ef] bg-[#f3f7fc] p-5 text-sm leading-7">
          Secure online contributions are not yet enabled for live payments. Please <a className="font-semibold text-[#1f5bbd] underline" href="/contact">contact Amaris</a> to discuss supporting the project. We are not collecting card details on this page.
        </div>
      ):(
        <form className="mt-6 grid gap-5" onSubmit={submit}>
          <div>
            <label htmlFor="donor-amount" className="text-sm font-semibold">Contribution amount (ZAR)</label>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {amounts.map(value=><button key={value} type="button" aria-pressed={amount===value} onClick={()=>setAmount(value)}
                className={`min-h-11 rounded-xl border px-3 text-sm font-bold ${amount===value?"border-[#0b2a5b] bg-[#0b2a5b] text-white":"border-[#c9d5e5] bg-white text-[#07152d]"}`}>R{value}</button>)}
            </div>
            <input id="donor-amount" name="amount" type="number" min="20" max="100000" step="0.01" required value={amount}
              onChange={e=>setAmount(e.target.value)} className="mt-3 min-h-12 w-full rounded-xl border border-[#c9d5e5] px-4" />
          </div>
          <label className="grid gap-2 text-sm font-semibold">Support category
            <select name="purpose" required className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal">
              {purposes.map(p=><option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-semibold">Your name
            <input name="donor_name" autoComplete="name" required minLength={2} maxLength={100} className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"/>
          </label>
          <label className="grid gap-2 text-sm font-semibold">Email for payment acknowledgement
            <input name="donor_email" type="email" autoComplete="email" required maxLength={254} className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"/>
          </label>
          <label className="flex items-start gap-3 text-sm leading-6">
            <input name="consent" type="checkbox" required className="mt-1 size-4 accent-[#0b2a5b]"/>
            <span>I understand that this is a voluntary contribution, not a course purchase, and no Section 18A tax-deductible receipt is promised. I agree to be redirected to PayFast for payment.</span>
          </label>
          {error?<p role="alert" className="text-sm font-semibold text-red-700">{error}</p>:null}
          <button disabled={busy} type="submit" className="flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white disabled:opacity-50">
            {busy?<LoaderCircle className="size-5 animate-spin"/>:<LockKeyhole className="size-5"/>}
            {busy?"Preparing checkout…":"Review secure contribution"}
          </button>
          <p className="text-xs leading-5 text-[#526781]">Payment status is confirmed only by PayFast’s verified server notification. We never ask for card details on Amaris.</p>
        </form>
      )}
    </section>
  );
}
