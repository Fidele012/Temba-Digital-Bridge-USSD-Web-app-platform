/**
 * Temba Digital Bridge — Smart Assistant Widget v2
 * • Fetches live provider data from the API
 * • Routes users to the right provider based on their service need
 * • Guides navigation of every platform feature
 * • Multi-turn conversation state for guided flows
 */

(function () {
  'use strict';

  // ─── Config ──────────────────────────────────────────────────────────────────
  const _localBase = window.API_BASE || 'http://127.0.0.1:8000';
  const _prodBase = 'https://temba-api-production.up.railway.app';
  const API = (['localhost','127.0.0.1'].includes(window.location.hostname) ? _localBase : _prodBase).replace(/\/$/, '');

  // ─── Service category labels ─────────────────────────────────────────────────
  const SERVICE_LABELS = {
    water_supply:    { label: 'Water Supply',       icon: '💧' },
    meter_services:  { label: 'Meter Services',     icon: '📊' },
    water_quality:   { label: 'Water Quality',      icon: '🧪' },
    truck_delivery:  { label: 'Water Truck',        icon: '🚛' },
    water_storage:   { label: 'Water Storage',      icon: '🪣' },
    sanitation:      { label: 'Sanitation',         icon: '🧹' },
    infrastructure:  { label: 'Infrastructure',     icon: '🔧' },
    pipe_repair:     { label: 'Pipe Repair',        icon: '🔩' },
    water_connection:{ label: 'New Connection',     icon: '🏠' },
    inspection:      { label: 'Inspection',         icon: '🔍' },
  };

  // ─── User-intent → service_category mapping ──────────────────────────────────
  const INTENT_TO_SERVICE = {
    // Contamination / quality
    contamination:   ['water_quality', 'sanitation'],
    'bad smell':     ['water_quality'],
    'dirty water':   ['water_quality'],
    'brown water':   ['water_quality'],
    'taste':         ['water_quality'],
    'test water':    ['water_quality'],
    'water quality': ['water_quality', 'water_supply'],
    // Supply / outage
    'no water':      ['water_supply', 'truck_delivery'],
    'no supply':     ['water_supply', 'truck_delivery'],
    'dry tap':       ['water_supply', 'truck_delivery'],
    outage:          ['water_supply'],
    shortage:        ['water_supply', 'truck_delivery'],
    drought:         ['truck_delivery', 'water_storage'],
    // Trucks / emergency delivery
    truck:           ['truck_delivery'],
    'water truck':   ['truck_delivery'],
    'emergency water':['truck_delivery'],
    'bulk water':    ['truck_delivery', 'water_storage'],
    'fill tank':     ['truck_delivery', 'water_storage'],
    // Storage
    storage:         ['water_storage'],
    tank:            ['water_storage', 'truck_delivery'],
    // Meters
    meter:           ['meter_services'],
    'meter reading': ['meter_services'],
    'meter repair':  ['meter_services'],
    'meter install': ['meter_services'],
    'billing':       ['meter_services'],
    // Infrastructure / pipes
    'pipe burst':    ['infrastructure', 'pipe_repair'],
    'burst pipe':    ['infrastructure', 'pipe_repair'],
    'broken pipe':   ['infrastructure', 'pipe_repair'],
    'pipe leak':     ['infrastructure', 'pipe_repair'],
    leak:            ['infrastructure', 'pipe_repair'],
    'low pressure':  ['infrastructure', 'water_supply'],
    // Sanitation
    sanitation:      ['sanitation'],
    sewage:          ['sanitation'],
    drainage:        ['sanitation'],
    toilet:          ['sanitation'],
    // Connection
    connection:      ['water_connection', 'water_supply'],
    'new connection':['water_connection', 'water_supply'],
    'connect home':  ['water_connection'],
    // Inspection
    inspection:      ['inspection', 'infrastructure'],
    survey:          ['inspection'],
  };

  // ─── Live provider store ─────────────────────────────────────────────────────
  let PROVIDERS = [];         // populated on init from API
  let providersLoaded = false;

  async function loadProviders() {
    try {
      const res = await fetch(`${API}/api/v1/providers?size=50`);
      if (!res.ok) return;
      const data = await res.json();
      PROVIDERS = (data.items || []).filter(p => p.status === 'approved' || !p.status);
      providersLoaded = true;
    } catch (_) {
      // API not reachable — chatbot still works with knowledge base
    }
  }

  function matchProviders(serviceCategories) {
    if (!PROVIDERS.length) return [];
    return PROVIDERS.filter(p => {
      const provCats = Array.isArray(p.service_categories)
        ? p.service_categories
        : (typeof p.service_categories === 'string'
            ? JSON.parse(p.service_categories)
            : []);
      return serviceCategories.some(cat => provCats.includes(cat));
    });
  }

  function getMatchingServicesFor(provider) {
    const cats = Array.isArray(provider.service_categories)
      ? provider.service_categories
      : (typeof provider.service_categories === 'string'
          ? JSON.parse(provider.service_categories)
          : []);
    return cats.map(c => SERVICE_LABELS[c] || { label: c, icon: '🔹' });
  }

  function renderProviderCards(providers, userNeed) {
    if (!providers.length) return '';
    const cards = providers.map(p => {
      const services = getMatchingServicesFor(p);
      const badgesHtml = services.slice(0, 4).map(s =>
        `<span class="tchat-badge">${s.icon} ${s.label}</span>`
      ).join('');
      const phoneLink = p.phone
        ? `<a href="tel:${p.phone}" class="tchat-prov-action tchat-prov-call">📞 Call</a>`
        : '';
      const emailLink = p.email
        ? `<a href="mailto:${p.email}" class="tchat-prov-action tchat-prov-email">✉️ Email</a>`
        : '';
      return `
        <div class="tchat-provider-card">
          <div class="tchat-prov-name">${p.organization_name}</div>
          ${p.description ? `<div class="tchat-prov-desc">${p.description}</div>` : ''}
          <div class="tchat-badge-row">${badgesHtml}</div>
          <div class="tchat-prov-actions">
            ${phoneLink}
            ${emailLink}
            <button class="tchat-prov-action tchat-prov-book"
              onclick="tembaChat._bookWith('${p.id}','${p.organization_name.replace(/'/g,"\\'")}')">
              📅 Book Appointment
            </button>
          </div>
        </div>`;
    }).join('');
    return `<div class="tchat-provider-list">${cards}</div>`;
  }

  // ─── Conversation state ───────────────────────────────────────────────────────
  let conversationState = null; // null | { flow, step, data }

  function setFlow(flow, step, data) {
    conversationState = { flow, step, data: data || {} };
  }
  function clearFlow() { conversationState = null; }

  // ─── Knowledge base ──────────────────────────────────────────────────────────
  const KB = [
    // GREETINGS
    {
      id: 'greeting',
      keywords: ['hello','hi','hey','good morning','good afternoon','good evening',
                 'muraho','mwaramutse','amakuru','bite','yego','oya','bonjour',
                 'help','start','assist','what can you do','i need help'],
      response: () => `Hello! I'm **Temba Assistant** 👋

I can help you with:

💧 **Find the right water provider** for your specific need
🗺️ **Navigate the platform** — reporting, tracking, bookings
📞 **Get provider contacts** for WASAC, IRIBA, Pro Water
🚨 **Water emergencies** — contamination, burst pipes, outages
❓ **Platform how-to** — accounts, appointments, USSD access

What can I help you with today?`,
      quickReplies: ['I need water service','How do I report an issue?','Find a provider near me','Use Temba without internet'],
    },

    // KINYARWANDA
    {
      id: 'kinyarwanda',
      keywords: ['kinyarwanda','ikinyarwanda','ndashaka','nshaka','amazi','ikibazo',
                 'muraho','mwaramutse','amakuru','bite','impungenge'],
      response: () => `Muraho! 🇷🇼

Nshobora kukufasha mu magambo make y'Ikinyarwanda.

🇷🇼 **Kinyarwanda:**\n• Raporo y'ikibazo cy'amazi → tandika ikibazo\n• Gukurikirana raporo → shyiraho kode yawe\n• Gutuza umunsi wo guterana → reba abatuzi

🇬🇧 **For full guidance**, please continue in **English** — I cover all platform features in detail.

Ibikubiye muri Temba kandi birahari muri **USSD** (*384*36640#) mu Kinyarwanda.`,
      quickReplies: ['How do I report? (English)','Find a provider','Use USSD in Kinyarwanda'],
    },

    // FIND PROVIDER (main intent)
    {
      id: 'find_provider',
      keywords: ['find provider','which provider','who provides','right provider','best provider',
                 'provider for','looking for provider','need a provider','recommend provider',
                 'suggest provider','who can help','which company','what company'],
      response: () => {
        if (!providersLoaded || !PROVIDERS.length) {
          return `I'm loading provider information...\n\nOur registered providers cover:\n• **Water supply & outages** — WASAC, IRIBA Water Group\n• **Water truck delivery** — Pro Water Rwanda\n• **Water quality testing** — IRIBA Water Group\n• **Sanitation & infrastructure** — WASAC\n• **Meter services** — IRIBA Water Group\n\nTell me what kind of service you need and I'll point you to the right one.`;
        }
        const list = PROVIDERS.map(p => {
          const services = getMatchingServicesFor(p);
          return `🏢 **${p.organization_name}** — ${services.map(s => s.icon + ' ' + s.label).join(', ')}`;
        }).join('\n');
        return `Here are all **registered providers** on Temba:\n\n${list}\n\nTell me what **service you need** (e.g. "water truck", "meter repair", "contamination") and I'll match you to the right provider.`;
      },
      quickReplies: ['Water truck delivery','Water quality issue','No water / outage','Meter problem','Burst pipe'],
    },

    // REPORTING
    {
      id: 'report_how',
      keywords: ['report','submit report','file report','raise issue','create report','new report',
                 'how report','make report','log issue','report issue','report problem'],
      response: () => `**How to Report a Water Issue:**

**Step 1** — Sign in to your community account
**Step 2** — Click **"Report Issue"** in your dashboard sidebar
**Step 3** — Choose the issue category:
  → Contamination · Pipe Burst · No Supply · Low Pressure · Meter · Billing · Other
**Step 4** — Set **urgency level** (Low / Medium / High / Critical)
**Step 5** — Select the **water provider** responsible for your area
**Step 6** — Add description and optional photos
**Step 7** — Submit — you'll instantly get a **reference code** (e.g. RPT-20260703-X4K2)

📱 **No internet?** Dial **\*384\*36640#** → "1. Report Water Issue"

Your report is visible to the provider immediately and you get SMS updates at every status change.`,
      quickReplies: ['What issue categories exist?','Report via USSD','Track my report','Contamination emergency'],
    },

    {
      id: 'report_categories',
      keywords: ['categories','types of issue','what issues','what can report','broken pipe','pipe burst',
                 'no water','dry tap','shortage','low pressure','contamination','sewage','pump','meter'],
      response: () => `**Issue Categories on Temba:**

🔴 **Critical (P1 — 4h SLA)**
• Contamination — discoloured, smelly, or chemically unsafe water
• Burst/broken main pipe with flooding

🟠 **Urgent (P2 — 24h SLA)**
• Pipe burst (no flooding)
• Complete water outage / no supply
• Low pressure affecting many households

🔵 **Standard (P3 — 72h SLA)**
• Persistent low pressure
• Billing / meter disputes
• Drainage issues
• General infrastructure damage

Every report gets an **automatic priority classification** (P1/P2/P3). Providers see P1 reports at the top of their dashboard.`,
      quickReplies: ['How do I report?','Contamination is an emergency','What is the SLA?'],
    },

    // TRACKING
    {
      id: 'track_report',
      keywords: ['track','status','check status','my report','update','progress','follow up',
                 'reference number','ref code','rpt-','what happened','no update','pending',
                 'where is my','how long'],
      response: () => `**Tracking Your Report:**

**Option 1 — Dashboard (logged in):**
1. Sign in → Dashboard → **"My Reports"** in sidebar
2. Reports show colour-coded badges:
   • 🔵 Submitted → 🟠 Acknowledged → 🔄 In Progress → 🟢 Resolution Submitted → ✅ Verified
3. Click any report card for full provider notes and timeline

**Option 2 — Public tracker (no login):**
Go to the **homepage** → enter your reference code in the **"Track Your Issue"** field
→ see real-time status, provider notes, and expected resolution date

**Option 3 — USSD:**
Dial **\*384\*36640#** → "2. Track My Reports" → see your 3 most recent reports

**Getting SMS updates?** Make sure your phone number is correct in your profile settings.`,
      quickReplies: ['I have not received an update','Verify my resolution','What does each status mean?'],
    },

    {
      id: 'status_meaning',
      keywords: ['what does status mean','status meaning','acknowledged','in progress','resolution submitted',
                 'verified','what is open','what is closed','follow up','management review'],
      response: () => `**Report Status Guide:**

🔵 **Submitted** — Your report was received and is in the provider's queue
🟡 **Acknowledged** — Provider has seen your report and assigned it
🔄 **In Progress** — Provider team is actively working on the issue
📋 **Resolution Submitted** — Provider says the issue is fixed — **you need to verify**
✅ **Verified** — You confirmed the fix. The case is officially closed.
⚠️ **Follow Up** — You disputed the resolution. Case re-opened.
🔒 **Auto Closed** — No verification response in 7 days (assumed resolved)

**Important:** When status becomes "Resolution Submitted", you receive an SMS asking you to confirm the fix. Please respond — it holds the provider accountable.`,
      quickReplies: ['How to verify a resolution','My issue is not fixed','Track my report'],
    },

    // APPOINTMENTS
    {
      id: 'appointment_book',
      keywords: ['appointment','book appointment','schedule','meeting','consultation','visit provider',
                 'talk to provider','see provider','callback','call back','book meeting'],
      response: () => `**Booking an Appointment:**

1. Sign in → Dashboard → **"Appointments"** in sidebar
2. Click **"Book Appointment"**
3. Select a **water service provider** (those registered on Temba)
4. Choose appointment **reason**:
   → New connection · Meter reading · Pipe repair · Billing · Inspection · Consultation
5. Pick your **preferred date & time slot** from the provider's available hours
6. Add notes and submit

✅ The provider approves within 1–2 business days
📩 You get an SMS/email confirmation (or a proposed alternative time)
🔄 You can reschedule or cancel any time from your dashboard

Appointments are **free to book** — no charge for scheduling.`,
      quickReplies: ['Reschedule an appointment','Cancel an appointment','Which providers accept appointments?'],
    },

    {
      id: 'appointment_reschedule',
      keywords: ['reschedule','change appointment','different time','postpone','move appointment',
                 'not available','update appointment'],
      response: () => `**Rescheduling an Appointment:**

1. Dashboard → **Appointments**
2. Find the appointment → click **"Reschedule"**
3. Select a new preferred date and time
4. Add a short note (optional) and submit

The provider will receive the request and confirm or propose a further alternative.

**You can reschedule:** Pending or Approved appointments
**You cannot reschedule:** Completed or Rejected appointments`,
      quickReplies: ['Cancel instead','Book new appointment','View my appointments'],
    },

    {
      id: 'appointment_cancel',
      keywords: ['cancel appointment','cancel booking','remove appointment','no longer need','withdraw'],
      response: () => `**Cancelling an Appointment:**

1. Dashboard → **Appointments**
2. Find the appointment → click **"Cancel"**
3. Select a cancellation reason and confirm

The provider is automatically notified.

💡 **Tip:** Cancel at least **24 hours in advance** where possible — this helps providers manage their schedules for other community members.`,
      quickReplies: ['Book a new appointment','Reschedule instead','View my appointments'],
    },

    // SERVICE REQUESTS
    {
      id: 'service_request',
      keywords: ['service request','request service','apply for service','request water',
                 'water connection','new connection','connect water','pipe installation',
                 'water tank','tank delivery','water truck','truck delivery',
                 'meter install','technical visit','borehole','new pipe'],
      response: () => `**Requesting a Water Service:**

Available services from Temba providers:

💧 **New Water Connection** — pipe installation to your home or property
🚛 **Water Truck Delivery** — emergency bulk water to your location
🪣 **Water Storage Tank** — tank supply and installation
📊 **Meter Support** — installation, repair, or dispute resolution
🔍 **Technical Inspection** — infrastructure assessment visit
🔧 **Pipe Repair** — planned repair of leaks or damage

**How to submit:**
1. Dashboard → **"Service Requests"** → **"New Request"**
2. Choose the service type
3. Select the provider offering that service
4. Enter your location and requirements
5. Submit — provider responds within 2–5 business days

Want me to find the **right provider for a specific service?** Tell me what you need!`,
      quickReplies: ['Water truck delivery','New water connection','Meter support','Technical inspection'],
    },

    // USSD
    {
      id: 'ussd',
      keywords: ['ussd','basic phone','no smartphone','no internet','feature phone','offline',
                 'without internet','dial','*384*','kinyarwanda phone','any phone'],
      response: () => `**Using Temba Without Internet — USSD:**

📱 Dial **\*384\*36640#** on **any mobile phone** — basic, smartphone, or borrowed.

**USSD Main Menu:**
1. 📢 Report Water Issue
2. 🔍 Track My Reports
3. 📅 Book Appointment
4. 📋 My Appointments
5. 📊 Service Request Status
6. 🔧 Submit Service Request

**Available in:**
🇷🇼 Kinyarwanda  |  🇬🇧 English (you choose at the start)

**What you can do via USSD:**
• Report water issues and get a tracking reference code
• Check status of your last 3 reports
• Book appointments and check upcoming ones
• Submit service requests (truck, connection, meter)
• Verify that a resolution fixed your issue
• Rate the service anonymously (1–5 stars)

⏱️ Respond within **30 seconds** per prompt to avoid session timeout.`,
      quickReplies: ['Report via USSD step by step','Register via USSD','Track via USSD'],
    },

    {
      id: 'ussd_registration',
      keywords: ['register ussd','sign up ussd','create account ussd','ussd register',
                 'basic phone register','register without internet'],
      response: () => `**Registering via USSD (no internet needed):**

1. Dial **\*384\*36640#**
2. Choose language: **1. English** or **2. Kinyarwanda**
3. Select **1. Register**
4. Enter your **full name**
5. Choose your **Province** from the numbered list
6. Choose your **District**
7. Create a **4-digit PIN** (you'll use this to log in via USSD)
8. Confirm the PIN

✅ Account created! You can now log in with your phone number + PIN on any USSD session.

**Note:** For the full web platform (reports with photos, detailed tracking, appointments), visit temba.rw and sign up with email.`,
      quickReplies: ['How to report via USSD','Login via USSD','What is USSD?'],
    },

    // ACCOUNTS
    {
      id: 'account_signup',
      keywords: ['register','sign up','create account','join temba','new account','how to register',
                 'make account','open account','get started'],
      response: () => `**Creating a Temba Account:**

**Community Member — free, instant:**
1. Click **"Sign Up"** on the homepage
2. Select **"Community Member"**
3. Enter name, phone, email, and ID number
4. Set your Rwanda location (Province → Village)
5. Create a password → account is **active immediately**

**Water Provider — verified:**
1. Click **"Sign Up"** → **"Water Provider"**
2. Enter organisation name, description, service categories
3. Add SLA commitment and escalation contacts (Officer + Supervisor)
4. Submit → reviewed by admin within **1–2 business days**

📧 Once approved, providers receive a verification email and can access their dashboard.

[Sign Up →](signup.html)`,
      quickReplies: ['Sign up as community member','Register as water provider','Already have an account?'],
    },

    {
      id: 'account_login',
      keywords: ['log in','login','sign in','forgot password','reset password','locked out',
                 'cannot login','access account','change password','wrong password'],
      response: () => `**Signing In & Password Help:**

**To sign in:** Click **"Sign In"** → enter your email + password

**Forgot password?**
1. Sign In page → **"Forgot Password?"**
2. Enter your registered email or phone number
3. Receive a reset code via SMS or email
4. Create a new password

**Common issues:**
• Make sure you're on the right tab (Community vs Provider)
• Check email spelling — no spaces before or after
• Try clearing browser cache or use a different browser

**USSD users:** Your login is your **phone number + 4-digit PIN** (not your web password)

[Go to Sign In →](signin.html)`,
      quickReplies: ['Reset my password','Sign up instead','Login via USSD'],
    },

    // VERIFICATION & RATING
    {
      id: 'verify_resolution',
      keywords: ['verify','confirm fixed','resolution','issue fixed','not fixed','dispute',
                 'confirm resolution','verify my report','it is fixed','still not fixed'],
      response: () => `**Verifying a Resolution:**

When a provider marks your issue as resolved, you'll receive an **SMS notification** and the report status changes to "Resolution Submitted".

**To verify via the web:**
1. Dashboard → **My Reports**
2. Find the report with status "Resolution Submitted"
3. Click **"Verify Resolution"**
4. Choose: **✅ Yes, it's fixed** or **❌ No, dispute resolution**

**To verify via USSD:**
Dial **\*384\*36640#** → Login → **"2. Track My Reports"**
Reports marked [VERIFY] will appear first → select and respond

**If you say it's NOT fixed:**
The case is re-opened with "Follow Up" status. The provider must respond again — and their supervisor is notified.

**After verifying as fixed:** You can leave an **anonymous 1–5 star rating** for the provider.`,
      quickReplies: ['Rate a provider','My issue is not fixed','How to dispute a resolution'],
    },

    {
      id: 'rating',
      keywords: ['rate','rating','review','stars','feedback','anonymous','score','how to rate',
                 'provider rating','review provider'],
      response: () => `**Rating a Provider (Anonymous):**

After you verify that your issue is fixed, you can leave a rating.

**How it works:**
1. Verify resolution as "Fixed" (web or USSD)
2. A rating prompt appears automatically
3. Select **1–5 stars** and optionally add a comment
4. Submit

**Key fact: Ratings are completely anonymous.**
Your name, phone, and account are **never** linked to your rating. Providers only see their **average score** and total count — never who gave which rating.

This encourages honest feedback and genuine improvement.

**On USSD:** After verifying, select a rating (1–5). No comments on USSD.`,
      quickReplies: ['How to verify resolution','What does the provider see?','How is the score calculated?'],
    },

    // WATER SAFETY
    {
      id: 'water_safety',
      keywords: ['safe to drink','water safety','water quality','boil water','filter','purify',
                 'ph level','chlorine','bacteria','is it safe','how to purify'],
      response: () => `**Water Safety Guide:**

**Signs your water may be unsafe:**
• Unusual smell (sewage, sulfur, chemical)
• Discolouration (brown, yellow, black, cloudy)
• Particles or sediment visible
• Bitter, metallic, or strange taste

**Rwanda safe water standards:**
| Parameter | Safe Range |
|-----------|-----------|
| pH | 6.5 – 8.5 |
| Turbidity | Below 1 NTU (clear) |
| Chlorine | 0.2 – 0.5 mg/L |
| E. coli | 0 detected |

**If unsure about your water:**
1. Boil for **1 minute** and let cool in a covered container
2. Use a certified filter
3. Use bottled water for drinking until confirmed safe

⚠️ Suspect contamination? **Submit an urgent report immediately** — this triggers a P1 (4-hour SLA) response.`,
      quickReplies: ['Report contamination','Find provider for water quality','What is P1 priority?'],
    },

    // CONTAMINATION EMERGENCY
    {
      id: 'contamination',
      keywords: ['contaminated','contamination','chemical','bad smell','smell bad','brown water',
                 'black water','yellow water','smell sewage','unsafe water','polluted','dirty water',
                 'oily water','strange taste'],
      response: () => `⚠️ **Suspected Water Contamination — Act Now:**

**Immediately:**
1. **Stop drinking** the water
2. Use bottled or stored clean water
3. **Warn your neighbours**
4. Submit an **URGENT report** → select "Contamination" category

Contamination is automatically classified **P1 Critical** — the provider must respond within **4 hours**.

**If anyone is already ill:** Go to the nearest health centre immediately and call **912**.

Contamination in your area means others may be affected — reporting it protects your whole community.`,
      professional: true,
      professionalMsg: 'Water contamination can affect an entire community and requires urgent assessment by a certified water quality specialist. IRIBA Water Group and WASAC both offer water quality services.',
      quickReplies: ['Report contamination now','Find water quality provider','Emergency: Call 912'],
    },

    // HEALTH
    {
      id: 'health_medical',
      keywords: ['sick','ill','disease','diarrhea','vomiting','stomach pain','fever',
                 'poisoning','hospital','doctor','health centre','unwell'],
      response: () => `🏥 **Health Emergency Linked to Water:**

**Do this right now:**
1. **Seek medical care** at your nearest health centre or hospital
2. **Stop drinking** tap water until confirmed safe
3. **Report the contamination** on Temba to protect others
4. Record when symptoms started and what water source you used

**Rwanda Emergency:** Call **912**
**WASAC Emergency:** +250 788 123 456

Please prioritise getting medical care — report the water issue in parallel.`,
      professional: true,
      professionalMsg: 'Health symptoms from water require both medical attention and a water quality investigation. Report the issue on Temba so WASAC or IRIBA can investigate the source.',
      quickReplies: ['Emergency: Call 912','Report contamination','Find water quality provider'],
    },

    // BURST PIPE / INFRASTRUCTURE
    {
      id: 'burst_pipe',
      keywords: ['burst pipe','broken pipe','main burst','road flooding','major leak',
                 'pipe exploded','pipe crack','water flooding road','broken main'],
      response: () => `🚨 **Burst Pipe / Major Leak:**

**Immediate steps:**
1. **Stay away** from the damaged area — pressurised water is dangerous
2. **Call WASAC directly** for emergency response: **+250 788 123 456**
3. Submit an **Urgent report** on Temba (P1/P2 — 4-24h SLA)
4. Alert your local sector office if roads are affected

**WASAC** handles infrastructure emergencies as Rwanda's national water utility. Do not wait for online processing alone — call first.`,
      professional: true,
      professionalMsg: 'Major pipe bursts require emergency response from infrastructure engineers. WASAC is the primary contact for infrastructure emergencies in Rwanda.',
      quickReplies: ['Call WASAC now','Submit urgent report','Find infrastructure provider'],
    },

    // BILLING
    {
      id: 'billing',
      keywords: ['bill','billing','invoice','overcharged','wrong bill','meter reading wrong',
                 'dispute bill','billing error','payment','too expensive'],
      response: () => `**Billing & Meter Disputes:**

Billing issues require your account history — these are handled by your provider's billing department.

**Steps:**
1. **Book an appointment** with your provider → select "Billing Dispute" as the reason
2. **Bring your bills/receipts** to the appointment
3. If meter readings seem wrong, also request a **"Meter Inspection"** service request

**IRIBA Water Group** handles meter services: 📞 +250 788 345 678 | support@iriba.rw
**WASAC billing:** 📞 +250 788 123 456 | info@wasac.rw`,
      quickReplies: ['Book billing appointment','Request meter inspection','Contact IRIBA'],
    },

    // PLATFORM NAVIGATION
    {
      id: 'dashboard_guide',
      keywords: ['dashboard','how to use dashboard','navigate','find','where is','sidebar',
                 'menu','platform navigation','what can i do','features'],
      response: () => `**Temba Platform Navigation Guide:**

**Community Dashboard — Sidebar:**
📊 **Overview** — stats on your reports, appointments, and requests
📢 **My Reports** — all your submitted reports with status badges
📅 **Appointments** — book and manage meetings with providers
🔧 **Service Requests** — new connection, truck, meter, inspection
🏢 **Providers** — browse all registered providers
🔔 **Notifications** — status updates and announcements

**Provider Dashboard — Sidebar:**
📥 **Report Inbox** — all incoming reports (sorted P1 → P2 → P3)
📋 **Service Requests** — requests assigned to your organisation
📅 **Appointments** — manage bookings with community members
📊 **Analytics** — your SLA stats and response metrics
⚙️ **Availability** — set your working days, hours, and blackout dates

**Top right:** Your profile, language toggle (EN/KN), and notification bell`,
      quickReplies: ['How to submit a report','How to book appointment','How to track report','Switch to Kinyarwanda'],
    },

    {
      id: 'language',
      keywords: ['language','kinyarwanda','english','switch language','change language',
                 'translate','rw','french','français'],
      response: () => `**Language Settings:**

Temba supports **English** and **Kinyarwanda** across the web platform and USSD channel.

**Web — switch language:**
1. Look for the **globe icon 🌐** or **"EN / KN"** toggle in the top-right navigation bar
2. Click it to switch between English and Kinyarwanda
3. All labels, menus, and UI text will change instantly

**USSD — choose language at start:**
When you dial **\*384\*36640#**, the first prompt asks:
1. English
2. Kinyarwanda (Ikinyarwanda)

Your language choice is saved for that USSD session.

**SMS notifications** are sent in the language you selected when you registered your account.`,
      quickReplies: ['How to use USSD','Muraho — help in Kinyarwanda','Navigate the dashboard'],
    },

    // SLA / ACCOUNTABILITY
    {
      id: 'sla',
      keywords: ['sla','response time','deadline','how long','accountability','when will',
                 'resolution time','days to fix','hours to fix','provider not responding'],
      response: () => `**SLA & Accountability System:**

Every report gets an automatic **priority classification**:

| Priority | Category | SLA Deadline |
|----------|----------|-------------|
| 🔴 P1 Critical | Contamination, burst pipe | **4 hours** |
| 🟠 P2 Urgent | No supply, quality issues | **24 hours** |
| 🔵 P3 Standard | Low pressure, billing, other | **72 hours** |

**What happens if the deadline is missed?**

1. **0h overdue** → Provider's Duty Officer receives an escalation email
2. **+24h overdue** → Provider's Supervisor receives an escalation email

Both contacts were required during provider registration — there's always someone accountable.

**You can see** your report's SLA deadline and whether it's overdue from your dashboard.`,
      quickReplies: ['My provider is not responding','Track my report','What is P1 priority?'],
    },

    {
      id: 'provider_not_responding',
      keywords: ['not responding','no response','provider ignoring','no action','late response',
                 'overdue','past deadline','exceeded sla','nothing happening','weeks waiting'],
      response: () => `**If Your Provider Is Not Responding:**

1. **Check the SLA status** — Dashboard → My Reports → click the report
   - If overdue, escalation emails have already been sent to the provider's officer and supervisor

2. **Contact the provider directly:**
   - Use the phone number or email shown in your report detail
   - Reference your tracking code (RPT-...)

3. **Book an escalation appointment:**
   - Dashboard → Appointments → select the provider → reason: "Follow Up on Overdue Report"

4. **Escalate to RURA** (if no action after escalation):
   - Rwanda Utilities Regulatory Authority handles formal complaints against licensed providers
   - Document all reference numbers and dates

**The platform automatically tracks all overdue cases.** Provider non-compliance is monitored by Temba admins.`,
      quickReplies: ['Contact WASAC','Contact IRIBA','Book escalation appointment','What is RURA?'],
    },

    // ABOUT
    {
      id: 'about',
      keywords: ['about temba','what is temba','who made','mission','purpose','goal','platform info',
                 'about this platform','organisation behind','how does temba work'],
      response: () => `**About Temba Digital Bridge:**

Temba (Kinyarwanda: *"to push forward"*) is a civic-tech platform connecting Rwandan communities to water service providers.

**Mission:** Enable every Rwandan — whether online or on a basic phone — to report water issues, request services, and hold providers accountable.

**What Temba offers:**
🌐 **Web platform** — full-featured dashboard for community and providers
📱 **USSD** (*384*36640#) — works on any phone, no internet
📩 **SMS notifications** — updates in English & Kinyarwanda
⭐ **Anonymous ratings** — honest feedback on service quality
📊 **SLA enforcement** — automatic escalation when providers miss deadlines

**Registered Providers:**
WASAC · IRIBA Water Group · Pro Water Rwanda

**Coverage:** All 5 provinces across Rwanda's administrative hierarchy

Built as a final-year Software Engineering project at ALU (African Leadership University).`,
      quickReplies: ['How do I start?','View all providers','Use Temba without internet'],
    },

    // PROVIDERS EXPLICIT
    {
      id: 'providers_all',
      keywords: ['wasac','iriba','pro water','list providers','all providers','who is registered',
                 'provider list','water companies','contact provider','provider contacts'],
      response: () => {
        if (PROVIDERS.length) {
          const list = PROVIDERS.map(p => {
            const services = getMatchingServicesFor(p);
            return `🏢 **${p.organization_name}**\n📞 ${p.phone || 'N/A'} | ✉️ ${p.email || 'N/A'}\n🔹 ${services.map(s => s.label).join(' · ')}\n${p.description ? `_${p.description}_` : ''}`;
          }).join('\n\n');
          return `**Registered Water Service Providers on Temba:**\n\n${list}\n\nWant to **book an appointment** or find which provider is right for your service need?`;
        }
        return `**Registered Water Service Providers on Temba:**\n\n🏢 **WASAC** — National water & sanitation utility\n📞 +250 788 123 456 | info@wasac.rw\n🔹 Water Supply · Sanitation · Infrastructure\n\n🏢 **IRIBA Water Group** — Urban water distribution\n📞 +250 788 345 678 | support@iriba.rw\n🔹 Water Supply · Meter Services · Water Quality\n\n🏢 **Pro Water Rwanda** — Commercial water services\n📞 +250 788 567 890 | hello@prowater.rw\n🔹 Water Truck Delivery · Water Storage · Water Supply`;
      },
      quickReplies: ['Book appointment with WASAC','Book appointment with IRIBA','Water truck from Pro Water','Which provider for my area?'],
    },

    // DEFAULT
    {
      id: 'not_understood',
      keywords: [],
      response: () => `I didn't quite understand that — let me offer some topics I can help with:

💧 **Find a provider** — match you to the right one for your service
📢 **Report an issue** — water outage, contamination, pipe burst
🔍 **Track your report** — status updates and timeline
📅 **Book an appointment** — meet with a provider
🔧 **Request a service** — water connection, truck, meter support
📱 **USSD access** — use Temba on any phone without internet
❓ **Platform help** — dashboard navigation, account, password

Try rephrasing or tap one of the quick actions below.`,
      quickReplies: ['Find a water provider','Report water issue','Track my report','Use USSD *384*36640#'],
    }
  ];

  // ─── Service-intent detection ─────────────────────────────────────────────────
  function detectServiceIntent(text) {
    const lower = text.toLowerCase();
    const matched = new Set();
    for (const [phrase, categories] of Object.entries(INTENT_TO_SERVICE)) {
      if (lower.includes(phrase)) {
        categories.forEach(c => matched.add(c));
      }
    }
    return Array.from(matched);
  }

  // ─── Scoring engine ──────────────────────────────────────────────────────────
  function findBestMatch(input) {
    const lower = input.toLowerCase().trim();
    const words = lower.split(/\W+/).filter(w => w.length > 2);
    let bestScore = 0;
    let bestTopic = null;

    for (const topic of KB) {
      if (topic.id === 'not_understood') continue;
      let score = 0;
      for (const kw of (topic.keywords || [])) {
        if (lower.includes(kw)) {
          score += kw.split(' ').length * 5;
        } else {
          for (const word of words) {
            if (kw === word) score += 3;
            else if (kw.includes(word) && word.length > 3) score += 1;
          }
        }
      }
      if (score > bestScore) { bestScore = score; bestTopic = topic; }
    }

    return bestScore >= 2 ? bestTopic : KB.find(t => t.id === 'not_understood');
  }

  // ─── Build response with optional provider cards ─────────────────────────────
  function buildResponse(input) {
    const serviceCategories = detectServiceIntent(input);
    const topic = findBestMatch(input);

    // If we detected a service need AND have live provider data
    if (serviceCategories.length && providersLoaded) {
      const matched = matchProviders(serviceCategories);
      if (matched.length) {
        const textResponse = topic.response ? topic.response() : '';
        return {
          text: textResponse || `I found ${matched.length} provider${matched.length > 1 ? 's' : ''} that can help with your request:`,
          providerCards: renderProviderCards(matched, input),
          topic,
        };
      }
    }

    return {
      text: topic.response ? topic.response() : topic.response,
      providerCards: null,
      topic,
    };
  }

  // ─── Markdown renderer ───────────────────────────────────────────────────────
  function renderMd(text) {
    if (!text) return '';
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="tchat-link">$1</a>')
      // Simple table → HTML
      .replace(/\|(.+)\|\n\|[-| :]+\|\n((?:\|.+\|\n?)*)/g, (_, header, rows) => {
        const ths = header.split('|').filter(Boolean).map(h => `<th>${h.trim()}</th>`).join('');
        const trs = rows.trim().split('\n').map(row =>
          '<tr>' + row.split('|').filter(Boolean).map(c => `<td>${c.trim()}</td>`).join('') + '</tr>'
        ).join('');
        return `<table class="tchat-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
      })
      .replace(/\n/g, '<br>');
  }

  // ─── State ───────────────────────────────────────────────────────────────────
  const history = [];
  let isOpen = false;
  let unreadCount = 0;

  // ─── CSS ─────────────────────────────────────────────────────────────────────
  const style = document.createElement('style');
  style.textContent = `
    #temba-chat-fab {
      position:fixed;bottom:28px;right:28px;z-index:9000;
      width:58px;height:58px;border-radius:50%;
      background:linear-gradient(135deg,#1565C0,#29B6F6);
      border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;
      box-shadow:0 4px 24px rgba(21,101,192,.5);
      transition:transform .25s,box-shadow .25s;
      font-size:24px;color:#fff;
    }
    #temba-chat-fab:hover{transform:scale(1.1);box-shadow:0 6px 32px rgba(21,101,192,.6);}
    #temba-chat-badge{
      position:absolute;top:-4px;right:-4px;
      background:#C62828;color:#fff;
      font-size:11px;font-weight:700;
      width:20px;height:20px;border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      border:2px solid #fff;
    }
    #temba-chat-panel{
      position:fixed;bottom:98px;right:28px;z-index:8999;
      width:380px;max-height:600px;
      background:#fff;border-radius:20px;
      box-shadow:0 8px 48px rgba(10,37,64,.2);
      display:flex;flex-direction:column;
      transform:translateY(24px) scale(.95);
      opacity:0;pointer-events:none;
      transition:transform .3s cubic-bezier(.34,1.56,.64,1),opacity .25s;
      overflow:hidden;
      font-family:'Plus Jakarta Sans',system-ui,sans-serif;
    }
    #temba-chat-panel.open{transform:translateY(0) scale(1);opacity:1;pointer-events:all;}
    .tchat-header{
      background:linear-gradient(135deg,#0A2540,#1565C0);
      padding:14px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0;
    }
    .tchat-avatar{
      width:38px;height:38px;border-radius:50%;
      background:rgba(255,255,255,.15);
      display:flex;align-items:center;justify-content:center;
      font-size:19px;color:#fff;flex-shrink:0;
    }
    .tchat-header-info{flex:1;}
    .tchat-title{font-size:14px;font-weight:700;color:#fff;}
    .tchat-subtitle{font-size:11px;color:rgba(255,255,255,.75);margin-top:1px;}
    .tchat-online{width:7px;height:7px;border-radius:50%;background:#4CAF50;display:inline-block;margin-right:4px;}
    .tchat-hbtn{background:none;border:none;color:rgba(255,255,255,.8);font-size:17px;cursor:pointer;padding:5px;border-radius:6px;transition:background .15s;}
    .tchat-hbtn:hover{background:rgba(255,255,255,.18);color:#fff;}
    .tchat-msgs{flex:1;overflow-y:auto;padding:14px 14px 6px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth;}
    .tchat-msgs::-webkit-scrollbar{width:4px;}
    .tchat-msgs::-webkit-scrollbar-thumb{background:#E2E8F0;border-radius:4px;}
    .tchat-msg{display:flex;gap:8px;align-items:flex-end;}
    .tchat-msg.user{flex-direction:row-reverse;}
    .tchat-bubble{max-width:84%;padding:10px 13px;border-radius:14px;font-size:13px;line-height:1.6;word-break:break-word;}
    .tchat-msg.bot .tchat-bubble{background:#F0F4F8;color:#1E293B;border-bottom-left-radius:4px;}
    .tchat-msg.user .tchat-bubble{background:linear-gradient(135deg,#1565C0,#29B6F6);color:#fff;border-bottom-right-radius:4px;}
    .tchat-bot-icon{width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,#0A2540,#1565C0);display:flex;align-items:center;justify-content:center;font-size:14px;color:#fff;flex-shrink:0;}
    .tchat-msg.user .tchat-bot-icon{display:none;}
    .tchat-time{font-size:10px;color:#94A3B8;margin-top:4px;}
    .tchat-msg.bot .tchat-time{text-align:left;}
    .tchat-msg.user .tchat-time{text-align:right;}
    /* Provider cards */
    .tchat-provider-list{display:flex;flex-direction:column;gap:8px;margin-top:8px;}
    .tchat-provider-card{
      background:#fff;border:1.5px solid #E2E8F0;border-radius:12px;
      padding:12px 13px;box-shadow:0 2px 8px rgba(0,0,0,.06);
    }
    .tchat-prov-name{font-weight:700;font-size:13px;color:#0F172A;margin-bottom:3px;}
    .tchat-prov-desc{font-size:11.5px;color:#64748B;margin-bottom:6px;line-height:1.4;}
    .tchat-badge-row{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px;}
    .tchat-badge{background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE;border-radius:20px;padding:2px 9px;font-size:11px;font-weight:600;}
    .tchat-prov-actions{display:flex;flex-wrap:wrap;gap:6px;}
    .tchat-prov-action{
      padding:5px 11px;border-radius:8px;font-size:11.5px;font-weight:600;cursor:pointer;
      text-decoration:none;border:none;display:inline-flex;align-items:center;gap:4px;
      transition:opacity .15s;font-family:inherit;
    }
    .tchat-prov-action:hover{opacity:.8;}
    .tchat-prov-call{background:#E8F5E9;color:#1B5E20;}
    .tchat-prov-email{background:#E3F2FD;color:#0D47A1;}
    .tchat-prov-book{background:linear-gradient(135deg,#1565C0,#29B6F6);color:#fff;}
    /* Quick replies */
    .tchat-qrs{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px;}
    .tchat-qr{
      background:#fff;border:1.5px solid #1565C0;color:#1565C0;
      border-radius:20px;padding:5px 12px;font-size:12px;font-weight:600;
      cursor:pointer;transition:background .15s,color .15s;
      font-family:'Plus Jakarta Sans',system-ui,sans-serif;
    }
    .tchat-qr:hover{background:#1565C0;color:#fff;}
    /* Professional box */
    .tchat-pro{background:#FFF8E1;border:1.5px solid #FFD54F;border-radius:10px;padding:10px 12px;margin-top:8px;font-size:12px;color:#5D4037;}
    .tchat-pro strong{color:#E65100;}
    .tchat-pro-btn{
      display:inline-flex;align-items:center;gap:5px;margin-top:8px;padding:7px 14px;
      background:#E65100;color:#fff;border:none;border-radius:8px;
      font-size:12px;font-weight:600;cursor:pointer;transition:background .2s;font-family:inherit;
    }
    .tchat-pro-btn:hover{background:#BF360C;}
    /* Table */
    .tchat-table{border-collapse:collapse;width:100%;font-size:12px;margin:6px 0;}
    .tchat-table th,.tchat-table td{border:1px solid #E2E8F0;padding:5px 8px;text-align:left;}
    .tchat-table th{background:#F0F4F8;font-weight:700;}
    /* Typing */
    .tchat-typing-row{display:flex;align-items:center;gap:8px;padding:0 14px 4px;flex-shrink:0;}
    .tchat-typing-dots{display:flex;gap:4px;padding:8px 12px;background:#F0F4F8;border-radius:14px;border-bottom-left-radius:4px;}
    .tchat-typing-dots span{width:7px;height:7px;border-radius:50%;background:#94A3B8;animation:tBounce 1.2s infinite;}
    .tchat-typing-dots span:nth-child(2){animation-delay:.2s;}
    .tchat-typing-dots span:nth-child(3){animation-delay:.4s;}
    @keyframes tBounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}
    /* Input */
    .tchat-input-row{display:flex;gap:8px;padding:10px 14px 13px;border-top:1px solid #F0F4F8;flex-shrink:0;background:#fff;}
    .tchat-input{
      flex:1;padding:9px 14px;border:1.5px solid #E2E8F0;
      border-radius:24px;font-size:13px;font-family:inherit;
      outline:none;transition:border-color .2s;color:#1E293B;background:#F8FAFB;
    }
    .tchat-input:focus{border-color:#29B6F6;background:#fff;}
    .tchat-send{
      width:38px;height:38px;border-radius:50%;
      background:linear-gradient(135deg,#1565C0,#29B6F6);
      border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;
      font-size:16px;color:#fff;flex-shrink:0;
      transition:transform .2s,box-shadow .2s;
    }
    .tchat-send:hover{transform:scale(1.1);box-shadow:0 3px 12px rgba(21,101,192,.4);}
    .tchat-footer{font-size:10px;color:#94A3B8;text-align:center;padding:0 14px 10px;flex-shrink:0;}
    .tchat-link{color:#1565C0;text-decoration:underline;}
    @media(max-width:440px){
      #temba-chat-panel{width:calc(100vw - 16px);right:8px;bottom:80px;max-height:80vh;}
      #temba-chat-fab{right:16px;bottom:16px;}
    }
  `;
  document.head.appendChild(style);

  // ─── HTML scaffold ────────────────────────────────────────────────────────────
  const root = document.createElement('div');
  root.id = 'temba-chat-root';
  root.innerHTML = `
    <div id="temba-chat-panel" role="dialog" aria-label="Temba Assistant">
      <div class="tchat-header">
        <div class="tchat-avatar">💧</div>
        <div class="tchat-header-info">
          <div class="tchat-title">Temba Assistant</div>
          <div class="tchat-subtitle"><span class="tchat-online"></span>Online — Water &amp; Sanitation Guide</div>
        </div>
        <button class="tchat-hbtn" onclick="tembaChat.close()" title="Close">✕</button>
      </div>
      <div class="tchat-msgs" id="tchat-msgs"></div>
      <div class="tchat-typing-row" id="tchat-typing" style="display:none;">
        <div class="tchat-bot-icon" style="width:24px;height:24px;font-size:12px;">💧</div>
        <div class="tchat-typing-dots"><span></span><span></span><span></span></div>
      </div>
      <div class="tchat-input-row">
        <input class="tchat-input" id="tchat-input" type="text"
               placeholder="Ask about water services, providers…"
               autocomplete="off"
               onkeydown="if(event.key==='Enter')tembaChat.send()">
        <button class="tchat-send" onclick="tembaChat.send()" title="Send">➤</button>
      </div>
      <div class="tchat-footer">Temba AI · Emergencies: call 912 or provider directly</div>
    </div>
    <button id="temba-chat-fab" onclick="tembaChat.toggle()" title="Open Temba Assistant">
      💧
      <span id="temba-chat-badge" style="display:none;position:absolute;top:-4px;right:-4px;background:#C62828;color:#fff;font-size:11px;font-weight:700;width:20px;height:20px;border-radius:50%;display:none;align-items:center;justify-content:center;border:2px solid #fff;"></span>
    </button>
  `;
  document.body.appendChild(root);

  // ─── Helpers ─────────────────────────────────────────────────────────────────
  function timeStr() {
    return new Date().toLocaleTimeString('en-RW', { hour: '2-digit', minute: '2-digit' });
  }

  function appendMessage(role, content, providerCards, topic) {
    const msgs = document.getElementById('tchat-msgs');
    const div = document.createElement('div');
    div.className = `tchat-msg ${role}`;

    if (role === 'user') {
      div.innerHTML = `
        <div class="tchat-bubble">${renderMd(content)}</div>
        <div class="tchat-time">${timeStr()}</div>`;
    } else {
      let inner = `
        <div class="tchat-bot-icon">💧</div>
        <div>
          <div class="tchat-bubble">${renderMd(content)}</div>
          ${providerCards || ''}`;

      if (topic && topic.professional) {
        inner += `<div class="tchat-pro">
          <strong>⚡ This needs a professional</strong><br>
          ${topic.professionalMsg}
          <br>
          <button class="tchat-pro-btn" onclick="tembaChat.connectPro()">
            📞 Connect to Professional
          </button>
        </div>`;
      }

      if (topic && topic.quickReplies && topic.quickReplies.length) {
        const qr = topic.quickReplies.map(q =>
          `<button class="tchat-qr" onclick="tembaChat.quickReply('${q.replace(/'/g, "\\'")}')">${q}</button>`
        ).join('');
        inner += `<div class="tchat-qrs">${qr}</div>`;
      }

      inner += `<div class="tchat-time">${timeStr()}</div></div>`;
      div.innerHTML = inner;
    }

    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function showTyping() {
    document.getElementById('tchat-typing').style.display = 'flex';
    document.getElementById('tchat-msgs').scrollTop = 99999;
  }
  function hideTyping() {
    document.getElementById('tchat-typing').style.display = 'none';
  }

  function bumpBadge() {
    if (!isOpen) {
      unreadCount++;
      const b = document.getElementById('temba-chat-badge');
      b.textContent = unreadCount;
      b.style.display = 'flex';
    }
  }

  // ─── Public API ──────────────────────────────────────────────────────────────
  window.tembaChat = {
    toggle() { isOpen ? this.close() : this.open(); },

    open() {
      isOpen = true;
      document.getElementById('temba-chat-panel').classList.add('open');
      unreadCount = 0;
      const b = document.getElementById('temba-chat-badge');
      b.style.display = 'none';
      if (history.length === 0) {
        setTimeout(() => {
          const greeting = KB.find(t => t.id === 'greeting');
          appendMessage('bot', greeting.response(), null, greeting);
          history.push('greeting');
        }, 200);
      }
      setTimeout(() => document.getElementById('tchat-input').focus(), 300);
    },

    close() {
      isOpen = false;
      document.getElementById('temba-chat-panel').classList.remove('open');
    },

    send(override) {
      const input = document.getElementById('tchat-input');
      const text = (override || input.value).trim();
      if (!text) return;
      input.value = '';

      appendMessage('user', text);
      history.push({ role: 'user', text });

      showTyping();
      setTimeout(() => {
        hideTyping();
        const result = buildResponse(text);
        appendMessage('bot', result.text, result.providerCards, result.topic);
        history.push({ role: 'bot', id: result.topic.id });
        bumpBadge();
      }, 500 + Math.random() * 600);
    },

    quickReply(text) { this.send(text); },

    connectPro() {
      showTyping();
      setTimeout(() => {
        hideTyping();
        const msg = `**Connecting you to professional support:**

📞 **WASAC Emergency:** +250 788 123 456
📞 **IRIBA Water Group:** +250 788 345 678
📞 **Pro Water Rwanda:** +250 788 567 890
🚨 **Rwanda Emergency Services:** 912

**Or book a formal appointment:**
Dashboard → Appointments → select your provider → "Book Appointment"

**Via USSD:** Dial **\*384\*36640#** → after login → Book Appointment`;
        const topic = {
          professional: false,
          quickReplies: ['Book appointment now', 'View all providers', 'Track my report'],
        };
        appendMessage('bot', msg, null, topic);
        bumpBadge();
      }, 700);
    },

    // Navigate to booking with a specific provider pre-selected
    _bookWith(providerId, providerName) {
      const msg = `**Booking an appointment with ${providerName}:**

1. Go to your **Dashboard** → **Appointments**
2. Click **"Book Appointment"**
3. Select **${providerName}** from the provider list
4. Choose your reason, date, and time slot
5. Submit

[Open Dashboard →](dashboard-community.html)

Or if you're not logged in yet: [Sign In →](signin.html)`;
      showTyping();
      setTimeout(() => {
        hideTyping();
        const topic = {
          professional: false,
          quickReplies: ['Go to dashboard', 'Sign in first', 'Cancel appointment instead'],
        };
        appendMessage('bot', msg, null, topic);
        bumpBadge();
      }, 500);
    },
  };

  // ─── Init: load providers, then show badge after 4s ──────────────────────────
  loadProviders();

  setTimeout(() => {
    if (!isOpen) {
      unreadCount = 1;
      const b = document.getElementById('temba-chat-badge');
      b.textContent = '1';
      b.style.display = 'flex';
    }
  }, 4000);

}());
