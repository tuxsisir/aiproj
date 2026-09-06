# StrataCorp Project Rules & Memory

This file serves as the core memory and instruction set for the Antigravity agent working on the StrataCorp project.

## Tech Stack & Architecture
- **Framework:** Django 6.0 (Python)
- **Frontend:** HTML, Tailwind CSS v4, HTMX
- **Database Architecture:** Single-Database, Shared-Schema multi-tenancy using UUIDs (linked via `StrataCorp` model)
- **Authentication:** `django-allauth` (email-first login, username automatically derived from email, no password confirmation field required)
- **CSS Build Pipeline:** `django-tailwind` compiling to `theme/static/css/dist/styles.css` (No CDN)

## Coding Preferences
- **Aesthetics:** Premium, dark-mode 'shadcn' inspired designs, high-converting copy.
- **Linting & Formatting:** Use `ruff` for Python and `djlint` for Django templates. HTML attributes MUST be on their own individual lines (`max_attribute_length: 1`).
- **State Management:** Use `localStorage` for light/dark mode persistence rather than complex backend session variables.

## Important Context
- **Document Chunking:** `DocumentChunk` model uses `pgvector.django` (1536-dimension `VectorField`).
- **User Ecosystem:** Three core roles: Manager (Strata Portfolio Manager), Council (Council Member), and Resident.

*(Note to User: You can type `/learn` in the chat at any time and ask me to add new behaviors or lessons to this file!)*
