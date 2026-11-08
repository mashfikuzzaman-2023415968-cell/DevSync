# Demo tools

Where to find the codes and messages DevSync would normally send to a phone or an inbox. These
exist only in development, in the test environment and on the offline demo stack (`make demo-up`).
In a real deployment they are not there.

## SMS inbox (phone codes)

Open **https://localhost/sandbox/sms** in a second window (https://localhost:8443 on the test
stack). It shows:

- the **newest code** in large type with a Copy button;
- every text, newest first, with its number, time and a copy button;
- a **filter by number** (type any part of it; `+` and spaces are ignored);
- **Live**, on by default, checks for new texts every 3 seconds (switch it off to freeze the list);
- **Clear inbox** to start a demo from an empty list.

A typical demo: register on `/register`, put `/sandbox/sms` on a second screen, read the code
there and type it on the verify page. It keeps the newest 100 texts for six hours.

If the page says "The SMS inbox is off here", the server is not in one of those environments.

## Email

Mailpit, the local mail catcher, shows every email (verification and reset links, invitations):
**http://127.0.0.1:8025**. The SMS inbox page links to it.

## Notes

- The inbox has no sign-in on purpose (the first code is read before an account exists), so it is
  only for machines you control. See `DECISIONS.md` D76 and
  `docs/security-reviews/role-assessment.md` for what it exposes.
- Administrators' sign-in codes come from an authenticator app (TOTP), not SMS, so they never
  appear here.
