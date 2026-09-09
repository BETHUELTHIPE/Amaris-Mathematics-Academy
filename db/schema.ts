import { sql } from "drizzle-orm";
import { integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const studentProfiles = sqliteTable("student_profiles", {
  userId: text("user_id").primaryKey(),
  email: text("email").notNull(),
  displayName: text("display_name").notNull(),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});

export const courseProgress = sqliteTable(
  "course_progress",
  {
    id: text("id").primaryKey(),
    userId: text("user_id").notNull(),
    courseSlug: text("course_slug").notNull(),
    completedLessons: integer("completed_lessons").notNull().default(0),
    lastLesson: text("last_lesson").notNull().default("Getting started"),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [uniqueIndex("course_progress_user_course_idx").on(table.userId, table.courseSlug)],
);

export const contactEnquiries = sqliteTable("contact_enquiries", {
  id: text("id").primaryKey(),
  fullName: text("full_name").notNull(),
  email: text("email").notNull(),
  phone: text("phone"),
  enquiryType: text("enquiry_type").notNull(),
  message: text("message").notNull(),
  consentGiven: integer("consent_given", { mode: "boolean" }).notNull().default(false),
  status: text("status").notNull().default("new"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});
