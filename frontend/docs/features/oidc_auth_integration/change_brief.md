# Change Brief: OIDC Authentication Integration

## Overview

Integrate OIDC authentication into the frontend application. The backend has already implemented OIDC with the following endpoints:

- `GET /api/auth/self` - Returns `UserInfoResponseSchema` (200) or 401 if not authenticated
- `GET /api/auth/login?redirect=<url>` - Initiates OIDC login flow
- `GET /api/auth/logout` - Logs out the current user

## Authentication Flow

1. On app load, call `/api/auth/self`
2. If 401 is returned, redirect to `/api/auth/login?redirect=<current_path>` (preserve full path so user returns to where they were going after login)
3. After successful login, `/api/auth/self` returns user info
4. The entire app is protected - no public routes

## Layout Changes

The current layout has a left sidebar with hamburger, title, and menu. This needs to change to:

### Desktop Layout
- **Top bar** (horizontal, spans full width):
  - Hamburger icon (toggles left menu visibility)
  - Logo (favicon.png at 110% of text height)
  - "IoT Support" text
  - Spacer
  - User's full name with dropdown arrow (▾)
  - Dropdown menu contains only "Logout" option
- **Bottom area** (below top bar):
  - Left panel: Menu only (collapses completely when hamburger is clicked)
  - Right panel: Content area

### Mobile Layout
- Keep it simple - top bar with hamburger, logo, title, and user dropdown
- Menu appears as overlay when hamburger is clicked

### Styling
- Maintain current dark zinc theme (`bg-zinc-950`, `border-zinc-800`)
- Logo and "IoT Support" text should link to home/root route

## User Display

- Display user's `name` field from `UserInfoResponseSchema`
- If `name` is null, display "Unknown User"
- Dropdown is minimal: just shows name and has logout option

## Logout Behavior

- Clicking logout immediately redirects to `/api/auth/logout` (no confirmation dialog)

## Auth Gate Pattern

- Use an AuthProvider/AuthGate pattern
- Suspend all rendering until `/api/auth/self` response is received
- Show error screen with retry option if non-401 error occurs (e.g., 500 server error)

## Technical Context

- `UserInfoResponseSchema` has fields: `email`, `name` (nullable), `roles`, `subject`
- Generated API hooks exist: `useGetAuthSelf()`, `useGetAuthLogin()`, `useGetAuthLogout()`
- Current layout is in `src/routes/__root.tsx` with sidebar in `src/components/layout/sidebar.tsx`
- Follow existing patterns: context providers in `src/contexts/`, custom hooks wrapping generated API
