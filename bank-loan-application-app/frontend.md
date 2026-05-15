# Bug Daddy - Frontend Design Specifications

## Login Page

The newly designed login page serves as the authentication gateway for the Bug Daddy platform. It follows our premium dark-mode aesthetic with vibrant neon accents.

### Design Mockup

![Bug Daddy Login Design Mockup](/Users/danishgada/.gemini/antigravity/brain/9c2c3682-352b-459e-a441-e14f98ccb3ea/bug_daddy_login_page_1775676403918.png)

### Key UI Elements
1. **Glassmorphism Base Layer**: The core of the login card should contain a subtle frosted glass effect using `backdrop-filter: blur(12px)` and a `rgba(255, 255, 255, 0.05)` background.
2. **Typography**: JetBrains Mono for technical labels and Inter/Plus Jakarta Sans for the primary headings.
3. **Form Inputs**: Floating borders that illuminate upon `:focus`.
4. **Primary Action**: "Sign In" button that glows smoothly and validates entry (currently set to pass-through directly to `index.html`).
5. **Third-Party Login**: Only Microsoft Single Sign-On (SSO) button is available, complete with a helpful tooltip referencing SSO usage "Tips".
6. **No Signup Provision**: Built strictly for internal usage. No 'Sign Up' links are present.

### Implementation Next Steps
- Created `login.html` in the frontend directory mirroring this exact design.
