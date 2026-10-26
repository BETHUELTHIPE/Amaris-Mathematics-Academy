import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const mock = `
export const state = {};
export async function requireVerifiedStudent() {
  if (state.guest) throw Object.assign(new Error("NEXT_REDIRECT"), {digest:"NEXT_REDIRECT;replace;/login?next=%2Faccount%2Fcomplete-profile;307;"});
  return { id: "verified-account", email: "verified@example.test" };
}
export function registeredBookingName(metadata) {
  const firstName = String(metadata?.first_name || "").trim();
  const lastName = String(metadata?.last_name || "").trim();
  return firstName.length < 2 || lastName.length < 2 ||
    (firstName.toLowerCase() === "student" && lastName.toLowerCase() === "learner")
    ? null : {firstName,lastName,fullName:firstName+" "+lastName};
}
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
const stubbed = new Set(["@/lib/auth","@/lib/supabase/server","@/lib/registered-booking-name","test:profile"]);
const vite = await createServer({
  appType:"custom", configFile:false, root:fileURLToPath(new URL("..",import.meta.url)),
  plugins:[{
    name:"isolate-profile-account",
    enforce:"pre",
    resolveId(id){if(stubbed.has(id))return "\0test:profile";},
    load(id){if(id==="\0test:profile")return mock;}
  }],
  server:{middlewareMode:true,hmr:false,ws:false}
});
const {state} = await vite.ssrLoadModule("test:profile");
const {completeStudentBookingProfile} = await vite.ssrLoadModule("/app/account/complete-profile/actions.ts");
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
