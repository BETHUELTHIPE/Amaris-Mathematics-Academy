"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Bot, Square, Volume2 } from "lucide-react";

const lessons = [
  {
    title: "Welcome to Amaris!",
    lead: "We help people learn mathematics online, one clear step at a time.",
    points: ["Learn from home or another suitable place.", "Find courses for school, college and university.", "Ask for help when you need it."],
    spoken: "Hello, and welcome to Amaris Mathematics Academy. We want to make learning clearer and easier to follow. You do not need to know anything about technology to get started.",
  },
  {
    title: "Who can study with us?",
    lead: "We welcome different types of students, including busy adults.",
    points: ["CAPS and IEB school learners.", "People preparing for Matric upgrades.", "TVET and university students.", "People balancing studies with work."],
    spoken: "Amaris supports school learners, people improving their Matric results, TVET college students, and university students. Working adults can also ask about suitable lesson times. Available classes depend on the tutor timetable.",
  },
  {
    title: "How do I join?",
    lead: "Start by opening a student account.",
    points: ["Select Register on the website.", "Enter your details and confirm your email.", "Sign in and choose the learning option you need."],
    spoken: "To join Amaris, open the Register page and create your account. Follow the email verification steps. Then sign in and look at the courses or classes you want to attend.",
  },
  {
    title: "How do I book a lesson?",
    lead: "Choose a subject, check an available tutor time, then book.",
    points: ["Select your programme, grade or level, and topic.", "Check the tutor's available date and time.", "Read the price before you pay."],
    spoken: "To book a live lesson, select your programme and subject. Choose the level and topic you need help with. Check the available tutor times carefully. Live lessons are subject to actual tutor availability.",
  },
  {
    title: "How do payments work?",
    lead: "The website must confirm your payment before giving paid access.",
    points: ["Review the amount before you pay.", "Follow the secure PayFast payment steps.", "Wait for the confirmed booking or course access."],
    spoken: "Before paying, please check the full price. Amaris uses PayFast to process payments. Paid lessons or course access should be given only after the payment is verified. If a payment looks stuck, ask for help before paying again.",
  },
  {
    title: "How do online lessons work?",
    lead: "Study online and follow the learning steps on your dashboard.",
    points: ["Open the courses you have access to.", "Continue your lessons and track progress.", "Join a confirmed Zoom class using its approved details."],
    spoken: "Your student dashboard is designed to show your learning. You can open authorised course materials and continue your lessons. For a booked live class, use the Zoom details given after your booking is confirmed.",
  },
  {
    title: "What if I work during the day?",
    lead: "You can ask about learning options that fit your schedule.",
    points: ["Ask about available early or late tutor slots.", "Look at suitable learning materials.", "Plan study time around your work and family."],
    spoken: "Many students also work. You can ask Amaris about lessons before or after work, or use suitable learning materials at your own pace. Live tutor availability is not guaranteed at every hour.",
  },
  {
    title: "How can I get help?",
    lead: "Our website has an assistant, and you can contact our team.",
    points: ["Tap the Amaris Assistant button to type or speak a question.", "Visit Contact if you need personal support.", "Do not share passwords, bank card details, or verification codes."],
    spoken: "If you are unsure, choose the Amaris Assistant button at the bottom of the page. You can use chat or voice where your browser supports it. Answers depend on the assistant service being available. You can also use our Contact page for help.",
  },
] as const;

export function AiGuideTour() {
  const [index, setIndex] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [message, setMessage] = useState("Select Listen to hear this explanation.");
  const current = lessons[index];

  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  function stop() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setSpeaking(false);
  }

  function move(next: number) {
    stop();
    setMessage("Select Listen to hear this explanation.");
    setIndex(Math.max(0, Math.min(lessons.length - 1, next)));
  }

  function listen() {
    if (typeof window === "undefined" || !("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      setMessage("Voice playback is not supported in this browser. You can read the words on the screen.");
      return;
    }
    stop();
    const utterance = new SpeechSynthesisUtterance(current.spoken);
    utterance.lang = "en-ZA";
    utterance.rate = 0.92;
    utterance.onstart = () => { setSpeaking(true); setMessage("Reading this step aloud…"); };
    utterance.onend = () => { setSpeaking(false); setMessage("Finished reading. You can continue to the next step."); };
    utterance.onerror = () => { setSpeaking(false); setMessage("The voice could not play. Please read the explanation instead."); };
    window.speechSynthesis.speak(utterance);
  }

  return (
    <section className="rounded-3xl border border-[#dce4ef] bg-white p-6 shadow-[0_18px_55px_rgba(7,21,45,.06)] sm:p-10" aria-labelledby="ai-guide-step-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-bold uppercase tracking-wide text-[#1f5bbd]">Step {index + 1} of {lessons.length}</p>
        <span className="inline-flex items-center gap-2 text-sm text-[#60708a]"><Bot className="size-4" aria-hidden="true" /> Client speaking guide</span>
      </div>
      <h2 id="ai-guide-step-title" className="mt-5 text-3xl font-semibold tracking-tight text-[#07152d] sm:text-4xl">{current.title}</h2>
      <p className="mt-4 max-w-3xl text-base leading-8 text-[#526781]">{current.lead}</p>
      <ul className="mt-6 grid gap-3">
        {current.points.map((point) => <li key={point} className="rounded-xl bg-[#f3f7fc] px-5 py-3 text-sm leading-6 text-[#243852]">{point}</li>)}
      </ul>
      <div className="mt-7 flex flex-wrap gap-3">
        <button type="button" onClick={() => move(index - 1)} disabled={index === 0} className="inline-flex min-h-12 items-center gap-2 rounded-full border border-[#c9d5e5] px-5 py-2 text-sm font-semibold text-[#0b2a5b] hover:bg-[#edf3ff] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"><ArrowLeft className="size-4" aria-hidden="true" /> Previous</button>
        <button type="button" onClick={() => move(index + 1)} disabled={index === lessons.length - 1} className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-2 text-sm font-semibold text-white hover:bg-[#1f5bbd] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]">Next step <ArrowRight className="size-4" aria-hidden="true" /></button>
        <button type="button" onClick={listen} className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#ffcc66] px-5 py-2 text-sm font-semibold text-[#07152d] hover:bg-[#ffe09a] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"><Volume2 className="size-4" aria-hidden="true" /> Listen</button>
        <button type="button" onClick={() => { stop(); setMessage("Voice stopped."); }} disabled={!speaking} className="inline-flex min-h-12 items-center gap-2 rounded-full border border-[#c9d5e5] px-5 py-2 text-sm font-semibold text-[#0b2a5b] hover:bg-[#edf3ff] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"><Square className="size-3" aria-hidden="true" /> Stop voice</button>
      </div>
      <p role="status" aria-live="polite" className="mt-4 text-sm text-[#60708a]">{message}</p>
      <p className="mt-3 text-xs leading-5 text-[#60708a]">Voice playback uses the speech feature in your browser. This step-by-step explanation is prepared information, not a live AI answer.</p>
    </section>
  );
}
