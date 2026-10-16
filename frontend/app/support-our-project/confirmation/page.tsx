import type { Metadata } from "next";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { DonationConfirmation } from "@/components/site/donation-confirmation";

export const metadata:Metadata={title:"Contribution Status — Amaris Mathematics Academy"};

export default async function SupportConfirmationPage({searchParams}:{searchParams:Promise<{reference?:string}>}){
  const query=await searchParams;
  const reference=query.reference||"";
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header/>
      <div className="px-5 py-16 lg:py-24">
        {/^DON-[A-Za-z0-9_-]{12,64}$/.test(reference)?
          <DonationConfirmation reference={reference}/>:
          <p className="mx-auto max-w-xl rounded-2xl bg-white p-8 text-center">The contribution reference is missing or invalid.</p>}
      </div>
      <Footer/>
    </main>
  );
}
