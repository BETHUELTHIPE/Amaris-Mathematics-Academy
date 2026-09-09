CREATE TABLE `course_progress` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`course_slug` text NOT NULL,
	`completed_lessons` integer DEFAULT 0 NOT NULL,
	`last_lesson` text DEFAULT 'Getting started' NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `course_progress_user_course_idx` ON `course_progress` (`user_id`,`course_slug`);--> statement-breakpoint
CREATE TABLE `student_profiles` (
	`user_id` text PRIMARY KEY NOT NULL,
	`email` text NOT NULL,
	`display_name` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
