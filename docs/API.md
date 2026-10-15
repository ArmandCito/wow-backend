# WOW Quick Bites API — reference

Base URL: `https://wow-quick-bites-backend-ziwt.onrender.com/api/v1` (local: `http://127.0.0.1:8000/api/v1`).
Interactive documentation, always up to date with the code: **`/api/docs/`** (Swagger), `/api/redoc/`,
raw schema `/api/schema/`.

This document explains the rules behind the endpoints. The exact fields of every request and
response are in Swagger.

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Format | JSON, **camelCase keys** (`isNew`, `clientCode`). Python code stays snake_case: the conversion is automatic (`djangorestframework-camel-case`). |
| Trailing slash | Optional: `/auth/sign-in` and `/auth/sign-in/` both work. |
| Bilingual text | `{"en": "Burger", "fr": "Burger"}` (type `Localized` on the website). On write, a language sent empty is translated with DeepL (or copied without a DeepL key). |
| Money | Integers in RWF (`6000`). Never decimals. |
| Dates | ISO 8601 in Kigali time: `"2026-10-06T12:18:00+02:00"`. Stored in UTC. |
| Ids | Readable strings: menu items and categories use slugs (`wow-toasted-burger`), orders `ORD-1042`, clients their code `WQB001A`, staff their staff id (`eric`). Numeric database ids are never exposed. |
| Lists | Plain arrays, except the audit trail: `{items, nextCursor}`. |
| Caching | Public catalogue endpoints send `Cache-Control: public, max-age=60, stale-while-revalidate=600`. |

### Authentication

`POST /auth/sign-in` (and every other sign-in) returns:

```json
{ "access": "<jwt>", "refresh": "<jwt>", "user": SessionUser }
```

- Send `Authorization: Bearer <access>` on every protected request. The access token lives **60 minutes**.
- When a request answers `401 unauthenticated`, call `POST /auth/refresh {refresh}`: it returns a **new
  pair**. Keep the new refresh token: the old one is revoked (rotation). The refresh token lives **7 days**.
- `POST /auth/sign-out {refresh}` revokes the refresh token.
- Permissions are **never read from the token**: they are recomputed from the database on every request.
  A suspended manager is refused immediately (`403 account_suspended`), and a new content grant applies
  on the manager's next request.

```ts
type SessionUser = {
  id: string;               // client code ("WQB001A") or staff id ("eric")
  role: "client" | "manager" | "superadmin";
  name: string;
  email: string;
  phone: string | null;     // "078 123 4567"
  clientCode: string | null;
  permissions: Permission[];
  contentGrant: ContentGrant | null;   // managers with a grant in force
};
type Permission = "overview:view" | "orders:process" | "menu:edit" | "labels:edit"
  | "ads:manage" | "content:publish" | "managers:manage" | "business:edit";
type ContentGrant = { grantedBy: string; scopes: ("food" | "drinks" | "labels" | "ads" | "publish")[];
  startsAt: string; expiresAt: string | null };
```

### Calls from the website server

The website calls the API from its server (Next.js), never from the browser. Two headers matter:

| Header | When | Why |
|---|---|---|
| `X-Frontend-Secret: <FRONTEND_SHARED_SECRET>` | Every call | Proves the call comes from the website server. Required by `POST /auth/google`. |
| `X-Client-IP: <visitor IP>` | Sign-in, sign-up, codes, password reset, checkout | Rate limits are per visitor. Without it, every visitor shares the website server's IP and limit. Trusted only together with the secret. |

### Errors

Every error has the same shape:

```json
{ "error": { "code": "invalid_transition", "message": "For logs, in English", "details": { "from": "new", "to": "ready" } } }
```

The website translates `code` (never shows `message`). Codes are stable.

| Status | Codes |
|---|---|
| 400 | `bad_request` (malformed JSON), `invalid_code`, `invalid_or_expired_token` |
| 401 | `unauthenticated` (missing/expired token → refresh), `invalid_credentials` |
| 403 | `forbidden`, `account_suspended`, `not_assigned`, `staff_password_only` |
| 404 | `not_found` (also "exists but is not yours") |
| 409 | `conflict`, `email_taken`, `invalid_transition`, `item_unavailable`, `manager_suspended` |
| 410 | `code_expired` |
| 422 | `validation_failed` — `details` maps each field to a reason: `{"email": "invalid", "lines.0.choices": "invalid_choice"}` |
| 429 | `too_many_attempts` — `details.retryAfter` (seconds) and a `Retry-After` header |
| 503 | `email_unavailable` (Brevo failed: try again) |

Field reasons in `validation_failed`: `required`, `invalid`, `blank`, `null`, `max_length`, `min_value`,
`max_value`, `invalid_choice`, `invalid_phone`, `does_not_exist`, `unique`, `read_only`,
`password_too_short`, `password_too_common`, `password_entirely_numeric`, `password_too_similar`,
`incorrect` (current password), `required_option_missing`, `too_many_choices`, `too_large`,
`invalid_image`, `unsupported_format`.

### Rate limits (per visitor)

| Scope | Limit | Endpoints |
|---|---|---|
| `sign_in` | 10 / minute | `/auth/sign-in` |
| `sign_up` | 20 / hour | `/auth/sign-up` |
| `email_code` | 30 / hour | `/auth/verify-email`, `/auth/verify-email/resend` |
| `password_reset` | 10 / hour | `/auth/password/*`, `/auth/invitations/accept` |
| `place_order` | 30 / hour | `POST /orders` |

Change them in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` (settings.py).

---

## 2. Roles and permissions

| Capability | Client | Manager | Manager + grant | Superadmin |
|---|---|---|---|---|
| Own orders and notifications | ✓ | – | – | – |
| Register queue, order details (`orders:process`) | – | ✓ | ✓ | ✓ |
| Move an order / confirm a payment | – | **assigned orders** | assigned orders | all |
| Edit menu items (`menu:edit`) | – | – | scope `food` and/or `drinks`, **only that group** | ✓ |
| NEW badge (`labels:edit`) | – | – | scope `labels` | ✓ |
| Campaigns (`ads:manage`) | – | – | scope `ads` | ✓ |
| Publish menu items and campaigns (`content:publish`) | – | – | scope `publish` | ✓ |
| Managers, grants, invitations, order assignment (`managers:manage`) | – | – | never | ✓ |
| Business settings (`business:edit`) | – | – | never | ✓ |
| Overview and audit (`overview:view`) | – | – | never | ✓ |

The rules live in one file: `accounts/access.py` (same as the website's `lib/auth/roles.ts`).

---

## 3. Endpoints

### Auth and profile

| Method & path | Who | Notes |
|---|---|---|
| `POST /auth/sign-up` `{name, email, phone, password, lang?}` | public | `202 {pendingVerification, email, expiresIn}`. Emails a **6-digit** code (10 min, 5 attempts). **Nothing is created yet.** Password: 8+ characters, not common, not only digits. Phone: Rwandan mobile, stored as `078 123 4567`. |
| `POST /auth/verify-email` `{email, code}` | public | `201 {access, refresh, user}`: creates the client account (client code assigned) and signs in. `invalid_code` has `details.attemptsLeft`. |
| `POST /auth/verify-email/resend` `{email, lang?}` | public | `202`. One code every 30 s (`429` otherwise). A new code replaces the previous one. |
| `POST /auth/sign-in` `{email, password}` | public | `200 {access, refresh, user}` |
| `POST /auth/refresh` `{refresh}` | public | `200 {access, refresh}` (rotation) |
| `POST /auth/sign-out` `{refresh}` | public | `204` |
| `GET /auth/me` (also `GET /me`) | signed in | `SessionUser` |
| `PATCH /me` `{name?, phone?}` | signed in | `SessionUser`. The email is not editable. |
| `POST /auth/password/forgot` `{email, lang?}` | public | `202` always. Emails `{FRONTEND_URL}/{lang}/forgot-password?token=…` (1 hour). |
| `POST /auth/password/reset` `{token, password}` | public | `204`. Signs the account out everywhere. |
| `POST /auth/password/change` `{currentPassword, newPassword}` | signed in | `200 {access, refresh, user}` (other sessions are signed out). |
| `POST /auth/google` `{email, name?}` + `X-Frontend-Secret` | website server | The website runs the OAuth flow and sends the **verified** Google email. `200` existing client, `201` new client, `403 staff_password_only` for staff. |
| `POST /auth/invitations/accept` `{token, password}` | public | `200 {access, refresh, user}`: an invited manager chooses a password. The email links to `{FRONTEND_URL}/{lang}/accept-invitation?token=…` (7 days). |

### Catalogue (public)

| Method & path | Response |
|---|---|
| `GET /menu` | Everything in one call: `{categories, drinkSections, tags, optionGroups, items}` |
| `GET /menu/items?group=food\|drinks&category=burgers&section=mojitos` | `MenuItem[]` |
| `GET /menu/items/{id}` | `MenuItem` · `404` |
| `GET /menu/categories` | `{id, name, icon}[]` |
| `GET /menu/drink-sections` | `{id, name, note}[]` |
| `GET /menu/tags` | `{ [key]: Localized }` |
| `GET /menu/option-groups` | `{ [id]: OptionGroup }` (only available choices) |
| `GET /promotions?placement=home-offers` | `Promotion[]`: campaigns published **and** inside their dates |
| `GET /business` | `{name, owner, location, hours, email, phone, socials, fees: {service, delivery}, queueWindowDays}` |

```ts
type MenuItem = {
  id: string; name: Localized; description: Localized; cartMeta: Localized | null;
  price: number; image: string; group: "food" | "drinks"; section: string | null;
  categories: string[]; tags: string[]; isNew: boolean;
  available: boolean;            // false = show greyed, cannot be ordered
  optionGroups: string[]; pairsWith: string | null;
};
type OptionGroup = { id: string; name: Localized; hint: Localized | null; kind: "add" | "remove";
  required: boolean; max: number | null; choices: { id: string; name: Localized; price: number }[] };
type Promotion = { id: string; kicker: Localized; title: Localized; text: Localized; cta: Localized;
  highlight: { label: Localized; value: Localized; labelFirst: boolean } | null;
  image: string; href: string; tone: "yellow" | "plain"; tag: string; placement: string;
  ctaCategory: string | null; schedule: Localized | null };
```

Only **published** items are public. `image` is an absolute URL for uploaded images, or a path served
by the website (`/images/burger.jpg`) for the seeded menu.

### Checkout and client orders

`POST /orders` — signed-in client (Bearer) **or guest** (no token):

```json
{
  "lines": [{ "itemId": "chips-marinated-chicken-leg", "quantity": 2, "choices": ["extra-cheese", "no-salt"], "note": "well done" }],
  "fulfilment": "pickup",
  "address": null,
  "payment": "pay-on-pickup",
  "contact": { "name": "Aline", "phone": "078 123 4567", "email": "aline@example.com" },
  "notes": null
}
```

- **The server computes every price** from the live menu: unit = item price + choice prices; `fees` =
  `business.fees.service` (+ `fees.delivery` for delivery). Names and prices are copied into the order:
  later menu changes never change past orders.
- Guests must send `contact.name` and `contact.phone`. A client may omit `contact`: the profile is used.
  A client without a phone must send one (it is then saved to the profile).
- `delivery` needs `address`.
- Choices must belong to the item's option groups (`invalid_choice`); required groups must be answered
  (`required_option_missing`); `max` is enforced (`too_many_choices`).
- `409 item_unavailable` → `details.itemIds` (unknown, unpublished or unavailable items).
- Staff accounts cannot order (`403`).
- The order is assigned to a manager (see §4) and gets `stage: "new"`, `paymentStatus: "pending"`.

Response `201 {"order": Order}`:

```ts
type Order = {
  id: string;                    // "ORD-1042"
  clientCode: string;            // "" for guests
  guest: boolean;
  contact: { name: string; phone: string };
  clientName: string;
  managerId: string | null; managerName: string | null;
  placedAt: string;
  fulfilment: "pickup" | "delivery"; address: string | null;
  payment: "pay-on-pickup" | "mtn-momo" | "airtel-money";
  paymentStatus: "pending" | "paid" | "not-charged";
  stage: "new" | "accepted" | "preparing" | "ready" | "completed" | "cancelled";
  lines: { itemId: string; quantity: number; choices: string[];
           options: { id: string; name: Localized; price: number }[];
           note: string | null; name: Localized; unitPrice: number; total: number }[];
  subtotal: number; fees: number; total: number;
  history: Partial<Record<Stage, string>>;   // when each stage was reached
  notes: string | null;
};
```

| Method & path | Who | Notes |
|---|---|---|
| `GET /me/orders?status=active\|completed\|cancelled&q=ORD-10` | client | `Order[]`, newest first |
| `GET /me/orders/{id}` | client | `404` when it is not the caller's order |
| `GET /me/notifications?unread=true` | client | `ClientNotification[]`, newest first (100 max) |
| `POST /me/notifications/read` `{ids}` or `{all: true}` | client | `204` |

```ts
type ClientNotification = { id: string; clientCode: string; orderId: string; stage: Stage;
  title: Localized; text: Localized; at: string; read: boolean };
```

Notifications are created by the server (texts copied from the website's dictionaries) when an order is
placed and at every stage change. Guests have no account, so no notifications.

### Register (staff)

| Method & path | Who | Notes |
|---|---|---|
| `GET /orders?since=&stage=&managerId=&guest=&q=` | `orders:process` | Default `since` = start of the register window (today + 2 previous Kigali days, `business.queueWindowDays`). `stage` accepts a list (`new,accepted`) or `active`. `q` matches order id, client code, name or phone. Orders also carry `contactEmail`. |
| `GET /orders/{id}` | `orders:process` | |
| `POST /orders/{id}/transition` `{to}` | assigned manager, superadmin | `200 {order}`. See §4. |
| `POST /orders/{id}/payment` `{status: "paid"}` | assigned manager, superadmin | Mobile Money is checked by staff for now: marks the order paid. |
| `POST /orders/{id}/assign` `{managerId}` | superadmin | Gives the order to another active manager. |

### Content (portal)

| Method & path | Permission | Notes |
|---|---|---|
| `GET /admin/menu/items?group=&category=&deleted=true` | `menu:edit` or `labels:edit` | Every item with `state` (`draft`/`published`), `draft` (pending changes, `MenuItemInput` shape) and `updatedAt`. |
| `POST /admin/menu/items` | `menu:edit` (+ the item's group in the grant) | `MenuItemInput` → `201`, state `draft`. `id` is optional (made from the English name). |
| `GET /admin/menu/items/{id}` | same as list | |
| `PATCH /admin/menu/items/{id}` | `menu:edit` (+ group), `labels:edit` for `isNew` | Published item: the changes are stored as its draft, the website keeps the live version. Never published item: edited directly. |
| `POST /admin/menu/items/{id}/publish` | `content:publish` | Applies the draft (photo, price, availability, badge together) and publishes. |
| `DELETE /admin/menu/items/{id}/draft` | edit | Discards pending changes. |
| `DELETE /admin/menu/items/{id}` | edit | Removes from the menu (soft delete). |
| `POST /admin/menu/items/{id}/restore` | edit | |
| `POST /admin/uploads` (multipart `file`) | `menu:edit` or `ads:manage` | JPEG/PNG/WebP, 5 MB max, resized to 1600 px → `201 {imageId, url}`. Send `imageId` in an item or a campaign. |
| `GET/POST /admin/campaigns`, `GET/PATCH/DELETE /admin/campaigns/{id}` | `ads:manage` | Created as `draft`. Editing a live campaign also needs `content:publish`. Only drafts can be deleted. |
| `POST /admin/campaigns/{id}/publish` | `content:publish` | → `scheduled` if `startsAt` is in the future, else `published`. |
| `POST /admin/campaigns/{id}/pause` · `/resume` · `/cancel-schedule` | `ads:manage` | |
| `GET/PUT/PATCH /admin/business` | `business:edit` | Same shape as `GET /business`. |

```ts
type MenuItemInput = {
  id?: string;                  // create only
  name: Localized; description?: Localized; cartMeta?: Localized | null;
  price: number; group: "food" | "drinks"; section?: string | null;
  categories?: string[]; tags?: string[]; optionGroups?: string[]; pairsWith?: string | null;
  isNew?: boolean; available?: boolean;
  imageId?: string;             // from POST /admin/uploads (or `image`: a URL)
};
type Campaign = {
  id: string; status: "draft" | "scheduled" | "published" | "paused";
  tag: "promotion" | "new" | "offer"; placement: "home-offers" | "home-hero"; tone: "yellow" | "plain";
  kicker: Localized | null; title: Localized; text: Localized | null; cta: Localized | null;
  highlight: { label: Localized; value: Localized; labelFirst: boolean } | null;
  schedule: Localized | null; ctaCategory: string | null;
  image: string; imageId: string; href: string; link: string;   // link = href, or /menu?category=…
  startsAt: string | null; endsAt: string | null; displayOrder: number; updatedAt: string;
};
```

Categories, drink sections, tags and option groups are managed by the superadmin in the Django admin
(`/admin/`): the website has no screen for them.

### Staff administration (superadmin)

| Method & path | Notes |
|---|---|
| `GET /admin/managers?status=active\|suspended\|invited&q=` | `StaffMember[]` with `activeOrders` and the current `contentGrant` |
| `GET /admin/managers/{id}` · `PATCH` `{name?, duty?, assignment?}` | A suspended manager cannot be put on duty or assigned (`409 manager_suspended`). |
| `POST /admin/managers/{id}/suspend` | Refused at once on every request, signed out, assignment and grant removed. **Active orders move to another on-duty manager** (or stay unassigned). |
| `POST /admin/managers/{id}/reactivate` | |
| `PUT /admin/managers/{id}/grant` `{scopes, startsAt?, expiresAt?}` | Replaces the current grant. No `expiresAt` = until revoked. |
| `DELETE /admin/managers/{id}/grant` | Revokes. |
| `POST /admin/invitations` `{name, email, assignment, lang?}` | Creates the manager (`status: "invited"`) and emails the link. Default access: orders only. |
| `POST /admin/managers/{id}/resend-invitation` | New link (the previous one stops working). |
| `GET /admin/overview` | `{orders, ordersToday, active: {stage: n}, activeOrders, pendingPayments, completedValue, completedCount, managers: {active, total, onDuty, offDuty, suspended}}` for the register window. |
| `GET /admin/audit?scope=orders\|content\|access&limit=20&cursor=` | `{items: AuditEvent[], nextCursor}` |

```ts
type StaffMember = { id: string; name: string; email: string; role: "manager";
  assignment: "pickup-register" | "backup" | "none"; duty: "on" | "off";
  status: "active" | "suspended" | "invited"; contentGrant: ContentGrant | null; activeOrders: number };
type AuditEvent = { id: string; at: string; actorId: string /* or "system" */; scope: "orders" | "content" | "access";
  targetId: string | null; type: string; data: object; text: Localized };
```

Audit `type`s: `order.placed`, `order.transition`, `order.paid`, `order.assigned`, `menu.draft`,
`menu.published`, `menu.deleted`, `campaign.saved|updated|published|scheduled|paused|resumed|unscheduled|deleted`,
`business.updated`, `manager.updated|suspended|reactivated|invited`, `grant.created|revoked`,
`invitation.accepted`.

---

## 4. Workflows

### Order stages

```
new → accepted → preparing → ready → completed
new | accepted → cancelled
```

- Anything else: `409 invalid_transition` with `details {from, to}`.
- `completed` marks a pay-on-pickup order `paid`; `cancelled` marks a pending order `not-charged`.
- Each step adds the time to `history`, notifies the client and records an audit event.
- **Assignment** of a new order: the on-duty `pickup-register` manager with the fewest active orders,
  else an on-duty `backup`, else any on-duty manager, else nobody. An unassigned order is taken by the
  first manager who moves it; the superadmin can act on every order and reassign it.

### Menu item: draft → published

1. `POST /admin/menu/items` → a draft, invisible on the website.
2. `PATCH` as many times as needed.
3. `POST …/publish` → visible. Later `PATCH`es are kept as a draft until the next publish (or
   `DELETE …/draft`).

### Campaign

`draft` → publish → `scheduled` (start in the future) / `published` ⇄ `paused`. A scheduled campaign
becomes live by itself at its start; `cancel-schedule` brings it back to draft. Public between
`startsAt` and `endsAt`.

### Sign-up

`sign-up` (code emailed) → `verify-email` (account created, signed in). An abandoned sign-up never
blocks the email: signing up again sends a new code.
