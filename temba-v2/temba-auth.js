/* ═════════════════════════════════════════
   TEMBA — temba-auth.js
   Shared auth logic: tab switch, step nav,
   Rwanda cascade, validation, password tools
   ═════════════════════════════════════════ */

/* ── TAB SWITCHING ── */
function switchTab(tab) {
  const isCom = tab === 'community';
  document.getElementById('communityForm').style.display = isCom ? 'block' : 'none';
  document.getElementById('providerForm').style.display  = isCom ? 'none'  : 'block';
  document.getElementById('tabC').classList.toggle('active', isCom);
  document.getElementById('tabP').classList.toggle('active', !isCom);
}

/* ── COMMUNITY STEPS ── */
let cStep = 1;
function cGoTo(n) {
  if (n > cStep && !cValidate(cStep)) return;
  document.getElementById('cStep' + cStep).classList.remove('active');
  document.getElementById('cStep' + n).classList.add('active');
  updateSteps('c', n, 3, ['cline1','cline2']);
  cStep = n;
  document.querySelector('.auth-page')?.scrollTo({ top: 0, behavior: 'smooth' });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function cValidate(step) {
  if (step === 1) {
    if (!v('cFirstName'))  return err('cFirstName', 'First name is required');
    if (!v('cLastName'))   return err('cLastName',  'Last name is required');
    if (!v('cPhone'))      return err('cPhone',     'Phone number is required');
    const idType = document.querySelector('input[name="cIdType"]:checked')?.value;
    if (idType === 'passport') {
      if (!v('cPassport')) return err('cPassport', 'Passport number is required');
    } else {
      const nid = document.getElementById('cNid')?.value || '';
      if (nid.length < 16) return err('cNid', 'Enter a valid 16-digit NID');
    }
    if (!document.querySelector('input[name="cGender"]:checked')) {
      showTembaToast('Please select your gender'); return false;
    }
    if (!v('cLang')) return err('cLang', 'Please choose a language');
    return true;
  }
  if (step === 2) {
    if (!v('cProvince')) return err('cProvince', 'Select a province');
    if (!v('cDistrict')) return err('cDistrict', 'Select a district');
    if (!v('cSector'))   return err('cSector',   'Select a sector');
    if (!v('cCell'))     return err('cCell',      'Select a cell');
    if (!v('cVillage'))  return err('cVillage',   'Select a village');
    return true;
  }
  return true;
}

/* ── PROVIDER STEPS ── */
let pStep = 1;
function pGoTo(n) {
  if (n > pStep && !pValidate(pStep)) return;
  document.getElementById('pStep' + pStep).classList.remove('active');
  document.getElementById('pStep' + n).classList.add('active');
  updateSteps('p', n, 3, ['pline1','pline2']);
  pStep = n;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function pValidate(step) {
  if (step === 1) {
    if (!v('pOrgName'))  return err('pOrgName',  'Organisation name is required');
    if (document.getElementById('pServiceType')) {
      if (!v('pServiceType')) return err('pServiceType', 'Select a service type');
      if (document.getElementById('pServiceType').value === 'other') {
        if (!v('pOtherSvc')) return err('pOtherSvc', 'Please describe your water service');
      }
    }
    if (!v('pLicence'))  return err('pLicence',  'Licence number is required');
    if (!v('pCoverage')) return err('pCoverage', 'Select your coverage area');
    if (document.getElementById('pCoverage')?.value === 'specific') {
      if (!v('pSpecificDist')) return err('pSpecificDist', 'Please list the districts you operate in');
    }
    if (!v('pOrgPhone'))  return err('pOrgPhone',  'Organisation phone is required');
    if (!v('pOrgEmail') || !isEmail(fv('pOrgEmail'))) return err('pOrgEmail', 'A valid email is required');
    return true;
  }
  if (step === 2) {
    if (!v('pAdminFirst'))  return err('pAdminFirst', 'First name is required');
    if (!v('pAdminLast'))   return err('pAdminLast',  'Last name is required');
    if (!v('pTitle'))       return err('pTitle',      'Job title is required');
    if (!v('pAdminPhone'))  return err('pAdminPhone', 'Admin phone is required');
    if (!v('pAdminEmail') || !isEmail(fv('pAdminEmail'))) return err('pAdminEmail', 'A valid email is required');
    return true;
  }
  return true;
}

function updateSteps(prefix, active, total, lineIds) {
  for (let i = 1; i <= total; i++) {
    const dot = document.getElementById(prefix + 's' + i);
    if (!dot) continue;
    dot.classList.remove('active','done');
    if (i < active)  dot.classList.add('done');
    if (i === active) dot.classList.add('active');
  }
  lineIds.forEach((id, idx) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('done', active > idx + 1);
  });
}

/* ── RWANDA CASCADE ── */
document.addEventListener('DOMContentLoaded', () => {
  const pEl = document.getElementById('cProvince');
  if (pEl && typeof RWANDA !== 'undefined') {
    Object.keys(RWANDA).sort().forEach(p => pEl.appendChild(new Option(p, p)));
  }
  const villEl = document.getElementById('cVillage');
  if (villEl) villEl.addEventListener('change', updateLocPreview);
  loadCustomSvcs();
});

function onProvinceChange() {
  const prov = fv('cProvince');
  resetSels(['cDistrict','cSector','cCell','cVillage'],
            ['Select district','Select district first','Select sector first','Select cell first']);
  if (!prov || !RWANDA?.[prov]) return;
  const el = document.getElementById('cDistrict');
  el.disabled = false;
  el.innerHTML = '<option value="" disabled selected>Select district</option>';
  Object.keys(RWANDA[prov]).sort().forEach(d => el.appendChild(new Option(d, d)));
  updateLocPreview();
}

function onDistrictChange() {
  const prov = fv('cProvince'), dist = fv('cDistrict');
  resetSels(['cSector','cCell','cVillage'],['Select sector','Select sector first','Select cell first']);
  if (!prov || !dist || !RWANDA?.[prov]?.[dist]) return;
  const el = document.getElementById('cSector');
  el.disabled = false;
  el.innerHTML = '<option value="" disabled selected>Select sector</option>';
  Object.keys(RWANDA[prov][dist]).sort().forEach(s => el.appendChild(new Option(s, s)));
  updateLocPreview();
}

function onSectorChange() {
  const prov = fv('cProvince'), dist = fv('cDistrict'), sect = fv('cSector');
  resetSels(['cCell','cVillage'],['Select cell','Select cell first']);
  if (!prov || !dist || !sect || !RWANDA?.[prov]?.[dist]?.[sect]) return;
  const el = document.getElementById('cCell');
  el.disabled = false;
  el.innerHTML = '<option value="" disabled selected>Select cell</option>';
  Object.keys(RWANDA[prov][dist][sect]).sort().forEach(c => el.appendChild(new Option(c, c)));
}

function onCellChange() {
  const prov = fv('cProvince'), dist = fv('cDistrict'), sect = fv('cSector'), cell = fv('cCell');
  resetSels(['cVillage'],['Select village']);
  const villages = RWANDA?.[prov]?.[dist]?.[sect]?.[cell];
  if (!villages) return;
  const el = document.getElementById('cVillage');
  el.disabled = false;
  el.innerHTML = '<option value="" disabled selected>Select village</option>';
  [...villages].sort().forEach(vl => el.appendChild(new Option(vl, vl)));
  updateLocPreview();
}

function resetSels(ids, labels) {
  ids.forEach((id, i) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = true;
    el.innerHTML = `<option value="" disabled selected>${labels[i]}</option>`;
  });
  updateLocPreview();
}

function updateLocPreview() {
  const parts = [fv('cVillage'), fv('cCell'), fv('cSector'), fv('cDistrict'), fv('cProvince')].filter(Boolean);
  const preview = document.getElementById('locPreview');
  const text    = document.getElementById('locPreviewText');
  if (preview && text) {
    if (parts.length >= 2) {
      text.textContent = parts.join(' → ');
      preview.style.display = 'flex';
    } else {
      preview.style.display = 'none';
    }
  }
}

/* ── ID TYPE TOGGLE ── */
function onIdType(prefix) {
  const type = document.querySelector(`input[name="${prefix}IdType"]:checked`)?.value;
  const nWrap = document.getElementById(`${prefix}NidWrap`);
  const pWrap = document.getElementById(`${prefix}PassWrap`);
  const hint  = document.getElementById(`${prefix}IdHint`);
  if (type === 'passport') {
    if (nWrap) nWrap.style.display = 'none';
    if (pWrap) pWrap.style.display = 'flex';
    if (hint)  hint.textContent = 'Enter your passport number exactly as it appears on the document';
  } else {
    if (nWrap) nWrap.style.display = 'flex';
    if (pWrap) pWrap.style.display = 'none';
    if (hint)  hint.textContent = 'Used to verify your identity';
  }
}

/* ── SERVICE TYPE ── */
const CUSTOM_SVC_KEY = 'temba_custom_services';

function loadCustomSvcs() {
  const sel = document.getElementById('pServiceType');
  if (!sel) return;
  const saved = JSON.parse(localStorage.getItem(CUSTOM_SVC_KEY) || '[]');
  const other = [...sel.options].find(o => o.value === 'other');
  saved.forEach(svc => {
    if (![...sel.options].find(o => o.text === svc)) {
      const opt = new Option(svc, svc);
      sel.insertBefore(opt, other);
    }
  });
}

function onServiceType() {
  const sel = document.getElementById('pServiceType');
  const rev = document.getElementById('otherSvcReveal');
  if (rev) rev.classList.toggle('open', sel?.value === 'other');
}

function addCustomSvc() {
  const input = document.getElementById('pOtherSvc');
  const svc   = input?.value.trim();
  if (!svc) { showTembaToast('Please type a service name first'); return; }
  const sel   = document.getElementById('pServiceType');
  const other = [...sel.options].find(o => o.value === 'other');
  if ([...sel.options].find(o => o.text.toLowerCase() === svc.toLowerCase())) {
    showTembaToast('This service is already in the list'); return;
  }
  const opt = new Option(svc, svc);
  sel.insertBefore(opt, other);
  sel.value = svc;
  document.getElementById('otherSvcReveal').classList.remove('open');
  input.value = '';
  const saved = JSON.parse(localStorage.getItem(CUSTOM_SVC_KEY) || '[]');
  if (!saved.includes(svc)) { saved.push(svc); localStorage.setItem(CUSTOM_SVC_KEY, JSON.stringify(saved)); }
  showTembaToast(`"${svc}" added ✓`, 'success');
}

/* ── COVERAGE AREA ── */
function onCoverage() {
  const sel = document.getElementById('pCoverage');
  const rev = document.getElementById('specificDistReveal');
  if (rev) rev.classList.toggle('open', sel?.value === 'specific');
}

/* ── PASSWORD TOOLS ── */
function checkStrength(val) {
  const fill = document.getElementById('cStrFill');
  const lbl  = document.getElementById('cStrLbl');
  if (!fill) return;
  let score = 0;
  if (val.length >= 8)          score++;
  if (/[A-Z]/.test(val))        score++;
  if (/[0-9]/.test(val))        score++;
  if (/[^A-Za-z0-9]/.test(val)) score++;
  const levels = [
    { w:'0%',   bg:'#ddd',     txt:'',       col:'' },
    { w:'25%',  bg:'#C62828',  txt:'Weak',   col:'#C62828' },
    { w:'50%',  bg:'#E65100',  txt:'Fair',   col:'#E65100' },
    { w:'75%',  bg:'#29B6F6',  txt:'Good',   col:'#1565C0' },
    { w:'100%', bg:'#2E7D32',  txt:'Strong', col:'#2E7D32' },
  ];
  const l = levels[score];
  fill.style.width = l.w; fill.style.background = l.bg;
  lbl.textContent = l.txt; lbl.style.color = l.col;
}

function checkMatch(id1, id2, msgId) {
  const p1 = document.getElementById(id1)?.value;
  const p2 = document.getElementById(id2)?.value;
  const el = document.getElementById(msgId);
  if (!p2 || !el) return;
  if (p1 === p2) { el.textContent = '✓ Passwords match'; el.style.color = '#2E7D32'; }
  else           { el.textContent = '✗ Passwords do not match'; el.style.color = '#C62828'; }
}

function togglePw(id, btn) {
  const f = document.getElementById(id);
  if (!f) return;
  const show = f.type === 'text';
  f.type = show ? 'password' : 'text';
  const i = btn.querySelector('i');
  if (i) i.className = show ? 'ti ti-eye' : 'ti ti-eye-off';
}

/* ── LOCAL CREDENTIAL STORE (works when backend is offline) ── */
async function _hashPw(pw) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(pw));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
function _saveLocalAccount(data) {
  const all = JSON.parse(localStorage.getItem('temba_accounts') || '[]');
  const idx = all.findIndex(a => a.email === data.email);
  if (idx >= 0) all[idx] = data; else all.push(data);
  localStorage.setItem('temba_accounts', JSON.stringify(all));
}
function _getLocalAccount(email) {
  const all = JSON.parse(localStorage.getItem('temba_accounts') || '[]');
  return all.find(a => a.email === email.toLowerCase().trim()) || null;
}

/* ── SUBMIT ── */
async function handleSubmit(type) {
  const isCom = type === 'community';
  const pw    = document.getElementById(isCom ? 'cPw'    : 'pPw')?.value;
  const conf  = document.getElementById(isCom ? 'cPwConf': 'pPwConf')?.value;
  const terms = document.getElementById(isCom ? 'cTerms' : 'pTerms');
  if (!pw || pw.length < 8)                              { showTembaToast('Password must be at least 8 characters'); return; }
  if (!/[A-Z]/.test(pw))                                { showTembaToast('Password must contain at least one uppercase letter (e.g. A–Z)'); return; }
  if (!/[0-9]/.test(pw))                                { showTembaToast('Password must contain at least one number (e.g. 1, 2, 3)'); return; }
  if (!/[!@#$%^&*()\-_=+\[\]{}|;:'",.<>?/]/.test(pw)) { showTembaToast('Password must contain at least one special character (e.g. @, !, #, $)'); return; }
  if (pw !== conf)                                       { showTembaToast('Passwords do not match'); return; }
  if (!terms?.checked)                                   { showTembaToast('Please accept the Terms of Use to continue'); return; }

  const _API = ['localhost','127.0.0.1'].includes(window.location.hostname)
    ? 'http://127.0.0.1:8000/api/v1' : 'https://temba-api-production.up.railway.app/api/v1';
  let token = null;

  /* Collect all registration data up-front */
  let email, fullName, phone, orgName, orgPhone, orgEmail, licence, coverage, cats,
      adminPhone, title;
  if (isCom) {
    email    = fv('cEmail');
    fullName = [fv('cFirstName'), fv('cLastName')].filter(Boolean).join(' ') || 'Community Member';
    const pCode = document.getElementById('cPhoneCode')?.value || '+250';
    const pNum  = fv('cPhone').replace(/\D/g, '');
    phone   = pNum ? `${pCode}${pNum}` : null;
    orgName = null;
  } else {
    email     = fv('pAdminEmail');
    const adminName = [fv('pAdminFirst'), fv('pAdminLast')].filter(Boolean).join(' ') || fv('pOrgName');
    fullName  = adminName;
    orgName   = fv('pOrgName');
    const orgCode = document.getElementById('pOrgPhoneCode')?.value || '+250';
    const orgNum  = fv('pOrgPhone').replace(/\D/g, '');
    orgPhone  = orgNum ? `${orgCode}${orgNum}` : null;
    const admCode = document.getElementById('pAdminPhoneCode')?.value || '+250';
    const admNum  = fv('pAdminPhone').replace(/\D/g, '');
    adminPhone = admNum ? `${admCode}${admNum}` : null;
    phone     = orgPhone;
    orgEmail  = fv('pOrgEmail') || email;
    licence   = fv('pLicence') || null;
    coverage  = document.getElementById('pCoverage')?.value || '';
    title     = fv('pTitle') || null;
    cats      = typeof getSelectedSvcCategories === 'function' ? getSelectedSvcCategories() : [];
    /* Include any custom "other" services saved in localStorage */
    const customSvcs = JSON.parse(localStorage.getItem('temba_custom_services') || '[]');
    customSvcs.forEach(s => { if (!cats.includes(s)) cats.push(s); });
  }
  const name = isCom ? (fv('cFirstName') || 'Member') : (orgName || 'Provider');
  const lang = document.getElementById(isCom ? 'cLang' : 'pLang')?.value || 'en';

  try {
    const _fetch = (typeof window !== 'undefined' && window._serverFetch) ? window._serverFetch : fetch;
    if (isCom) {
      const r = await _fetch(`${_API}/auth/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pw, full_name: fullName, role: 'community', phone })
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        showTembaToast(_errMsg(e, 'Registration failed. Please try again.'), 'error'); return;
      }
      const lr = await _fetch(`${_API}/auth/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pw })
      });
      if (lr.ok) { const td = await lr.json(); token = td.access_token; localStorage.setItem('temba_token', token); if (td.refresh_token) localStorage.setItem('temba_refresh_token', td.refresh_token); }

    } else {
      const rr = await _fetch(`${_API}/auth/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pw, full_name: fullName, role: 'provider' })
      });
      if (!rr.ok) {
        const e = await rr.json().catch(() => ({}));
        showTembaToast(_errMsg(e, 'Registration failed. Please try again.'), 'error'); return;
      }
      const lr = await _fetch(`${_API}/auth/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pw })
      });
      if (lr.ok) {
        const td = await lr.json();
        token = td.access_token;
        localStorage.setItem('temba_token', token);
        if (td.refresh_token) localStorage.setItem('temba_refresh_token', td.refresh_token);
        const isNational = !coverage || coverage.toLowerCase().includes('national') || coverage.toLowerCase().includes('all');
        const serviceAreas = isNational
          ? ['Kigali City','Northern Province','Southern Province','Eastern Province','Western Province'].map(p => ({ province: p }))
          : [{ province: 'Kigali City' }];
        const descEl = document.getElementById('pDescription');
        const slaResp = document.getElementById('pSlaResponse')?.value;
        const slaRes  = document.getElementById('pSlaResolution')?.value;
        const supName  = document.getElementById('pSupName')?.value || '';
        const supEmail = document.getElementById('pSupEmail')?.value || '';
        const supPhoneCode = document.getElementById('pSupPhoneCode')?.value || '+250';
        const supPhoneNum  = document.getElementById('pSupPhone')?.value || '';
        const supPhone = supPhoneNum ? supPhoneCode + supPhoneNum.replace(/\s+/g, '') : '';

        await _fetch(`${_API}/providers/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            organization_name: orgName,
            registration_number: licence,
            service_categories: cats.length ? cats : ['water_supply'],
            description: descEl?.value || `${orgName} — water service provider registered on Temba Digital Bridge.`,
            phone: orgPhone,
            email: orgEmail,
            website: document.getElementById('pWebsite')?.value || null,
            service_areas: serviceAreas,
            sla_response_hours: parseInt(slaResp) || 4,
            sla_resolution_hours: parseInt(slaRes) || 24,
            officer: {
              name: name,
              email: email,
              phone: phone,
            },
            supervisor: {
              name: supName,
              email: supEmail,
              phone: supPhone,
            },
          })
        });
      }
    }
  } catch (_) {
    /* API unreachable — save locally. Warn the user so they know their account
       is device-only until they sign in again when online (auto-sync happens on login). */
    showTembaToast(
      'No internet connection — your account was saved on this device. Sign in once you\'re back online to activate it on all devices.',
      'warning'
    );
  }

  /* Always save credentials locally so sign-in works even when server is offline */
  const pwHash = await _hashPw(pw);
  const gender = isCom
    ? (document.querySelector('input[name="cGender"]:checked')?.value || null)
    : null;
  const firstName = isCom ? fv('cFirstName') : fv('pAdminFirst');
  const lastName  = isCom ? fv('cLastName')  : fv('pAdminLast');
  _saveLocalAccount({
    email:      email.toLowerCase().trim(),
    phone,
    passwordHash: pwHash,
    role:       type,
    name,
    firstName,
    lastName,
    gender,
    orgName,
    orgPhone:   isCom ? null : (orgPhone  || null),
    orgEmail:   isCom ? null : (orgEmail  || null),
    adminPhone: isCom ? null : (adminPhone|| null),
    title:      isCom ? null : (title     || null),
    licence:    isCom ? null : (licence   || null),
    coverage:   isCom ? null : (coverage  || null),
    services:   isCom ? null : (cats.length ? cats : null),
    province:   isCom ? fv('cProvince') : null,
    district:   isCom ? fv('cDistrict') : null,
    sector:     isCom ? fv('cSector')   : null,
    cell:       isCom ? fv('cCell')     : null,
    lang,
    createdAt:  new Date().toISOString()
  });
  localStorage.setItem('temba_lang', lang);

  /* Show success screen and auto-redirect to sign-in */
  document.getElementById('communityForm').style.display = 'none';
  document.getElementById('providerForm').style.display  = 'none';
  const cta = document.getElementById('signinCta');
  if (cta) cta.style.display = 'none';
  document.getElementById('successScreen').style.display = 'block';
  document.getElementById('successTitle').textContent = isCom ? 'Account Created!' : 'Account Activated!';
  document.getElementById('successMsg').textContent = isCom
    ? `Welcome, ${name}! Your account is ready. Sign in with your email and password to get started.`
    : `Welcome, ${orgName || name}! Your provider account is active. Sign in to access your dashboard.`;

  /* Countdown redirect */
  let secs = 5;
  const cd = document.getElementById('successCountdown');
  const tick = () => { if (cd) cd.textContent = secs > 0 ? `Redirecting to sign in in ${secs}s…` : 'Redirecting…'; };
  tick();
  const iv = setInterval(() => { secs--; tick(); if (secs <= 0) { clearInterval(iv); window.location.href = 'signin.html'; } }, 1000);
}

/* ── UTILITIES ── */
function v(id)  { const el = document.getElementById(id); return el ? el.value.trim() !== '' : false; }
function fv(id) { return document.getElementById(id)?.value.trim() || ''; }
function isEmail(s) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s); }

function _errMsg(e, fallback) {
  if (!e || !e.detail) return fallback;
  if (typeof e.detail === 'string') return e.detail;
  if (Array.isArray(e.detail)) {
    return e.detail.map(d => (d.msg || String(d)).replace(/^Value error,\s*/i, '')).join('. ');
  }
  return fallback;
}

function err(id, msg) {
  const el = document.getElementById(id);
  if (el) {
    el.focus();
    el.style.borderColor = 'var(--red)';
    el.style.boxShadow   = '0 0 0 3px rgba(198,40,40,0.1)';
    setTimeout(() => { el.style.borderColor = ''; el.style.boxShadow = ''; }, 2500);
  }
  showTembaToast(msg, 'error');
  return false;
}

function showTembaToast(msg, type = 'error') {
  const t = document.getElementById('temba-toast');
  if (!t) return;
  t.style.background = type === 'success' ? '#2E7D32' : type === 'warning' ? '#E65100' : '#C62828';
  t.textContent = msg;
  t.style.opacity = '1';
  t.style.maxWidth = type === 'warning' ? '380px' : '320px';
  clearTimeout(t._tm);
  t._tm = setTimeout(() => { t.style.opacity = '0'; }, type === 'warning' ? 6000 : 3000);
}
