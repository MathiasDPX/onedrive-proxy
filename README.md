# OneDrive Proxy

OneDrive Proxy is a proxy service that allows you to make OneDrive file downloads available without requiring users to sign in with a Microsoft account.

## Features

- Choose who can access files with strong regex rules
- Fast & easy to setup
- ACL-like rights management with users and groups
- Lightweight web interface for easy usage
- Dropbox for fast and easy files uploading

## Setup

There are two config files that you need to modify before running this. The first one is `.env` (from `example.env`) where you need to put your OneDrive authentication credentials. The other is `rules.yml` (from `rules.example.yml`) which contains rules on who can access what.

```yaml
users:
  joe: "bcrypt_password"

groups:
  admins:
    - joe

rules:
  # Give the user 'joe' access to every files
  - permit: ALLOW
    principal: "user:joe"
    pattern: ".+"
    
  # This rule allows everyone to read the files in /public
  - permit: ALLOW
    principal: "group:everyone"
    pattern: "\\/public(\\/[a-zA-Z0-9_-]+\\.[a-zA-Z0-9]+)?"
```

### Groups
A group is a collection of multiple users (e.g. `admins`, `archive-team`). There are also special groups like `everyone` which includes all users (logged in or not), `logged` which includes only authenticated users and the `dropbox` group have access to the dropbox

### Users
A user is the association of a username (key) and a password (value). On startup, a `logged` group is created which every user is part of. You can login at `/auth`.

### Rules
Each rule has 3 values:
- permit: Can be `ALLOW` or `DENY`. You can allow a user to see a folder but deny access to one of its children.
- principal: Should start with `user:` or `group:`. It describes who the rule is for.
- pattern: Every file matching this regex pattern will be affected by the rule.