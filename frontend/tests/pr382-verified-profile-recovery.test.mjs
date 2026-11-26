import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const mock = `
export const state = {};
export async function requireVerifiedStudent() {
  if (state.guest) throw Object.assign(new Error("NEXT_REDIRECT"), {digest:"NEXT_REDIRECT;replace;/login?next=%2Faccount%2Fcomplete-profile;307;"});
  return { id: "verified-account", email: "verified@example.test" };
}
export async function createStudentLiveClassCheckout(slotId, topic, attempt) {
  state.checkout = {slotId, topic, attempt};
  return {
    booking_reference: "LCB-SYNTHETIC",
    gateway_url: "https://sandbox.payfast.co.za/eng/process",
    booking: {
      tutor: "Tutor Example", programme: "CAPS", subject: "Mathematics", level: "Grade 12", topic,
      starts_at: "2026-12-01T13:00:00Z", duration_minutes: 60, amount: "250.00",
    },
  };
}
export function Header() { return null; }
export function Footer() { return null; }
export function PayFastHostedCheckout() { return null; }
export default function Link({children}) { return children; }
export async function createSupabaseServerClient() {
  const client = {
    auth: {
      getUser: async () => ({data: {user: {
        id: state.otherAccount ? "another-account" : "verified-account",
        email_confirmed_at: state.unverified ? null : "2026-10-26T10:00:00Z",
        user_metadata: state.metadata || {first_name:"Student",last_name:"Learner"},
      }},error:state.readError || null}),
      updateUser: async input => {
        state.update = input;
        if (state.updateError) return {error:state.updateError};
        state.metadata = {...state.metadata,...input.data};
        return {error:null};
      },
    },
  };
  return client;
}
`;
const stubbed = new Set([
  "@/lib/auth", "@/lib/supabase/server", "@/lib/student-api",
  "@/components/site/header", "@/components/site/footer", "@/components/site/payfast-hosted-checkout",
  "next/link", "server-only", "test:profile",
]);
const root = fileURLToPath(new URL("..", import.meta.url));
const vite = await createServer({
  appType:"custom", configFile:false, root,
  plugins:[{
    name:"isolate-profile-account",
    enforce:"pre",
    resolveId(id) {
      if (id === "@/lib/registered-booking-name") return root + "/lib/registered-booking-name.ts";
      if (stubbed.has(id)) return "\0test:profile";
    },
    load(id){if(id==="\0test:profile")return mock;}
  }],
  server:{middlewareMode:true,hmr:false,ws:false}
});
const {state} = await vite.ssrLoadModule("test:profile");
const {completeStudentBookingProfile} = await vite.ssrLoadModule("/app/account/complete-profile/actions.ts");
const {default: LiveClassCheckoutPage} = await vite.ssrLoadModule("/app/book-online-live-class/checkout/page.tsx");
after(()=>vite.close());
beforeEach(()=>{for(const key of Object.keys(state))delete state[key];});
async function destination(form){
  let url;
  await assert.rejects(completeStudentBookingProfile(form),error=>{
    assert.equal(error.message,"NEXT_REDIRECT");
    url=new URL(error.digest.split(";")[2],"https://academy.example.test");
    return true;
  });
  return url;
}
function form(firstName="Amara",lastName="Ndlovu"){
  const data=new FormData();
  data.set("firstName",firstName);
  data.set("lastName",lastName);
  return data;
}
test("verified student updates OWN registered Supabase metadata and returns to booking",async()=>{
  const result=await destination(form());
  assert.equal(result.pathname,"/book-online-live-class");
  assert.deepEqual(state.update,{data:{first_name:"Amara",last_name:"Ndlovu"}});
});
test("unverified or mismatched student cannot change registration names",async()=>{
  state.unverified=true;
  assert.equal((await destination(form())).pathname,"/account/complete-profile");
  assert.equal(state.update,undefined);
  state.unverified=false;
  state.otherAccount=true;
  assert.equal((await destination(form())).pathname,"/account/complete-profile");
  assert.equal(state.update,undefined);
});
test("incomplete, generic, markup and numeric names cannot be saved",async()=>{
  for(const [a,b] of [["Student","Learner"],["A","Smith"],["<script>","Smith"],["Amara","12345"],["","Smith"]]){
    assert.equal((await destination(form(a,b))).pathname,"/account/complete-profile");
    assert.equal(state.update,undefined);
  }
});
test("provider failures fail closed and do not permit checkout",async()=>{
  state.readError={message:"network"};
  assert.equal((await destination(form())).pathname,"/account/complete-profile");
  assert.equal(state.update,undefined);
  state.readError=null;
  state.updateError={message:"network"};
  assert.equal((await destination(form())).pathname,"/account/complete-profile");
});
test("checkout still reads registration identity on the server, never form-provided payment names",()=>{
  const booking=readFileSync(new URL("../app/book-online-live-class/page.tsx",import.meta.url),"utf8");
  const checkout=readFileSync(new URL("../app/book-online-live-class/checkout/page.tsx",import.meta.url),"utf8");
  const update=readFileSync(new URL("../app/account/complete-profile/actions.ts",import.meta.url),"utf8");
  assert.match(booking,/href="\/account\/complete-profile"/);
  assert.match(checkout,/getVerifiedStudentBookingName\(student\.id\)/);
  assert.match(update,/supabase\.auth\.updateUser/);
  assert.doesNotMatch(update,/form\.get\("userId"\)|form\.get\("email"\)|form\.get\("role"\)/);
});

function checkoutPage() {
  return LiveClassCheckoutPage({
    searchParams: Promise.resolve({
      slot: "00000000-0000-4000-8000-000000000301",
      topic: "Algebra",
      attempt: "00000000-0000-4000-8000-000000000302",
      firstName: "Submitted",
      lastName: "Identity",
    }),
  });
}

test("direct checkout requires the account name before asking Django to reserve a slot", async () => {
  await assert.rejects(checkoutPage(), error =>
    error.message === "NEXT_REDIRECT" && error.digest.split(";")[2] === "/account/complete-profile",
  );
  assert.equal(state.checkout, undefined);
});

test("checkout blocks a mismatched or unverified account before creating a hold", async () => {
  state.metadata = {first_name: "Amara", last_name: "Ndlovu"};
  for (const account of ["otherAccount", "unverified", "readError"]) {
    state[account] = true;
    await assert.rejects(checkoutPage(), error =>
      error.message === "NEXT_REDIRECT" && error.digest.split(";")[2] === "/account/complete-profile",
    );
    assert.equal(state.checkout, undefined);
    delete state[account];
  }
});

test("verified checkout uses the registered name and sends only booking choices to Django", async () => {
  state.metadata = {first_name: "Amara", last_name: "Ndlovu"};
  const html = renderToStaticMarkup(await checkoutPage());
  assert.match(html, /Registered student.*Amara Ndlovu/);
  assert.doesNotMatch(html, /Submitted Identity/);
  assert.deepEqual(state.checkout, {
    slotId: "00000000-0000-4000-8000-000000000301",
    topic: "Algebra",
    attempt: "00000000-0000-4000-8000-000000000302",
  });
});
