# Testing Checklist

Use this after any update to the code, or periodically, to confirm nothing is broken.

## Public Website
- [ ] Homepage loads, hero section shows correctly
- [ ] Translate button switches English / Hindi / Sanskrit
- [ ] Notice ticker scrolls, closes with the ✕ button, becomes sticky on scroll
- [ ] About, Principal, Teachers, Gallery, Notices sections all display
- [ ] Clicking a gallery/teacher/principal photo opens the fullscreen zoom viewer
- [ ] Admission form submits successfully and shows a success message
- [ ] Complaint form submits and returns a complaint code
- [ ] Contact form submits successfully
- [ ] Site looks correct on mobile width (resize browser or use device toolbar)

## Login & Security
- [ ] Logging in with correct credentials works
- [ ] Logging in with wrong password shows an error, does not log in
- [ ] 5 wrong passwords in a row locks the account for 15 minutes
- [ ] "Forgot password?" sends a code to the account's email, and the code resets the password
- [ ] A weak new password (e.g. `abc123`) is rejected with a clear reason
- [ ] Session logs out automatically after ~30 minutes of inactivity
- [ ] Disabling an account (via Manage Team) immediately blocks that user's next action

## Role Access
- [ ] **Super Admin** can open Website Customization, Manage Team, Email Settings, Activity Log, Backup & Restore
- [ ] **Admin** dashboard shows NO "Website Customization" button and NO design-related sidebar links
- [ ] **Admin** cannot open `/admin/cms`, `/admin/hero`, `/admin/branding`, `/admin/fonts`, `/admin/sections`,
      `/admin/content`, `/admin/teachers`, `/admin/gallery`, `/admin/team`, `/admin/email-settings`,
      `/admin/activity-log`, `/admin/backup` by typing the URL directly (should redirect with a message)
- [ ] **Admin** CAN open Admissions, Complaints, Contact Messages, Notices
- [ ] **Teacher** logging in lands on the Teacher Portal, not the main dashboard
- [ ] **Teacher** can only see Notifications, Admission Requests (view-only), Notices — nothing else
- [ ] **Teacher** typing an admin URL directly (e.g. `/admin/hero`) gets redirected, not shown the page

## Website Customization CMS (Super Admin)
- [ ] Changing the Home Designing eyebrow/tagline reflects on the public homepage immediately
- [ ] Uploading a hero image shows as the homepage background (not just text)
- [ ] Logo upload (with crop tool) shows in the top-left of the public site
- [ ] Founder photo upload shows as homepage watermark + admin login background
- [ ] Font/Typography changes (family, size, color) visibly change the public site
- [ ] Toggling a Homepage Section off hides it from the public site, and back on restores it
- [ ] Adding/editing a teacher shows on the public Teachers section
- [ ] Uploading a gallery photo shows on the public Gallery section

## Email
- [ ] Email Settings "Send Test" successfully delivers an email once SMTP is configured
- [ ] Replying to a Contact Message actually emails the sender (not just saves to database)
- [ ] Replying to a Complaint actually emails the sender
- [ ] Creating a new team member account emails them their login details
- [ ] Email-change flow: code arrives at OLD email, then code arrives at NEW email, then both addresses
      get a confirmation once complete

## Data Safety
- [ ] Creating a backup produces a downloadable `.db` file
- [ ] Restoring a backup works and creates a `before_restore_...` safety file automatically
- [ ] Activity Log records logins, logouts, and content changes with correct usernames and timestamps
