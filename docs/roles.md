# Roles and access

Romule has **two roles**, and no more. An administrator changes settings and
manages accounts. Everybody else gets the library and the actions that go with
it — send to the console, convert, move to the trash.

There is no third role, and no per-feature permission matrix. A self-hosted
library manager used by a household or a small team does not need one, and
every permission you cannot explain is a permission nobody will set correctly.

## Three modes, and what a role means in each

| Mode | Who gets in | Who administers |
|---|---|---|
| **No authentication** (default) | anyone who can reach the port | everyone |
| **Internal accounts** | anyone with an account | accounts marked administrator |
| **OpenID Connect** ([beta](beta.md)) | whoever your provider allows, narrowed by `oidc_emails` / `oidc_groupes` | members of `oidc_admin_groupes` |

!!! info "With no authentication, everyone is an administrator"
    That is not an oversight — it is the most common way Romule runs, on a home
    network, by one person. There is no identity to check, so there is nothing
    to distinguish. The built-in audit reports it at every start, because it is
    worth knowing rather than worth hiding.

## Internal accounts

The **first account created is the administrator**, and it can only be created
from the machine hosting the library. Without that restriction, “the first
account is the administrator” would mean “the first person on the network
becomes the administrator”.

An administrator can promote another account. Romule refuses to remove the last
administrator: an instance nobody can administer is an instance you have to
repair by hand, in a file.

## OpenID Connect: two different questions

`oidc_groupes` says **who may get in**. `oidc_admin_groupes` says **who may
administer**. Confusing them would hand administration to everyone your
provider authenticates.

```
oidc_groupes        = romule-users      ← may open the library
oidc_admin_groupes  = romule-admins     ← may open Settings
```

**Empty means nobody.** If `oidc_admin_groupes` is not set, no SSO session is
administrative. A blank setting must never mean “everyone”.

The role is read from the identity token **when the session starts**. Removing
someone from a group demotes them at their **next** sign-in, not in the middle
of the current one — the alternative would be to call your provider on every
request. This is how most SSO integrations behave; it is stated here rather
than assumed.

!!! tip "You will not lock yourself out"
    Turning on authentication from an already-authorised browser hands that
    browser a 30-minute pass, so you can finish configuring — including setting
    `oidc_admin_groupes` — before anything demands a role you have not granted
    yet.

## What a non-administrator cannot do

Thirty-three routes are reserved server-side. They fall into seven groups:

- **erase or restore data** — restoring a backup puts the accounts file back,
  which would hand administration back to whoever lost it;
- **move files in bulk** — reorganising the library or the console;
- **write into another program's files** — emulator configuration, NAND;
- **change the link to the console** — Wi‑Fi pairing, forgetting a device;
- **choose where the service reads and writes on the host** — the folder
  picker, the library location, and the list of consoles. Browsing the host's
  filesystem is a disclosure primitive, so it is treated as one; declaring a
  console changes eight settings at once, which is the same thing by another
  route;
- **send outward in the service's name** — [notification](configuration.md#notifications)
  destinations. A Discord webhook is a bearer secret: whoever holds it can post
  in the channel. Testing an arbitrary address is also a port scanner by proxy,
  which is its own reason;
- **reveal who connects, and the security posture** — access log, audit.

The interface hides what the role cannot use: a non-administrator does not see
the Settings tab. That is a courtesy, **not** the security boundary. The server
refuses regardless of what the interface shows, and the test suite checks all
thirty-three routes against an ordinary account — for internal accounts and for
SSO sessions alike.

## API keys are a third thing

An [API key](api.md) is neither an account nor a role. It reaches `/api/v1/`
and nothing else: it cannot open the interface, read the configuration, or
touch accounts.

Presenting a key does not *grant* rights, it *selects a regime*. A request from
`127.0.0.1` normally gets full local access — but the moment it carries
`X-Api-Key`, the key decides, and the key is scoped. A key can never widen an
access; at most it narrows one.
