export type ChatRole = "student" | "tutor";
export type Message = {
  id: string;
  sender: ChatRole | "admin";
  text: string;
  sent_at: string;
};
export type MessagePage = { messages: Message[]; has_more: boolean };
export type BookingRoom = {
  id: string;
  topic: string;
  participant: string;
  starts_at: string;
  assignment: string;
};
export type ChatRooms = {
  role: ChatRole;
  bookings: BookingRoom[];
  has_next: boolean;
};

export const MESSAGE_MAX_LENGTH = 2000;
export const BOOKING_ROOM_ID = /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i;
