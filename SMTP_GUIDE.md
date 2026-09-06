# Email (SMTP) Configuration Guide

The website needs to send real emails for: contact-form replies, complaint replies, forgot-password codes,
email-change verification codes, and new-account login details. Without this set up, those features will
tell you clearly that email isn't configured instead of failing silently.

## Recommended: Gmail

1. Use a Gmail address (a dedicated one for the school is best, e.g. the one already in use:
   `r21871928@gmail.com`, or any Gmail account you control).
2. Go to **myaccount.google.com → Security → 2-Step Verification** and turn it **ON**. This is required —
   Gmail will not allow the next step without it.
3. Go to **myaccount.google.com → Security → App Passwords**.
4. Create a new app password, name it something like "MMIC Website", and copy the 16-character code it
   generates (it looks like `abcd efgh ijkl mnop`).
5. In the website: log in as **Super Admin → Email Settings**, and fill in:
   - **SMTP Host**: `smtp.gmail.com`
   - **SMTP Port**: `587`
   - **Email Address**: your full Gmail address
   - **SMTP Password**: the 16-character App Password from step 4 (⚠️ not your normal Gmail password —
     that will not work and Google will block the login attempt)
   - **From Name**: whatever you want visitors to see, e.g. "Mahamana Malviya Inter College"
6. Click **Save Email Settings**, then use the **Send a Test Email** box lower on the same page to confirm
   it works before relying on it.

## Using a different provider
Any standard SMTP provider works (Outlook/Office365, Zoho Mail, a hosting provider's email, etc.) — you
just need its SMTP host and port (usually 587 for TLS). The steps are the same, just skip the
Gmail-specific App Password step and use the credentials your provider gives you.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| "Could not send email: (535, ...)" | Wrong password — for Gmail, make sure you used the App Password, not your regular password. |
| "Could not send email: [Errno 11001] getaddrinfo failed" | No internet connection on the machine running the site, or wrong SMTP host spelling. |
| Test email never arrives | Check spam/junk folder first. Also double-check the address you sent the test to. |
| "Email is not set up yet" message anywhere | Email Settings hasn't been saved yet, or one of Host/Port/Username/Password is blank. |
