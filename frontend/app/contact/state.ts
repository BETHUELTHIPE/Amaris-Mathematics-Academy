export type EnquiryState = {
  status: "idle" | "success" | "error";
  message?: string;
  errors?: Record<string, string>;
};

export const initialEnquiryState: EnquiryState = { status: "idle" };
