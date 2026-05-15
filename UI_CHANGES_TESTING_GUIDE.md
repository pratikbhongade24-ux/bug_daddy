# Bug Daddy — UI Upgrade Testing Guide

> A complete walkthrough of every feature implemented across the hackathon redesign sessions.  
> Follow each section in order for the best demo experience.

---

## Prerequisites — Start the App

```bash
# From the project root
cd C:\Users\prati\Downloads\bug_daddy
bash local_run.sh
```

Wait for the frontend dev server to print `ready on http://localhost:3000`, then open your browser.

---

## 1. Login Screen

**URL:** `http://localhost:3000/login`

### What to look for
- Clean, centered card with **glassmorphic shadow** and soft gradient background
- Input fields highlight with a **blue ring glow** on focus
- Submit button has a **blue gradient + hover lift** animation

### Test steps
1. Open `http://localhost:3000/login`
2. Click the **Email** field — verify blue glow ring appears
3. Enter credentials:
   - **User ID:** `bug_daddy@bugdaddy.local`
   - **Password:** `bug_daddy`
4. Click **Sign In** — verify button does not flicker on submit
5. You should be redirected to `/dashboard`

---

## 2. Ambient Background Mesh

**Where:** Entire app — visible on every screen

### What to look for
- A **very subtle, slowly drifting** multi-color radial gradient in the background (blue top-left, purple bottom-right, green center)
- Cycles every ~20 seconds — barely noticeable but makes the app feel "alive"

### Test steps
1. After login, look at the **background** of the dashboard (behind all cards)
2. Wait ~10 seconds — notice the gradient very gently shifts position
3. Navigate to Issues, Sonar — gradient persists across all views

---

## 3. Glassmorphic Topbar

**Where:** Top navigation bar

### What to look for
- The topbar has a **frosted glass** appearance — `backdrop-filter: blur(20px)`
- It appears semi-transparent over the background mesh
- A very soft shadow separates it from the content below

### Test steps
1. Look at the top navigation bar
2. On a supported browser (Chrome/Edge), notice the slight translucency
3. The topbar should feel distinctly **premium** — not a flat white bar

---

## 4. Live Dot — Double Ring Pulse

**Where:** Topbar, next to "LIVE" text

### What to look for
- The green dot now has a **ripple/sonar ring animation** — a ring expands outward and fades
- Larger and more visible than before (10px, was 8px)

### Test steps
1. Look at the **top-left of the topbar** — find the green "● LIVE" indicator
2. Watch for ~3 seconds — the ring should pulse outward like a sonar ping
3. Animation repeats every 2 seconds

---

## 5. AI Active Badge (Topbar)

**Where:** Topbar — appears only when an agent is running

### What to look for
- A purple gradient pill badge labeled **"AI ACTIVE"** with a pulsing dot
- Appears between the LIVE indicator and the metric pills

### Test steps
1. Go to the **Issues** view
2. Click **"Invoke AI"** on any backlog issue
3. Immediately look at the **topbar** — the `AI ACTIVE` badge should appear with its own pulse animation
4. The badge disappears when the modal is closed

---

## 6. ⌘K Command Palette Button (Topbar)

**Where:** Topbar, right section

### What to look for
- A small pill button showing `⌘K` with a CPU icon
- Hovering turns it blue

### Test steps
1. Find the `⌘K` badge in the **top-right of the topbar**
2. Click it — the Command Palette should open
3. Alternatively, press `Ctrl+K` (Windows) or `Cmd+K` (Mac) from anywhere in the app

---

## 7. Animated Role-Switcher Pill

**Where:** Topbar, right section — Developer / SRE / Manager

### What to look for
- The three role buttons are now inside a **unified segmented pill**
- Active role has a **white background card** that slides to the selected option
- Smooth transition animation between roles

### Test steps
1. Look at the top-right — find **Developer | SRE | Manager**
2. Click **SRE** — watch the white highlight smoothly move
3. Click **Manager** — smooth transition again
4. Role selection is purely visual (no data change required for demo)

---

## 8. Live Clock — Second-Level Updates

**Where:** Topbar, far right

### What to look for
- The clock now ticks **every second** (was every 30 seconds)
- Format: `HH:MM:SS` in monospace font

### Test steps
1. Look at the time display in the **top-right corner**
2. Watch for 2 seconds — the seconds digit should increment live

---

## 9. Demo Tour Banner

**Where:** Immediately below the topbar, on dashboard load

### What to look for
- A **purple-to-blue gradient banner** with a sparkle icon
- Reads: *"AI Demo Mode Active — Click any issue from the Escalation Queue to watch AI agents..."*
- Has a left-side gradient accent bar
- **Auto-dismisses after 12 seconds**

### Test steps
1. Navigate to the **Dashboard** view
2. The banner should appear at the top within 0.5s of load (slides in from above)
3. Wait 12 seconds — it should **fade out and collapse** automatically
4. OR click the **× button** on the right to dismiss manually

---

## 10. KPI Cards — Animated Number Counters

**Where:** Dashboard — top 4 metric cards (Total Issues, Critical, WIP, Resolved)

### What to look for
- Numbers **count up from 0** to their real value when the dashboard first loads
- Animation takes ~1.2 seconds with a smooth deceleration curve
- Large **3.2rem, 900-weight** numbers — clearly readable from a projector

### Test steps
1. Go to **Dashboard**
2. Watch the 4 KPI cards at the top load — numbers should animate upward from 0
3. To re-trigger: do a hard refresh (`Ctrl+Shift+R`)

---

## 11. KPI Cards — Mini Sparklines

**Where:** Dashboard KPI cards — bottom of each card

### What to look for
- A small **SVG waveform line** (like a stock ticker) in the bottom-left of each card
- A dot marks the latest data point
- Colored to match each card's accent color

### Test steps
1. Look at the **bottom of any KPI card** (e.g., Total Issues)
2. You should see a small waveform line + colored "LIVE" badge
3. The sparkline is a visual trendline representing recent activity

---

## 12. Spotlight Hover Physics (KPI & Chart Cards)

**Where:** All dashboard cards

### What to look for
- Moving your mouse over a card creates a **soft radial glow** that follows your cursor
- The glow matches the card's accent color
- Effect is visible on the **border and background** of the card

### Test steps
1. Hover your mouse over the **"Critical" KPI card** (red accent)
2. Slowly move the cursor around inside the card
3. Watch the **red glow follow your cursor** along the border
4. Move to the **"Resolved" card** (green) — glow changes color
5. Try the same on the horizontal bar charts below

---

## 13. Escalation Queue — Critical Issue Glow

**Where:** Dashboard — bottom-left Escalation Queue card

### What to look for
- Issues with **Critical** severity have a **pulsing red left border**
- The row background subtly flashes red every 2.5 seconds
- Makes critical issues immediately stand out to judges

### Test steps
1. Scroll down to the **Escalation Queue** card on the dashboard
2. Look for rows with a **red left border** — these are Critical severity items
3. Watch for the subtle pulsing red background flash

---

## 14. Command Palette — AI Intelligence Layer

**Where:** Press `Ctrl+K` (Windows) / `Cmd+K` (Mac) from anywhere

### What to look for
- A **glassmorphic floating search panel** morphs in from above
- Search bar at top with real-time filtering
- Standard navigation commands in the main list
- A **"✦ AI Insights"** section at the bottom with **contextual suggestions** generated from live issue data

### Test steps
1. Press `Ctrl+K` anywhere in the app
2. The palette should **spring-animate** into view (scale up + slide down)
3. Look at the **bottom section** labeled `AI Insights`
4. It should show smart suggestions like:
   - *"5 critical issues need immediate attention"* (if criticals exist)
   - *"12 issues in WIP — agents are actively resolving"* (if WIP exists)
   - *"All agents idle — run a Sonar scan"* (if everything quiet)
5. Type `sonar` in the search — list filters in real-time
6. Press `Escape` — palette slides out

---

## 15. AI Thinking Badge — Floating Agent Status

**Where:** Bottom-left corner — appears when an agent is invoked

### What to look for
- A **frosted glass card** slides in from the bottom-left
- Shows **"AI Agents Active"** label in purple
- A **typewriter animation** streams through agent activity messages cycling every 3.2s
- Three animated dots pulse at the right

### Test steps
1. Go to **Issues → Backlog** tab
2. Click **"Invoke AI"** on any issue
3. In the **bottom-left of the screen**, a badge should slide in
4. Watch the typewriter text cycle: `Analyzing error context…` → `Running Planner agent…` → etc.
5. Close the Execution Graph modal — the badge disappears

---

## 16. Issues View — Skeleton Loaders

**Where:** Issues view while data is loading

### What to look for
- Instead of blank space or "Loading...", you see **shimmer placeholder rows**
- 6 rows of grey shimmer blocks with a gradient sweep animation

### Test steps
1. Open DevTools → Network → set Throttling to "Slow 3G"
2. Navigate to **Issues** view (hard refresh)
3. Observe **shimmer skeleton rows** appear before real data loads
4. Remove throttling after testing

---

## 17. Issues View — Glowing "Invoke AI" Button

**Where:** Issues → Backlog tab → Action column

### What to look for
- The action button is now labeled **"Invoke AI"** (was "Prioritize")
- It has a **blue gradient background** with a sheen sweep on hover
- Hovering lifts the button with a stronger shadow
- While loading, the text disappears and a **spinning arc** appears

### Test steps
1. Go to **Issues → Backlog** tab
2. Find any issue row — look at the **"Invoke AI"** button (right column)
3. Hover over it — watch the **white sheen sweep** across the button
4. Click it — the button should show a **spinning arc loader** while the agent starts

---

## 18. Issues View — Row Flash on Invoke

**Where:** Issues table row after clicking "Invoke AI"

### What to look for
- The entire table row **flashes blue** briefly (1.5 seconds) after clicking Invoke AI
- Fades back to white smoothly

### Test steps
1. Click **"Invoke AI"** on a backlog issue
2. Watch the **entire row** — it should flash with a blue highlight and fade

---

## 19. Critical Badge Pulse

**Where:** Issues table → Criticality column → "Critical" badges

### What to look for
- Critical severity badges have a **slow red glow pulse** around them
- A ring of red shadow expands and contracts every 2 seconds

### Test steps
1. Go to **Issues** view (any tab)
2. Find a row with **"Critical"** in the Criticality column
3. Watch the badge — a soft red shadow should pulse outward rhythmically

---

## 20. Execution Graph Modal — Cinematic Entrance

**Where:** Any "Live Graph" or "Invoke AI" modal

### What to look for
- Modal scales in from **0.88 → 1.0** (more dramatic — was 0.95)
- Combined with a vertical slide-up spring animation
- Background blurs more strongly (`backdrop-filter: blur(8px)`)

### Test steps
1. Click **"Live Graph"** on any WIP issue, or **"Invoke AI"** on a backlog issue
2. Watch the modal **scale up from smaller** — the spring physics should feel snappy and natural
3. The dark overlay behind should be noticeably blurred

---

## 21. Execution Graph Modal — Step Progress Strip

**Where:** Inside the Execution Graph modal — below the header

### What to look for
- A horizontal strip showing the **AI workflow stages**:
  - Bug Daddy: `Analyze → Plan → Code → Review → Deploy`
  - Incident Daddy: `Analyze → Route → JIRA Update → Resolve`
- Steps light up **green** (✓) as they complete
- The current active step shows a **blue spinning indicator**
- Connecting lines fill green as progress advances

### Test steps
1. Open any **Live Graph** modal
2. Look at the **progress strip below the modal header**
3. For a resolved issue's Summary view, most steps should show ✓
4. For a live execution, watch the steps fill in as the agent progresses

---

## 22. Execution Graph Modal — Enhanced Node Glow

**Where:** Inside the graph canvas — active nodes

### What to look for
- Active nodes have a **two-layer glow** — a colored halo + a wider atmospheric glow
- The node also **scales up to 1.08x** when active
- Combined with the spinning ring, creates a strong "AI is thinking here" visual

### Test steps
1. Open a **Live Graph** for an in-progress issue
2. Watch the graph canvas — the **active node** should glow prominently
3. The glow color matches the node's type (purple for Planner, blue for Coder, etc.)

---

## 23. Dashboard — Skeleton Loaders (KPI Grid)

**Where:** Dashboard → KPI cards on first load

### What to look for
- If data hasn't loaded yet, 4 **grey shimmer rectangles** appear instead of KPI cards
- Matches the exact shape and size of the real KPI cards

### Test steps
1. Open DevTools → Network → throttle to "Slow 3G"
2. Navigate to **Dashboard** (hard refresh)
3. Observe the **4 shimmer placeholder cards** before real KPIs appear

---

## 24. Sonar View

**URL:** Click "SonarQube" in the left sidebar

### Test steps
1. Click **SonarQube** in the sidebar
2. Page should animate in smoothly (fade-up transition)
3. Click **"Run Scan"** button — verify toast appears in bottom-right

---

## 25. Toast Notifications

**Where:** Bottom-right corner

### Test steps
1. Click **"Escalate All Critical"** on Dashboard
2. A toast should **spring-slide in** from the bottom-right
3. Green border = success, Red = error, Blue = info
4. Auto-dismisses after 3.4 seconds

---

## Recommended Demo Flow for Judges

Follow this exact 2-minute sequence for maximum impact:

```
1.  Fresh load: http://localhost:3000  (Ctrl+Shift+R for clean start)
2.  Login with bug_daddy@bugdaddy.local / bug_daddy
3.  [Dashboard] — Narrate:
      "This is the Command Center — notice the KPIs counting up live"
      Point to: Demo Banner, Live dot, Ambient background
4.  Hover KPI cards — show spotlight glow following cursor
5.  Press Ctrl+K — "We have an AI-powered command palette"
      Point to: AI Insights at the bottom (contextual suggestions)
      Press Esc to close
6.  Click a critical (red-glowing) issue in the Escalation Queue
      "Let's watch the AI agents work — this opens the Execution Graph"
      Point to: Step progress strip (Analyze → Plan → Code...)
      Point to: Graph nodes lighting up
7.  Close modal
8.  Navigate to Issues → Backlog
      Show "Invoke AI" button — hover to show shimmer effect
      Click it — "We're invoking the Bug Daddy AI agent now"
      Point to: Spinning arc loader, AI Active badge in topbar
      Point to: AI Thinking Badge (bottom-left) streaming text
9.  Graph opens again — point to live step progress
10. Close → SonarQube → Run Scan → show success toast
```

---

## Files Changed (Reference)

| File | Type | Change Summary |
|------|------|----------------|
| `src/app/globals.css` | Modified | Ambient mesh, projector sizing, all new animations |
| `src/components/layout/Topbar.tsx` | Modified | Glassmorphism, role pill, ⌘K, AI Active badge |
| `src/components/dashboard/Kpi.tsx` | Modified | Animated counters, sparklines |
| `src/components/dashboard/DashboardOverview.tsx` | Modified | Skeleton loading, critical glow |
| `src/components/dashboard/HorizontalChart.tsx` | Modified | SpotlightCard integration |
| `src/components/issues/IssuesView.tsx` | Modified | Skeleton rows, Invoke AI button, row flash |
| `src/components/graph/ExecutionGraphModal.tsx` | Modified | Step strip, cinematic entrance, node glow |
| `src/components/shared/CommandPalette.tsx` | Modified | AI Insights intelligence layer |
| `src/components/shared/SpotlightCard.tsx` | New | Cursor-tracking radial glow wrapper |
| `src/components/shared/DemoTourBanner.tsx` | **New** | Auto-dismissing demo guide banner |
| `src/components/shared/AiThinkingBadge.tsx` | **New** | Floating AI activity indicator |
| `src/components/shared/SkeletonLoader.tsx` | **New** | Shimmer skeleton loaders |
| `src/components/DashboardApp.tsx` | Modified | SSR hydration fix, agent state wiring |
