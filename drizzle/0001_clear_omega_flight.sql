CREATE TABLE `contact_enquiries` (
	`id` text PRIMARY KEY NOT NULL,
	`full_name` text NOT NULL,
	`email` text NOT NULL,
	`phone` text,
	`enquiry_type` text NOT NULL,
	`message` text NOT NULL,
	`consent_given` integer DEFAULT false NOT NULL,
	`status` text DEFAULT 'new' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
