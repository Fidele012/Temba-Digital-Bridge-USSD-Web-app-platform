"""
Africa's Talking USSD callback - fully bilingual (English / Kinyarwanda).

USSD navigation encoding:
  text = "<lang>*<route>*..."

  parts[0] = language choice  (1=EN, 2=RW)
  parts[1] = auth route       (1=Register, 2=Login, 0=Exit)

── REGISTER FLOW (route == "1") ──────────────────────────────────────────────
  parts[2]    = full name
  parts[3]    = province choice (1-5)
  parts[4]    = district choice (1-N)
  parts[5..x] = sector  (paginated numbered menu; "9" advances page, "0" goes back)
  parts[x..y] = cell    (paginated numbered menu)
  parts[y..z] = village (paginated numbered menu)
  parts[z]    = create 4-digit PIN
  parts[z+1]  = confirm PIN
  → Phone number is captured automatically from the calling number (not typed).
  → Account created with province/district/sector/cell/village all stored.

── LOGIN FLOW (route == "2") ─────────────────────────────────────────────────
  parts[2] = 4-digit USSD PIN
  parts[3] = main menu choice (1-6, 0=Exit)
  parts[4+]= sub-navigation for selected service

  Main menu:
    1. Report water issue
    2. Track my reports
    3. Book appointment
    4. My appointments
    5. Service request status
    6. Submit service request

── PIN SETUP (existing web user, no USSD PIN yet) ───────────────────────────
  Triggered automatically under Login route when ussd_pin_hash is None:
  parts[2] = new 4-digit PIN
  parts[3] = confirm PIN
"""
from __future__ import annotations

import asyncio
import random
import re
import secrets
import string
from datetime import date, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.services.notification_service import notify_org, notify_org_background, notify_user, send_sms_background
from app.models.appointment import (
    Appointment,
    AppointmentReason,
    AppointmentStatus,
    MeetingType,
)
from app.models.provider import Provider, ProviderStatus
from app.models.report import Report, ReportCategory, ReportStatus, ReportUrgency
from app.models.service_request import (
    ServiceRequest,
    ServiceRequestType,
    ServiceRequestUrgency,
)
from app.models.user import User, UserRole

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/ussd", tags=["ussd"])


def _phone_variants(phone: str) -> list[str]:
    """Return all common storage formats of a Rwanda phone number."""
    p = re.sub(r"[\s\-]", "", phone)
    variants: set[str] = {p}
    if p.startswith("+250") and len(p) >= 12:
        variants.update({"0" + p[4:], "250" + p[4:]})
    elif p.startswith("250") and len(p) == 12:
        variants.update({"+" + p, "0" + p[3:]})
    elif p.startswith("0") and len(p) == 10:
        variants.update({"+250" + p[1:], "250" + p[1:]})
    return list(variants)


def _ussd_email_variants(phone: str) -> list[str]:
    """Return every USSD-generated email that could map to this phone number.

    AT sometimes delivers the same physical SIM as +250XXXXXXXXX, 250XXXXXXXXX,
    or 0XXXXXXXXX depending on network / session config.  All three produce a
    different email suffix during registration, so we try every combination at
    login time so any of those accounts is found.
    """
    emails: set[str] = set()
    for v in _phone_variants(phone):
        emails.add(f"{v.lstrip('+')}@ussd.temba.rw")
        if v.startswith("+250"):
            emails.add(f"0{v[4:]}@ussd.temba.rw")
        elif v.startswith("250"):
            emails.add(f"0{v[3:]}@ussd.temba.rw")
    return list(emails)


# ── Rwanda Administrative Hierarchy ──────────────────────────────────────────
# Province list (index 0-4 maps to choice "1"-"5")
_PROVINCES_LIST: list[str] = [
    "Kigali City",
    "Northern Province",
    "Southern Province",
    "Eastern Province",
    "Western Province",
]

# Districts per province (province choice "1"-"5" → district list)
_DISTRICTS: dict[str, list[str]] = {
    "1": ["Gasabo", "Kicukiro", "Nyarugenge"],
    "2": ["Burera", "Gakenke", "Gicumbi", "Musanze", "Rulindo"],
    "3": ["Gisagara", "Huye", "Kamonyi", "Muhanga", "Nyamagabe", "Nyanza", "Nyaruguru", "Ruhango"],
    "4": ["Bugesera", "Gatsibo", "Kayonza", "Kirehe", "Ngoma", "Nyagatare", "Rwamagana"],
    "5": ["Karongi", "Ngororero", "Nyabihu", "Nyamasheke", "Rubavu", "Rutsiro", "Rusizi"],
}

# Sectors per district → cells per sector
# _RW[district][sector] = [cell, ...]
_RW: dict[str, dict[str, list[str]]] = {
    # ── Kigali City ──────────────────────────────────────────────────────────
    "Gasabo": {
        "Bumbogo":    ["Bidudu","Cyarubare","Gasagara","Kagugu","Ntarama","Rubaya"],
        "Gatsata":    ["Bibare","Gisanga","Gitega","Kagugu","Murundo","Ntarama"],
        "Gikomero":   ["Birunga","Burega","Gacurabwenge","Gikomero","Kabuye","Kagina"],
        "Gisozi":     ["Bidudu","Gasagara","Gisozi","Murambi","Rugenge","Rusororo"],
        "Jabana":     ["Bwiza","Gasagara","Jabana","Karuruma","Mburabuturo","Nyagatovu"],
        "Jali":       ["Bukirwa","Gasharu","Jali","Kabuga","Rubungo","Rutonde"],
        "Kacyiru":    ["Kamatamu","Kacyiru","Kamutwa","Kibagabaga","Nyarutarama"],
        "Kimihurura": ["Gikondo","Kagugu","Kimihurura","Rugando"],
        "Kimironko":  ["Bibare","Kanzenze","Kimironko","Mageragere","Rukiri"],
        "Kinyinya":   ["Kabuyange","Kinyinya","Murama","Nyirangarama","Rukuri"],
        "Ndera":      ["Kagugu","Musenyi","Ndera","Rutonde"],
        "Nduba":      ["Busenyi","Kagugu","Nduba","Rurimbi"],
        "Remera":     ["Gisimenti","Nyabisindu","Odesha","Rukiri"],
        "Rusororo":   ["Bumbogo","Gasagara","Karuruma","Ntarama","Rusororo"],
        "Rutunga":    ["Bidudu","Kagina","Murambi","Rutunga"],
    },
    "Kicukiro": {
        "Gahanga":    ["Biryogo","Cyimo","Gahanga","Kibirizi","Ruhuha"],
        "Gatenga":    ["Gatenga","Kabarondo","Kagugu","Kibirizi","Nyabisindu"],
        "Gikondo":    ["Biryogo","Gikondo","Kagugu","Rugunga"],
        "Kagarama":   ["Kagarama","Kibagabaga","Nyanza","Rugunga"],
        "Kanombe":    ["Gikondo","Kanombe","Kibagabaga","Nyarugunga"],
        "Kicukiro":   ["Kicukiro","Niboye","Nyarugunga","Rwezamenyo"],
        "Masaka":     ["Kabuye","Masaka","Nzige","Rugunga"],
        "Niboye":     ["Kibirizi","Niboye","Ruhuha","Rutunga"],
        "Nyarugunga": ["Kadahokwa","Nyarugunga","Rugunga","Rusororo"],
        "Rubilizi":   ["Gikomero","Nyarugenge","Rubilizi","Rusororo"],
    },
    "Nyarugenge": {
        "Gitega":     ["Biryogo","Gitega","Kagugu","Nyarutarama"],
        "Kanyinya":   ["Bidudu","Gikondo","Kanyinya","Murambi"],
        "Kigali":     ["Biryogo","Kigali","Rugenge","Rwezamenyo"],
        "Kimisagara": ["Kimisagara","Muhima","Nyabugogo","Rugenge"],
        "Mageragere": ["Biryogo","Mageragere","Rugunga","Rusororo"],
        "Muhima":     ["Muhima","Nyamirambo","Rugenge","Rwezamenyo"],
        "Nyakabanda": ["Biryogo","Kibirizi","Nyakabanda","Rugunga"],
        "Nyamirambo": ["Biryogo","Gikondo","Nyamirambo","Rugunga"],
        "Nyarugenge": ["Kagugu","Nyarugenge","Rugenge","Rwezamenyo"],
        "Rwezamenyo": ["Biryogo","Kagugu","Rugunga","Rwezamenyo"],
    },
    # ── Northern Province ─────────────────────────────────────────────────────
    "Burera": {
        "Bungwe":      ["Bungwe","Cyeru","Gitovu","Kinoni","Ruhunde"],
        "Butaro":      ["Buhanga","Butaro","Cyabingo","Kinoni","Ruhunde"],
        "Cyanika":     ["Cyanika","Kagogo","Kinoni","Nemba","Ruhunde"],
        "Cyeru":       ["Cyeru","Kagogo","Kinoni","Rugarama","Rusarabuye"],
        "Gahunga":     ["Cyabingo","Gahunga","Kinoni","Nemba","Ruhunde"],
        "Gatebe":      ["Cyabingo","Gatebe","Kinoni","Rugarama","Ruhunde"],
        "Gitovu":      ["Cyabingo","Gitovu","Kinoni","Rugarama","Ruhunde"],
        "Kagogo":      ["Cyabingo","Kagogo","Kinoni","Rugarama","Ruhunde"],
        "Kinoni":      ["Cyabingo","Kinoni","Nemba","Rugarama","Ruhunde"],
        "Kivuye":      ["Cyabingo","Kinoni","Kivuye","Rugarama","Ruhunde"],
        "Nemba":       ["Cyabingo","Kinoni","Nemba","Rugarama","Ruhunde"],
        "Rugarama":    ["Cyabingo","Kinoni","Rugarama","Rugendabari","Ruhunde"],
        "Rugendabari": ["Cyabingo","Kinoni","Rugarama","Rugendabari","Ruhunde"],
        "Ruhunde":     ["Cyabingo","Kinoni","Rugarama","Ruhunde","Rusarabuye"],
        "Rusarabuye":  ["Cyabingo","Kinoni","Rugarama","Rusarabuye","Rwerere"],
        "Rwerere":     ["Cyabingo","Kinoni","Rugarama","Ruhunde","Rwerere"],
    },
    "Gakenke": {
        "Busengo":   ["Busengo","Cyabingo","Muhororo","Nemba","Rushashi"],
        "Coko":      ["Coko","Muhororo","Nemba","Rugarama","Rusasa"],
        "Cyabingo":  ["Cyabingo","Muhororo","Musasa","Nemba","Rushashi"],
        "Gakenke":   ["Cyabingo","Gakenke","Muhororo","Nemba","Rushashi"],
        "Gashenyi":  ["Cyabingo","Gashenyi","Muhororo","Nemba","Rushashi"],
        "Janja":     ["Janja","Muhororo","Nemba","Rugarama","Rusasa"],
        "Kamubuga":  ["Kamubuga","Muhororo","Nemba","Rugarama","Rushashi"],
        "Karambi":   ["Karambi","Muhororo","Nemba","Rugarama","Rushashi"],
        "Kayonga":   ["Kayonga","Muhororo","Nemba","Rugarama","Rushashi"],
        "Minazi":    ["Minazi","Muhororo","Nemba","Rugarama","Rushashi"],
        "Muhondo":   ["Muhondo","Muhororo","Nemba","Rugarama","Rushashi"],
        "Mukarange": ["Muhororo","Mukarange","Nemba","Rugarama","Rushashi"],
        "Musasa":    ["Muhororo","Musasa","Nemba","Rugarama","Rushashi"],
        "Muzo":      ["Muhororo","Muzo","Nemba","Rugarama","Rushashi"],
        "Nemba":     ["Muhororo","Nemba","Rugarama","Ruli","Rushashi"],
        "Ruli":      ["Muhororo","Nemba","Rugarama","Ruli","Rushashi"],
        "Rusasa":    ["Muhororo","Nemba","Rugarama","Rusasa","Rushashi"],
        "Rushashi":  ["Muhororo","Nemba","Rugarama","Ruli","Rushashi"],
    },
    "Gicumbi": {
        "Bukure":      ["Bukure","Byumba","Kamugisha","Mugunga","Nyamugali"],
        "Bwisige":     ["Bwisige","Byumba","Kamugisha","Mugunga","Nyamugali"],
        "Byumba":      ["Byumba","Kamugisha","Mugunga","Nyamugali","Rugengabari"],
        "Cyumba":      ["Byumba","Cyumba","Kamugisha","Mugunga","Nyamugali"],
        "Gicumbi":     ["Byumba","Gicumbi","Kamugisha","Mugunga","Nyamugali"],
        "Gosho":       ["Byumba","Gosho","Kamugisha","Mugunga","Nyamugali"],
        "Kaniga":      ["Byumba","Kamugisha","Kaniga","Mugunga","Nyamugali"],
        "Manyagiro":   ["Byumba","Kamugisha","Manyagiro","Mugunga","Nyamugali"],
        "Miyove":      ["Byumba","Kamugisha","Miyove","Mugunga","Nyamugali"],
        "Mukono":      ["Byumba","Kamugisha","Mugunga","Mukono","Nyamugali"],
        "Mutete":      ["Byumba","Kamugisha","Mugunga","Mutete","Nyamugali"],
        "Nyamiyaga":   ["Byumba","Kamugisha","Mugunga","Nyamiyaga","Nyamugali"],
        "Nyankenke":   ["Byumba","Kamugisha","Mugunga","Nyankenke","Nyamugali"],
        "Rubaya":      ["Byumba","Kamugisha","Mugunga","Nyamugali","Rubaya"],
        "Rugabano":    ["Byumba","Kamugisha","Mugunga","Nyamugali","Rugabano"],
        "Rugali":      ["Byumba","Kamugisha","Mugunga","Nyamugali","Rugali"],
        "Ruhondo":     ["Byumba","Kamugisha","Mugunga","Nyamugali","Ruhondo"],
        "Rusiga":      ["Byumba","Kamugisha","Mugunga","Nyamugali","Rusiga"],
        "Tanda":       ["Byumba","Kamugisha","Mugunga","Nyamugali","Tanda"],
        "Wimana":      ["Byumba","Kamugisha","Mugunga","Nyamugali","Wimana"],
    },
    "Musanze": {
        "Busogo":    ["Busogo","Cyabashuri","Mubuga","Nkanka","Rususa"],
        "Cyuve":     ["Cyuve","Kiyumba","Nkotsi","Rwaza","Sarangi"],
        "Gacaca":    ["Bitare","Gacaca","Karwasa","Nyagisozi","Remera"],
        "Gashaki":   ["Gashaki","Kagano","Karwasa","Nyundo","Rwaza"],
        "Gataraga":  ["Gataraga","Kagano","Murambi","Nyundo","Shingiro"],
        "Kimonyi":   ["Biruyi","Kimonyi","Nyundo","Ruganda","Ryabega"],
        "Kinigi":    ["Bisizi","Cyanzarwe","Kinigi","Nyabigoma","Nyamyumba"],
        "Muhoza":    ["Busogo","Muganwa","Muhoza","Nyundo","Rutonde"],
        "Muko":      ["Busenyi","Kageyo","Mukarange","Muko","Nyabirasi"],
        "Musanze":   ["Mpenge","Musanze","Nyabugogo","Rugarama","Ruhondo"],
        "Nkotsi":    ["Kabuye","Murambi","Nkotsi","Nyundo","Rutonde"],
        "Nyange":    ["Kagano","Murambi","Nyange","Nyundo","Rutonde"],
        "Remera":    ["Kagano","Murambi","Nyundo","Remera","Rutonde"],
        "Rwaza":     ["Cyabingo","Kagano","Nyundo","Remera","Rwaza"],
        "Shingiro":  ["Kagano","Murambi","Nyundo","Remera","Shingiro"],
    },
    "Rulindo": {
        "Base":        ["Base","Cyahinda","Kabara","Murambi","Ntarabana"],
        "Burega":      ["Burega","Cyahinda","Kabara","Murambi","Ntarabana"],
        "Bushoki":     ["Bushoki","Cyahinda","Kabara","Murambi","Ntarabana"],
        "Buyoga":      ["Buyoga","Cyahinda","Kabara","Murambi","Ntarabana"],
        "Cyinzuzi":    ["Cyahinda","Cyinzuzi","Kabara","Murambi","Ntarabana"],
        "Cyungo":      ["Cyahinda","Cyungo","Kabara","Murambi","Ntarabana"],
        "Kinihira":    ["Cyahinda","Kabara","Kinihira","Murambi","Ntarabana"],
        "Kisaro":      ["Cyahinda","Kabara","Kisaro","Murambi","Ntarabana"],
        "Masoro":      ["Cyahinda","Kabara","Masoro","Murambi","Ntarabana"],
        "Mbogo":       ["Cyahinda","Kabara","Mbogo","Murambi","Ntarabana"],
        "Murambi":     ["Cyahinda","Kabara","Murambi","Ntarabana","Shyorongi"],
        "Ngoma":       ["Cyahinda","Kabara","Murambi","Ngoma","Ntarabana"],
        "Ntarabana":   ["Cyahinda","Kabara","Murambi","Ntarabana","Rukomangwa"],
        "Rukomangwa":  ["Cyahinda","Kabara","Murambi","Ntarabana","Rukomangwa"],
        "Rusiga":      ["Cyahinda","Kabara","Murambi","Ntarabana","Rusiga"],
        "Shyorongi":   ["Cyahinda","Kabara","Murambi","Ntarabana","Shyorongi"],
        "Tumba":       ["Cyahinda","Kabara","Murambi","Ntarabana","Tumba"],
    },
    # ── Southern Province ─────────────────────────────────────────────────────
    "Gisagara": {
        "Gikonko":  ["Gikonko","Karama","Mugobagoba","Musasa","Rwabicuma"],
        "Gishubi":  ["Gishubi","Karama","Mugobagoba","Musasa","Rwabicuma"],
        "Kansi":    ["Kansi","Karama","Mugobagoba","Musasa","Rwabicuma"],
        "Kibirizi": ["Karama","Kibirizi","Mugobagoba","Musasa","Rwabicuma"],
        "Kigembe":  ["Karama","Kigembe","Mugobagoba","Musasa","Rwabicuma"],
        "Mamba":    ["Karama","Mamba","Mugobagoba","Musasa","Rwabicuma"],
        "Muganza":  ["Karama","Muganza","Mugobagoba","Musasa","Rwabicuma"],
        "Mugombwa": ["Karama","Mugobagoba","Mugombwa","Musasa","Rwabicuma"],
        "Mukindo":  ["Karama","Mugobagoba","Mukindo","Musasa","Rwabicuma"],
        "Musha":    ["Karama","Mugobagoba","Musha","Musasa","Rwabicuma"],
        "Ndora":    ["Karama","Mugobagoba","Musasa","Ndora","Rwabicuma"],
        "Nyanza":   ["Karama","Mugobagoba","Musasa","Nyanza","Rwabicuma"],
        "Save":     ["Karama","Mugobagoba","Musasa","Rwabicuma","Save"],
    },
    "Huye": {
        "Gishamvu": ["Gishamvu","Karama","Maraba","Mbazi","Rusaka"],
        "Huye":     ["Huye","Karama","Maraba","Mbazi","Rusaka"],
        "Karama":   ["Gishamvu","Karama","Maraba","Mbazi","Rusaka"],
        "Kigoma":   ["Gishamvu","Karama","Kigoma","Mbazi","Rusaka"],
        "Kinazi":   ["Gishamvu","Karama","Kinazi","Mbazi","Rusaka"],
        "Maraba":   ["Gishamvu","Karama","Maraba","Mbazi","Rusaka"],
        "Mbazi":    ["Gishamvu","Karama","Maraba","Mbazi","Rusaka"],
        "Mukura":   ["Gishamvu","Karama","Maraba","Mukura","Rusaka"],
        "Ngoma":    ["Gishamvu","Karama","Maraba","Ngoma","Rusaka"],
        "Ruhashya": ["Gishamvu","Karama","Maraba","Ruhashya","Rusaka"],
        "Rusatira": ["Gishamvu","Karama","Maraba","Rusaka","Rusatira"],
        "Rwaniro":  ["Gishamvu","Karama","Maraba","Rusaka","Rwaniro"],
        "Simbi":    ["Gishamvu","Karama","Maraba","Rusaka","Simbi"],
        "Tumba":    ["Gishamvu","Karama","Maraba","Rusaka","Tumba"],
    },
    "Kamonyi": {
        "Gacurabwenge": ["Gacurabwenge","Kabagari","Kayenzi","Muhororo","Runda"],
        "Karama":       ["Kabagari","Karama","Kayenzi","Muhororo","Runda"],
        "Kayenzi":      ["Kabagari","Kayenzi","Muhororo","Ngamba","Runda"],
        "Kayumbu":      ["Kabagari","Kayumbu","Muhororo","Ngamba","Runda"],
        "Mugina":       ["Kabagari","Muhororo","Mugina","Ngamba","Runda"],
        "Musambira":    ["Kabagari","Muhororo","Musambira","Ngamba","Runda"],
        "Ngamba":       ["Kabagari","Muhororo","Ngamba","Nyamiyaga","Runda"],
        "Nyamiyaga":    ["Kabagari","Muhororo","Ngamba","Nyamiyaga","Runda"],
        "Nyarubaka":    ["Kabagari","Muhororo","Ngamba","Nyarubaka","Runda"],
        "Rugalika":     ["Kabagari","Muhororo","Ngamba","Runda","Rugalika"],
        "Rugarika":     ["Kabagari","Muhororo","Ngamba","Runda","Rugarika"],
        "Rukoma":       ["Kabagari","Muhororo","Ngamba","Runda","Rukoma"],
        "Runda":        ["Kabagari","Muhororo","Ngamba","Nyamiyaga","Runda"],
    },
    "Muhanga": {
        "Cyeza":       ["Cyeza","Kabacuzi","Kiyumba","Mushishiro","Nyamabuye"],
        "Kabacuzi":    ["Cyeza","Kabacuzi","Kiyumba","Mushishiro","Nyamabuye"],
        "Kibangu":     ["Cyeza","Kibangu","Kiyumba","Mushishiro","Nyamabuye"],
        "Kiyumba":     ["Cyeza","Kiyumba","Mushishiro","Nyamabuye","Nyamariza"],
        "Muhanga":     ["Cyeza","Kiyumba","Muhanga","Mushishiro","Nyamabuye"],
        "Mushishiro":  ["Cyeza","Kiyumba","Muhanga","Mushishiro","Nyamabuye"],
        "Nyabinoni":   ["Cyeza","Kiyumba","Muhanga","Nyabinoni","Nyamabuye"],
        "Nyamabuye":   ["Cyeza","Kiyumba","Muhanga","Nyamabuye","Nyamariza"],
        "Nyamariza":   ["Cyeza","Kiyumba","Muhanga","Nyamabuye","Nyamariza"],
        "Rongi":       ["Cyeza","Kiyumba","Muhanga","Nyamabuye","Rongi"],
        "Rugendabari": ["Cyeza","Kiyumba","Muhanga","Nyamabuye","Rugendabari"],
    },
    "Nyamagabe": {
        "Buruhukiro": ["Buruhukiro","Cyanika","Gasaka","Kaduha","Musenyi"],
        "Cyanika":    ["Cyanika","Gasaka","Kaduha","Musenyi","Tare"],
        "Gasaka":     ["Cyanika","Gasaka","Kaduha","Musenyi","Tare"],
        "Gatare":     ["Cyanika","Gasaka","Gatare","Musenyi","Tare"],
        "Kaduha":     ["Cyanika","Gasaka","Kaduha","Musenyi","Tare"],
        "Kamegeri":   ["Cyanika","Gasaka","Kamegeri","Musenyi","Tare"],
        "Kibirizi":   ["Cyanika","Gasaka","Kibirizi","Musenyi","Tare"],
        "Kibumbwe":   ["Cyanika","Gasaka","Kibumbwe","Musenyi","Tare"],
        "Kitabi":     ["Cyanika","Gasaka","Kitabi","Musenyi","Tare"],
        "Mbazi":      ["Cyanika","Gasaka","Mbazi","Musenyi","Tare"],
        "Mugano":     ["Cyanika","Gasaka","Mugano","Musenyi","Tare"],
        "Musange":    ["Cyanika","Gasaka","Musenyi","Musange","Tare"],
        "Musebeya":   ["Cyanika","Gasaka","Musenyi","Musebeya","Tare"],
        "Musubi":     ["Cyanika","Gasaka","Musenyi","Musubi","Tare"],
        "Nkomane":    ["Cyanika","Gasaka","Musenyi","Nkomane","Tare"],
        "Tare":       ["Cyanika","Gasaka","Musenyi","Tare","Uwinkingi"],
        "Uwinkingi":  ["Cyanika","Gasaka","Musenyi","Tare","Uwinkingi"],
    },
    "Nyanza": {
        "Busasamana": ["Busasamana","Cyabakamyi","Kibirizi","Mukingo","Rwabicuma"],
        "Cyabakamyi": ["Busasamana","Cyabakamyi","Kibirizi","Mukingo","Rwabicuma"],
        "Kibirizi":   ["Busasamana","Kibirizi","Kigoma","Mukingo","Rwabicuma"],
        "Kigoma":     ["Busasamana","Kibirizi","Kigoma","Mukingo","Rwabicuma"],
        "Mukingo":    ["Busasamana","Kibirizi","Kigoma","Mukingo","Rwabicuma"],
        "Muyira":     ["Busasamana","Kibirizi","Kigoma","Muyira","Rwabicuma"],
        "Ntyazo":     ["Busasamana","Kibirizi","Kigoma","Ntyazo","Rwabicuma"],
        "Nyagisozi":  ["Busasamana","Kibirizi","Kigoma","Nyagisozi","Rwabicuma"],
        "Rwabicuma":  ["Busasamana","Kibirizi","Kigoma","Mukingo","Rwabicuma"],
    },
    "Nyaruguru": {
        "Busanze":   ["Busanze","Cyahinda","Kibago","Munini","Ruramba"],
        "Cyahinda":  ["Cyahinda","Kibago","Munini","Ruramba","Rusenge"],
        "Kibeho":    ["Cyahinda","Kibeho","Munini","Ruramba","Rusenge"],
        "Kivu":      ["Cyahinda","Kivu","Munini","Ruramba","Rusenge"],
        "Mata":      ["Cyahinda","Kibago","Mata","Munini","Ruramba"],
        "Muganza":   ["Cyahinda","Kibago","Muganza","Munini","Ruramba"],
        "Munini":    ["Cyahinda","Kibago","Munini","Ruramba","Rusenge"],
        "Ngera":     ["Cyahinda","Kibago","Munini","Ngera","Ruramba"],
        "Ngoma":     ["Cyahinda","Kibago","Munini","Ngoma","Ruramba"],
        "Nyabimata": ["Cyahinda","Kibago","Munini","Nyabimata","Ruramba"],
        "Nyagisozi": ["Cyahinda","Kibago","Munini","Nyagisozi","Ruramba"],
        "Ruheru":    ["Cyahinda","Kibago","Munini","Ruheru","Ruramba"],
        "Ruramba":   ["Cyahinda","Kibago","Munini","Ruramba","Rusenge"],
        "Rusenge":   ["Cyahinda","Kibago","Munini","Ruramba","Rusenge"],
    },
    "Ruhango": {
        "Bweramana": ["Bweramana","Kabagali","Kinazi","Mbuye","Ntongwe"],
        "Byimana":   ["Byimana","Kabagali","Kinazi","Mbuye","Ntongwe"],
        "Kabagali":  ["Kabagali","Kinazi","Mbuye","Mwendo","Ntongwe"],
        "Kinazi":    ["Kabagali","Kinazi","Mbuye","Mwendo","Ntongwe"],
        "Kinihira":  ["Kabagali","Kinihira","Mbuye","Mwendo","Ntongwe"],
        "Mbuye":     ["Kabagali","Kinazi","Mbuye","Mwendo","Ntongwe"],
        "Mwendo":    ["Kabagali","Kinazi","Mbuye","Mwendo","Ntongwe"],
        "Ntongwe":   ["Kabagali","Kinazi","Mbuye","Mwendo","Ntongwe"],
        "Ruhango":   ["Kabagali","Kinazi","Mbuye","Mwendo","Ruhango"],
    },
    # ── Eastern Province ──────────────────────────────────────────────────────
    "Bugesera": {
        "Gashora":    ["Biharwe","Gashora","Mwogo","Nyarugenge","Rweru"],
        "Juru":       ["Biharwe","Juru","Kagina","Nyarugenge","Rweru"],
        "Kamabuye":   ["Biharwe","Kamabuye","Kagina","Nyarugenge","Rweru"],
        "Ntarama":    ["Biharwe","Kagina","Ntarama","Nyarugenge","Rweru"],
        "Mareba":     ["Biharwe","Kagina","Mareba","Nyarugenge","Rweru"],
        "Mayange":    ["Biharwe","Kagina","Mayange","Nyarugenge","Rweru"],
        "Musenyi":    ["Biharwe","Kagina","Musenyi","Nyarugenge","Rweru"],
        "Mwogo":      ["Biharwe","Kagina","Mwogo","Nyarugenge","Rweru"],
        "Ngeruka":    ["Biharwe","Kagina","Ngeruka","Nyarugenge","Rweru"],
        "Nyamata":    ["Biharwe","Kagina","Nyamata","Nyarugenge","Rweru"],
        "Nyarugenge": ["Biharwe","Kagina","Nyarugenge","Ruhuha","Rweru"],
        "Rilima":     ["Biharwe","Kagina","Nyarugenge","Rilima","Rweru"],
        "Ruhuha":     ["Biharwe","Kagina","Nyarugenge","Ruhuha","Rweru"],
        "Rweru":      ["Biharwe","Kagina","Nyarugenge","Ruhuha","Rweru"],
        "Shyara":     ["Biharwe","Kagina","Nyarugenge","Ruhuha","Shyara"],
    },
    "Gatsibo": {
        "Gasange":    ["Gasange","Gashike","Murama","Ngarama","Nzige"],
        "Gatsibo":    ["Gatsibo","Murama","Ngarama","Nzige","Remera"],
        "Gitoki":     ["Gitoki","Murama","Ngarama","Nzige","Remera"],
        "Kabarore":   ["Kabarore","Murama","Ngarama","Nzige","Remera"],
        "Kageyo":     ["Kageyo","Murama","Ngarama","Nzige","Remera"],
        "Kiramuruzi": ["Kiramuruzi","Murama","Ngarama","Nzige","Remera"],
        "Kiziguro":   ["Kiziguro","Murama","Ngarama","Nzige","Remera"],
        "Muhura":     ["Murama","Muhura","Ngarama","Nzige","Remera"],
        "Murambi":    ["Murama","Murambi","Ngarama","Nzige","Remera"],
        "Ngarama":    ["Murama","Ngarama","Nzige","Remera","Rugarama"],
        "Nyagihanga": ["Murama","Ngarama","Nzige","Nyagihanga","Remera"],
        "Remera":     ["Murama","Ngarama","Nzige","Remera","Rugarama"],
        "Rugarama":   ["Murama","Ngarama","Nzige","Remera","Rugarama"],
        "Rwimbogo":   ["Murama","Ngarama","Nzige","Remera","Rwimbogo"],
    },
    "Kayonza": {
        "Gahini":     ["Gahini","Gisagara","Murama","Nyarusange","Rundu"],
        "Kabarondo":  ["Gisagara","Kabarondo","Murama","Nyarusange","Rundu"],
        "Mukarange":  ["Gisagara","Mukarange","Murama","Nyarusange","Rundu"],
        "Murama":     ["Gisagara","Murama","Nyarusange","Rundu","Rwinkwavu"],
        "Murundi":    ["Gisagara","Murama","Murundi","Nyarusange","Rundu"],
        "Mwiri":      ["Gisagara","Murama","Mwiri","Nyarusange","Rundu"],
        "Ndego":      ["Gisagara","Murama","Ndego","Nyarusange","Rundu"],
        "Nyamirama":  ["Gisagara","Murama","Nyamirama","Nyarusange","Rundu"],
        "Rukara":     ["Gisagara","Murama","Nyarusange","Rukara","Rundu"],
        "Ruramira":   ["Gisagara","Murama","Nyarusange","Rundu","Ruramira"],
        "Rwinkwavu":  ["Gisagara","Murama","Nyarusange","Rundu","Rwinkwavu"],
    },
    "Kirehe": {
        "Gahara":    ["Gahara","Gashike","Kirehe","Murama","Nyagisozi"],
        "Gatore":    ["Gashike","Gatore","Kirehe","Murama","Nyagisozi"],
        "Kigarama":  ["Gashike","Kigarama","Kirehe","Murama","Nyagisozi"],
        "Kigina":    ["Gashike","Kigina","Kirehe","Murama","Nyagisozi"],
        "Kirehe":    ["Gashike","Kirehe","Murama","Nyagisozi","Nyarubuye"],
        "Mahama":    ["Gashike","Kirehe","Mahama","Murama","Nyagisozi"],
        "Mpanga":    ["Gashike","Kirehe","Mpanga","Murama","Nyagisozi"],
        "Musaza":    ["Gashike","Kirehe","Murama","Musaza","Nyagisozi"],
        "Mushikiri": ["Gashike","Kirehe","Murama","Mushikiri","Nyagisozi"],
        "Nasho":     ["Gashike","Kirehe","Murama","Nasho","Nyagisozi"],
        "Nyamugari": ["Gashike","Kirehe","Murama","Nyagisozi","Nyamugari"],
        "Nyarubuye": ["Gashike","Kirehe","Murama","Nyagisozi","Nyarubuye"],
    },
    "Ngoma": {
        "Gashanda":  ["Gashanda","Jarama","Kibungo","Murama","Zaza"],
        "Jarama":    ["Gashanda","Jarama","Kibungo","Murama","Zaza"],
        "Karembo":   ["Gashanda","Karembo","Kibungo","Murama","Zaza"],
        "Kazo":      ["Gashanda","Kazo","Kibungo","Murama","Zaza"],
        "Kibungo":   ["Gashanda","Jarama","Kibungo","Murama","Zaza"],
        "Mugesera":  ["Gashanda","Jarama","Kibungo","Mugesera","Zaza"],
        "Murama":    ["Gashanda","Jarama","Kibungo","Murama","Zaza"],
        "Mutenderi": ["Gashanda","Kibungo","Murama","Mutenderi","Zaza"],
        "Remera":    ["Gashanda","Kibungo","Murama","Remera","Zaza"],
        "Rukira":    ["Gashanda","Kibungo","Murama","Rukira","Zaza"],
        "Rukumberi": ["Gashanda","Kibungo","Murama","Rukumberi","Zaza"],
        "Rurenge":   ["Gashanda","Kibungo","Murama","Rurenge","Zaza"],
        "Sake":      ["Gashanda","Kibungo","Murama","Sake","Zaza"],
        "Zaza":      ["Gashanda","Kibungo","Murama","Rurenge","Zaza"],
    },
    "Nyagatare": {
        "Gatunda":    ["Cyavuro","Gatunda","Kidaho","Mugogo","Nyabisiga"],
        "Karama":     ["Cyabayaga","Kagitumba","Karama","Musasa","Nyagafunzo"],
        "Karangazi":  ["Bukinanyana","Gikundamvura","Kinyababa","Mbare","Nyabwishongwezi"],
        "Katabagemu": ["Cyabagomba","Gatuza","Katabagemu","Nyagatare","Rwahi"],
        "Kiyombe":    ["Cyabagomba","Gahengeri","Kabeza","Kiyombe","Nyagafunzo"],
        "Matimba":    ["Bishenyi","Gahengeri","Matimba","Ngarama","Nyagafunzo"],
        "Mimuli":     ["Gahengeri","Kabare","Mimuli","Mukarange","Rugarama"],
        "Mukama":     ["Cyabagomba","Gahengeri","Mukama","Mukarange","Nyagafunzo"],
        "Musheli":    ["Cyabagomba","Kabare","Mukarange","Musheli","Nyagafunzo"],
        "Nyagatare":  ["Cyabagomba","Gahengeri","Kabare","Mukarange","Nyagatare"],
        "Rukomo":     ["Cyabagomba","Gahengeri","Mukarange","Nyagafunzo","Rukomo"],
        "Rwempasha":  ["Cyabagomba","Gahengeri","Mukarange","Nyagafunzo","Rwempasha"],
        "Rwimiyaga":  ["Cyabagomba","Gahengeri","Mukarange","Nyagafunzo","Rwimiyaga"],
        "Tabagwe":    ["Cyabagomba","Gahengeri","Kabare","Mukarange","Tabagwe"],
    },
    "Rwamagana": {
        "Fumbwe":     ["Fumbwe","Karenge","Murama","Nzige","Rubona"],
        "Gahengeri":  ["Gahengeri","Karenge","Murama","Nzige","Rubona"],
        "Gishali":    ["Gishali","Karenge","Murama","Nzige","Rubona"],
        "Karenge":    ["Fumbwe","Karenge","Murama","Nzige","Rubona"],
        "Kigabiro":   ["Fumbwe","Karenge","Kigabiro","Murama","Rubona"],
        "Muhazi":     ["Fumbwe","Karenge","Muhazi","Murama","Rubona"],
        "Munyaga":    ["Fumbwe","Karenge","Munyaga","Murama","Rubona"],
        "Munyiginya": ["Fumbwe","Karenge","Munyiginya","Murama","Rubona"],
        "Musha":      ["Fumbwe","Karenge","Murama","Musha","Rubona"],
        "Muyumbu":    ["Fumbwe","Karenge","Murama","Muyumbu","Rubona"],
        "Mwulire":    ["Fumbwe","Karenge","Murama","Mwulire","Rubona"],
        "Nyakariro":  ["Fumbwe","Karenge","Murama","Nyakariro","Rubona"],
        "Nzige":      ["Fumbwe","Karenge","Murama","Nzige","Rubona"],
        "Rubona":     ["Fumbwe","Karenge","Murama","Nzige","Rubona"],
    },
    # ── Western Province ──────────────────────────────────────────────────────
    "Karongi": {
        "Bwishyura": ["Bwishyura","Gitesi","Mubuga","Rugabano","Twumba"],
        "Gashari":   ["Gashari","Gitesi","Mubuga","Rugabano","Twumba"],
        "Gishyita":  ["Gitesi","Gishyita","Mubuga","Rugabano","Twumba"],
        "Gitesi":    ["Gitesi","Mubuga","Murambi","Rugabano","Twumba"],
        "Mubuga":    ["Gitesi","Mubuga","Murambi","Rugabano","Twumba"],
        "Murambi":   ["Gitesi","Mubuga","Murambi","Rugabano","Twumba"],
        "Murundi":   ["Gitesi","Mubuga","Murundi","Rugabano","Twumba"],
        "Mutuntu":   ["Gitesi","Mubuga","Mutuntu","Rugabano","Twumba"],
        "Rugabano":  ["Gitesi","Mubuga","Murambi","Rugabano","Twumba"],
        "Ruganda":   ["Gitesi","Mubuga","Rugabano","Ruganda","Twumba"],
        "Rwankuba":  ["Gitesi","Mubuga","Rugabano","Rwankuba","Twumba"],
        "Twumba":    ["Gitesi","Mubuga","Rugabano","Twumba","Rwankuba"],
    },
    "Ngororero": {
        "Bwira":     ["Bwira","Hindiro","Kabaya","Kavumu","Muhororo"],
        "Gatumba":   ["Bwira","Gatumba","Kabaya","Kavumu","Muhororo"],
        "Hindiro":   ["Bwira","Hindiro","Kabaya","Kavumu","Muhororo"],
        "Kabaya":    ["Bwira","Hindiro","Kabaya","Kavumu","Muhororo"],
        "Kageyo":    ["Bwira","Hindiro","Kabaya","Kageyo","Muhororo"],
        "Kavumu":    ["Bwira","Hindiro","Kabaya","Kavumu","Muhororo"],
        "Matyazo":   ["Bwira","Hindiro","Kabaya","Matyazo","Muhororo"],
        "Muhanda":   ["Bwira","Hindiro","Kabaya","Muhanda","Muhororo"],
        "Muhororo":  ["Bwira","Hindiro","Kabaya","Kavumu","Muhororo"],
        "Ndaro":     ["Bwira","Hindiro","Kabaya","Muhororo","Ndaro"],
        "Ngororero": ["Bwira","Hindiro","Kabaya","Muhororo","Ngororero"],
        "Nyange":    ["Bwira","Hindiro","Kabaya","Muhororo","Nyange"],
        "Sovu":      ["Bwira","Hindiro","Kabaya","Muhororo","Sovu"],
    },
    "Nyabihu": {
        "Bigogwe":  ["Bigogwe","Karago","Mukamira","Muringa","Rambura"],
        "Jomba":    ["Bigogwe","Jomba","Karago","Muringa","Rambura"],
        "Kabatwa":  ["Bigogwe","Kabatwa","Karago","Muringa","Rambura"],
        "Karago":   ["Bigogwe","Jomba","Karago","Muringa","Rambura"],
        "Kintobo":  ["Bigogwe","Jomba","Kintobo","Muringa","Rambura"],
        "Mukamira": ["Bigogwe","Jomba","Karago","Mukamira","Rambura"],
        "Muringa":  ["Bigogwe","Jomba","Karago","Muringa","Rambura"],
        "Rambura":  ["Bigogwe","Jomba","Karago","Muringa","Rambura"],
        "Rugera":   ["Bigogwe","Jomba","Karago","Muringa","Rugera"],
        "Rurembo":  ["Bigogwe","Jomba","Karago","Muringa","Rurembo"],
        "Shyira":   ["Bigogwe","Jomba","Karago","Muringa","Shyira"],
    },
    "Nyamasheke": {
        "Bushekeri":    ["Bushekeri","Cyato","Kagano","Kanjongo","Shangi"],
        "Bushenge":     ["Bushenge","Cyato","Kagano","Kanjongo","Shangi"],
        "Cyato":        ["Bushekeri","Cyato","Kagano","Kanjongo","Shangi"],
        "Gihombo":      ["Cyato","Gihombo","Kagano","Kanjongo","Shangi"],
        "Kagano":       ["Cyato","Gihombo","Kagano","Kanjongo","Shangi"],
        "Kanjongo":     ["Cyato","Kagano","Kanjongo","Kirimbi","Shangi"],
        "Karambi":      ["Cyato","Kagano","Karambi","Kanjongo","Shangi"],
        "Karengera":    ["Cyato","Kagano","Kanjongo","Karengera","Shangi"],
        "Kirimbi":      ["Cyato","Kagano","Kanjongo","Kirimbi","Shangi"],
        "Macuba":       ["Cyato","Kagano","Kanjongo","Macuba","Shangi"],
        "Mahembe":      ["Cyato","Kagano","Kanjongo","Mahembe","Shangi"],
        "Nyabitekeri":  ["Cyato","Kagano","Kanjongo","Nyabitekeri","Shangi"],
        "Rangiro":      ["Cyato","Kagano","Kanjongo","Rangiro","Shangi"],
        "Ruharambuga":  ["Cyato","Kagano","Kanjongo","Ruharambuga","Shangi"],
        "Shangi":       ["Cyato","Kagano","Kanjongo","Ruharambuga","Shangi"],
    },
    "Rubavu": {
        "Bugeshi":    ["Bugeshi","Cyanzarwe","Kanama","Nyakiliba","Rugerero"],
        "Busasamana": ["Bugeshi","Cyanzarwe","Kanama","Nyakiliba","Rugerero"],
        "Cyanzarwe":  ["Bugeshi","Cyanzarwe","Kanama","Nyakiliba","Rugerero"],
        "Gisenyi":    ["Bugeshi","Cyanzarwe","Gisenyi","Kanama","Rugerero"],
        "Kanama":     ["Bugeshi","Cyanzarwe","Gisenyi","Kanama","Rugerero"],
        "Kanzenze":   ["Bugeshi","Cyanzarwe","Kanama","Kanzenze","Rugerero"],
        "Mudende":    ["Bugeshi","Cyanzarwe","Kanama","Mudende","Rugerero"],
        "Nyakiliba":  ["Bugeshi","Cyanzarwe","Kanama","Nyakiliba","Rugerero"],
        "Nyamyumba":  ["Bugeshi","Cyanzarwe","Kanama","Nyamyumba","Rugerero"],
        "Nyundo":     ["Bugeshi","Cyanzarwe","Kanama","Nyundo","Rugerero"],
        "Rugerero":   ["Bugeshi","Cyanzarwe","Gisenyi","Kanama","Rugerero"],
    },
    "Rusizi": {
        "Bugarama":      ["Bugarama","Giheke","Kamembe","Mururu","Nyakabuye"],
        "Bweyeye":       ["Bweyeye","Giheke","Kamembe","Mururu","Nyakabuye"],
        "Giheke":        ["Bugarama","Giheke","Kamembe","Mururu","Nyakabuye"],
        "Gihundwe":      ["Bugarama","Giheke","Gihundwe","Kamembe","Nyakabuye"],
        "Gikundamvura":  ["Bugarama","Giheke","Gikundamvura","Kamembe","Nyakabuye"],
        "Gitambi":       ["Bugarama","Giheke","Gitambi","Kamembe","Nyakabuye"],
        "Kamembe":       ["Bugarama","Giheke","Kamembe","Mururu","Nyakabuye"],
        "Muganza":       ["Bugarama","Giheke","Kamembe","Muganza","Nyakabuye"],
        "Mururu":        ["Bugarama","Giheke","Kamembe","Mururu","Nyakabuye"],
        "Nkungu":        ["Bugarama","Giheke","Kamembe","Nkungu","Nyakabuye"],
        "Nyakabuye":     ["Bugarama","Giheke","Kamembe","Mururu","Nyakabuye"],
        "Nyandungu":     ["Bugarama","Giheke","Kamembe","Nyandungu","Nyakabuye"],
        "Nzahaha":       ["Bugarama","Giheke","Kamembe","Nyakabuye","Nzahaha"],
        "Nzovwe":        ["Bugarama","Giheke","Kamembe","Nyakabuye","Nzovwe"],
        "Rwimbogo":      ["Bugarama","Giheke","Kamembe","Nyakabuye","Rwimbogo"],
    },
    "Rutsiro": {
        "Boneza":    ["Boneza","Gihango","Kigeyo","Musasa","Mushubati"],
        "Gihango":   ["Boneza","Gihango","Kigeyo","Musasa","Mushubati"],
        "Kigeyo":    ["Boneza","Gihango","Kigeyo","Musasa","Mushubati"],
        "Kivumu":    ["Boneza","Gihango","Kivumu","Musasa","Mushubati"],
        "Manihira":  ["Boneza","Gihango","Manihira","Musasa","Mushubati"],
        "Mukura":    ["Boneza","Gihango","Kigeyo","Mukura","Musasa"],
        "Murunda":   ["Boneza","Gihango","Kigeyo","Murunda","Musasa"],
        "Musasa":    ["Boneza","Gihango","Kigeyo","Musasa","Mushubati"],
        "Mushonyi":  ["Boneza","Gihango","Kigeyo","Mushonyi","Musasa"],
        "Mushubati": ["Boneza","Gihango","Kigeyo","Musasa","Mushubati"],
        "Nyabirasi": ["Boneza","Gihango","Kigeyo","Musasa","Nyabirasi"],
        "Ruhango":   ["Boneza","Gihango","Kigeyo","Musasa","Ruhango"],
        "Rusebeya":  ["Boneza","Gihango","Kigeyo","Musasa","Rusebeya"],
    },
}

# Convenience: sectors listed per district (derived from _RW)
def _sectors_for(district: str) -> list[str]:
    return list(_RW.get(district, {}).keys())

def _cells_for(district: str, sector: str) -> list[str]:
    return _RW.get(district, {}).get(sector, [])

# Villages per cell — explicit for Kigali City; all others get synthetic fallback
_VIL: dict[str, dict[str, dict[str, list[str]]]] = {
    "Gasabo": {
        "Bumbogo":    {"Bidudu":    ["Bidudu","Kiramuruzi","Murambi","Nyabugogo","Taba"],
                       "Cyarubare": ["Bwampanga","Cyarubare","Gasaka","Kabuga","Rwintare"],
                       "Gasagara":  ["Gakenke","Gasagara","Gitega","Kamonyi","Mugina"],
                       "Kagugu":    ["Butare","Bwira","Kagugu","Karama","Mugina"],
                       "Ntarama":   ["Bugesera","Gitaraga","Kagugu","Ntarama","Ruhuha"],
                       "Rubaya":    ["Cyabakamyi","Kaguru","Nyamata","Rubaya","Ruhuha"]},
        "Gatsata":    {"Bibare":    ["Bibare","Gakwege","Kibungo","Rubirizi","Rugendabari"],
                       "Gisanga":   ["Gasare","Gisanga","Kagugu","Munini","Nyagatovu"],
                       "Gitega":    ["Gitega","Kabuye","Murambi","Nyundo","Rebero"],
                       "Kagugu":    ["Byimana","Gikondo","Kagugu","Rugarama","Rutonde"],
                       "Murundo":   ["Gasagara","Mugunga","Murundo","Nyakabanda","Rugina"],
                       "Ntarama":   ["Bugesera","Karama","Kibungo","Ntarama","Rwintare"]},
        "Gikomero":   {"Birunga":   ["Birunga","Kabeza","Kabuye","Murambi","Nyagahama"],
                       "Burega":    ["Burega","Gashike","Kabuye","Murambi","Rwintare"],
                       "Gacurabwenge": ["Gacurabwenge","Kagugu","Mugina","Murambi","Rutonde"],
                       "Gikomero":  ["Gikomero","Kagugu","Murambi","Nyagahama","Rubaya"],
                       "Kabuye":    ["Bugesera","Kabuye","Murambi","Nyundo","Ruhuha"],
                       "Kagina":    ["Byimana","Kagina","Karama","Rugarama","Rutonde"]},
        "Gisozi":     {"Bidudu":    ["Bidudu","Gako","Murama","Nyagahama","Taba"],
                       "Gasagara":  ["Gasagara","Gitega","Kagugu","Mugina","Rusororo"],
                       "Gisozi":    ["Bugesera","Gisozi","Kabeza","Murambi","Rutonde"],
                       "Murambi":   ["Bwira","Murambi","Nyabugogo","Rebero","Rubirizi"],
                       "Rugenge":   ["Kagugu","Karama","Rugenge","Rugarama","Rwintare"],
                       "Rusororo":  ["Birunga","Kabuye","Mugina","Rusororo","Taba"]},
        "Jabana":     {"Bwiza":     ["Bwiza","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gasagara":  ["Gasagara","Gitega","Kagugu","Mugina","Rugarama"],
                       "Jabana":    ["Jabana","Karama","Murambi","Nyagahama","Rusororo"],
                       "Karuruma":  ["Byimana","Kagugu","Karuruma","Murambi","Rebero"],
                       "Mburabuturo": ["Bugesera","Kagugu","Mburabuturo","Murambi","Ruhuha"],
                       "Nyagatovu": ["Kabuye","Mugina","Nyagatovu","Rubaya","Rwintare"]},
        "Jali":       {"Bukirwa":   ["Bukirwa","Gako","Kagugu","Murambi","Taba"],
                       "Gasharu":   ["Gasharu","Gitega","Kabuye","Mugina","Rutonde"],
                       "Jali":      ["Byimana","Jali","Kagugu","Murambi","Rusororo"],
                       "Kabuga":    ["Gakwege","Kabuga","Karama","Murambi","Rubaya"],
                       "Rubungo":   ["Birunga","Kagugu","Murambi","Rubungo","Rwintare"],
                       "Rutonde":   ["Bugesera","Kagugu","Nyagahama","Ruhuha","Rutonde"]},
        "Kacyiru":    {"Kamatamu":  ["Kamatamu","Karama","Murambi","Nyundo","Rubaya"],
                       "Kacyiru":   ["Gakwege","Kacyiru","Murambi","Rebero","Rugarama"],
                       "Kamutwa":   ["Bwira","Kamutwa","Murambi","Nyabugogo","Rutonde"],
                       "Kibagabaga": ["Byimana","Kagugu","Kibagabaga","Murambi","Rusororo"],
                       "Nyarutarama": ["Gisozi","Murambi","Nyarutarama","Rebero","Rwintare"]},
        "Kimihurura": {"Gikondo":   ["Gakwege","Gikondo","Kagugu","Murambi","Rubaya"],
                       "Kagugu":    ["Kagugu","Karama","Murambi","Nyabugogo","Rutonde"],
                       "Kimihurura": ["Bwira","Kabuye","Kimihurura","Rebero","Rugarama"],
                       "Rugando":   ["Byimana","Kagugu","Murambi","Rugando","Rwintare"]},
        "Kimironko":  {"Bibare":    ["Bibare","Gakwege","Kagugu","Murambi","Nyagahama"],
                       "Kanzenze":  ["Gakwege","Kagugu","Kanzenze","Murambi","Rubaya"],
                       "Kimironko": ["Byimana","Kagugu","Kimironko","Murambi","Rusororo"],
                       "Mageragere": ["Gisozi","Kagugu","Mageragere","Murambi","Rutonde"],
                       "Rukiri":    ["Birunga","Kagugu","Murambi","Rubungo","Rukiri"]},
        "Kinyinya":   {"Kabuyange":  ["Gakwege","Kabuyange","Karama","Murambi","Rutonde"],
                       "Kinyinya":   ["Birunga","Kagugu","Kinyinya","Murambi","Rwintare"],
                       "Murama":     ["Byimana","Kagugu","Murama","Murambi","Rubaya"],
                       "Nyirangarama": ["Bugesera","Kagugu","Murambi","Nyirangarama","Ruhuha"],
                       "Rukuri":     ["Gakwege","Kagugu","Murambi","Rubungo","Rukuri"]},
        "Ndera":      {"Kagugu":    ["Gakwege","Kagugu","Murambi","Rugarama","Rutonde"],
                       "Musenyi":   ["Birunga","Kagugu","Murambi","Musenyi","Rwintare"],
                       "Ndera":     ["Byimana","Kabuye","Murambi","Ndera","Rusororo"],
                       "Rutonde":   ["Bugesera","Kagugu","Murambi","Rubaya","Rutonde"]},
        "Nduba":      {"Busenyi":   ["Busenyi","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kagugu":    ["Birunga","Kagugu","Murambi","Rugarama","Rwintare"],
                       "Nduba":     ["Byimana","Kabuye","Murambi","Nduba","Rusororo"],
                       "Rurimbi":   ["Bugesera","Kagugu","Murambi","Rubaya","Rurimbi"]},
        "Remera":     {"Gisimenti": ["Gakwege","Gisimenti","Kagugu","Murambi","Rutonde"],
                       "Nyabisindu": ["Birunga","Kagugu","Murambi","Nyabisindu","Rwintare"],
                       "Odesha":    ["Byimana","Kagugu","Murambi","Odesha","Rusororo"],
                       "Rukiri":    ["Bugesera","Kagugu","Murambi","Rubaya","Rukiri"]},
        "Rusororo":   {"Bumbogo":   ["Bumbogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gasagara":  ["Birunga","Gasagara","Kagugu","Murambi","Rwintare"],
                       "Karuruma":  ["Byimana","Kagugu","Karuruma","Murambi","Rusororo"],
                       "Ntarama":   ["Bugesera","Kagugu","Murambi","Ntarama","Ruhuha"],
                       "Rusororo":  ["Gakwege","Kagugu","Murambi","Rusororo","Taba"]},
        "Rutunga":    {"Bidudu":    ["Bidudu","Gakwege","Kagugu","Murambi","Taba"],
                       "Kagina":    ["Birunga","Kagina","Karama","Murambi","Rutonde"],
                       "Murambi":   ["Byimana","Kabuye","Murambi","Nyabugogo","Rusororo"],
                       "Rutunga":   ["Bugesera","Kagugu","Murambi","Rubaya","Rutunga"]},
    },
    "Kicukiro": {
        "Gahanga":    {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Cyimo":     ["Birunga","Cyimo","Kagugu","Murambi","Rwintare"],
                       "Gahanga":   ["Byimana","Gahanga","Kagugu","Murambi","Rusororo"],
                       "Kibirizi":  ["Bugesera","Kagugu","Kibirizi","Murambi","Ruhuha"],
                       "Ruhuha":    ["Gakwege","Kagugu","Murambi","Ruhuha","Taba"]},
        "Gatenga":    {"Gatenga":   ["Gatenga","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kabarondo": ["Birunga","Kagugu","Kabarondo","Murambi","Rwintare"],
                       "Kagugu":    ["Byimana","Kagugu","Murambi","Rugarama","Rusororo"],
                       "Kibirizi":  ["Bugesera","Kagugu","Kibirizi","Murambi","Ruhuha"],
                       "Nyabisindu": ["Gakwege","Kagugu","Murambi","Nyabisindu","Taba"]},
        "Gikondo":    {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gikondo":   ["Birunga","Gikondo","Kagugu","Murambi","Rwintare"],
                       "Kagugu":    ["Byimana","Kagugu","Murambi","Rugarama","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Kagarama":   {"Kagarama":  ["Gakwege","Kagugu","Kagarama","Murambi","Rutonde"],
                       "Kibagabaga": ["Birunga","Kagugu","Kibagabaga","Murambi","Rwintare"],
                       "Nyanza":    ["Byimana","Kagugu","Murambi","Nyanza","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Kanombe":    {"Gikondo":   ["Gakwege","Gikondo","Kagugu","Murambi","Rutonde"],
                       "Kanombe":   ["Birunga","Kagugu","Kanombe","Murambi","Rwintare"],
                       "Kibagabaga": ["Byimana","Kagugu","Kibagabaga","Murambi","Rusororo"],
                       "Nyarugunga": ["Bugesera","Kagugu","Murambi","Nyarugunga","Ruhuha"]},
        "Kicukiro":   {"Kicukiro":  ["Gakwege","Kagugu","Kicukiro","Murambi","Rutonde"],
                       "Niboye":    ["Birunga","Kagugu","Murambi","Niboye","Rwintare"],
                       "Nyarugunga": ["Byimana","Kagugu","Murambi","Nyarugunga","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
        "Masaka":     {"Kabuye":    ["Gakwege","Kagugu","Kabuye","Murambi","Rutonde"],
                       "Masaka":    ["Birunga","Kagugu","Masaka","Murambi","Rwintare"],
                       "Nzige":     ["Byimana","Kagugu","Murambi","Nzige","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Niboye":     {"Kibirizi":  ["Gakwege","Kagugu","Kibirizi","Murambi","Rutonde"],
                       "Niboye":    ["Birunga","Kagugu","Murambi","Niboye","Rwintare"],
                       "Ruhuha":    ["Byimana","Kagugu","Murambi","Ruhuha","Rusororo"],
                       "Rutunga":   ["Bugesera","Kagugu","Murambi","Ruhuha","Rutunga"]},
        "Nyarugunga": {"Kadahokwa": ["Gakwege","Kadahokwa","Kagugu","Murambi","Rutonde"],
                       "Nyarugunga": ["Birunga","Kagugu","Murambi","Nyarugunga","Rwintare"],
                       "Rugunga":   ["Byimana","Kagugu","Murambi","Rugunga","Rusororo"],
                       "Rusororo":  ["Bugesera","Kagugu","Murambi","Ruhuha","Rusororo"]},
        "Rubilizi":   {"Gikomero":  ["Gakwege","Gikomero","Kagugu","Murambi","Rutonde"],
                       "Nyarugenge": ["Birunga","Kagugu","Murambi","Nyarugenge","Rwintare"],
                       "Rubilizi":  ["Byimana","Kagugu","Murambi","Rubilizi","Rusororo"],
                       "Rusororo":  ["Bugesera","Kagugu","Murambi","Ruhuha","Rusororo"]},
    },
    "Nyarugenge": {
        "Gitega":     {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gitega":    ["Birunga","Gitega","Kagugu","Murambi","Rwintare"],
                       "Kagugu":    ["Byimana","Kagugu","Murambi","Rugarama","Rusororo"],
                       "Nyarutarama": ["Bugesera","Kagugu","Murambi","Nyarutarama","Ruhuha"]},
        "Kanyinya":   {"Bidudu":    ["Bidudu","Gakwege","Kagugu","Murambi","Taba"],
                       "Gikondo":   ["Birunga","Gikondo","Kagugu","Murambi","Rwintare"],
                       "Kanyinya":  ["Byimana","Kagugu","Kanyinya","Murambi","Rusororo"],
                       "Murambi":   ["Bugesera","Kagugu","Murambi","Nyabugogo","Ruhuha"]},
        "Kigali":     {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kigali":    ["Birunga","Kagugu","Kigali","Murambi","Rwintare"],
                       "Rugenge":   ["Byimana","Kagugu","Murambi","Rugenge","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
        "Kimisagara": {"Kimisagara": ["Gakwege","Kagugu","Kimisagara","Murambi","Rutonde"],
                       "Muhima":    ["Birunga","Kagugu","Murambi","Muhima","Rwintare"],
                       "Nyabugogo": ["Byimana","Kagugu","Murambi","Nyabugogo","Rusororo"],
                       "Rugenge":   ["Bugesera","Kagugu","Murambi","Rugenge","Ruhuha"]},
        "Mageragere": {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Mageragere": ["Birunga","Kagugu","Mageragere","Murambi","Rwintare"],
                       "Rugunga":   ["Byimana","Kagugu","Murambi","Rugunga","Rusororo"],
                       "Rusororo":  ["Bugesera","Kagugu","Murambi","Ruhuha","Rusororo"]},
        "Muhima":     {"Muhima":    ["Gakwege","Kagugu","Muhima","Murambi","Rutonde"],
                       "Nyamirambo": ["Birunga","Kagugu","Murambi","Nyamirambo","Rwintare"],
                       "Rugenge":   ["Byimana","Kagugu","Murambi","Rugenge","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
        "Nyakabanda": {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kibirizi":  ["Birunga","Kagugu","Kibirizi","Murambi","Rwintare"],
                       "Nyakabanda": ["Byimana","Kagugu","Murambi","Nyakabanda","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Nyamirambo": {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gikondo":   ["Birunga","Gikondo","Kagugu","Murambi","Rwintare"],
                       "Nyamirambo": ["Byimana","Kagugu","Murambi","Nyamirambo","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Nyarugenge": {"Kagugu":    ["Gakwege","Kagugu","Murambi","Rugarama","Rutonde"],
                       "Nyarugenge": ["Birunga","Kagugu","Murambi","Nyarugenge","Rwintare"],
                       "Rugenge":   ["Byimana","Kagugu","Murambi","Rugenge","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
        "Rwezamenyo": {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kagugu":    ["Birunga","Kagugu","Murambi","Rugarama","Rwintare"],
                       "Rugunga":   ["Byimana","Kagugu","Murambi","Rugunga","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
    },
}


def _villages_for(district: str, sector: str, cell: str) -> list[str]:
    """Return village list for a cell. Falls back to 4 synthetic names if not explicitly listed."""
    explicit = _VIL.get(district, {}).get(sector, {}).get(cell)
    if explicit:
        return explicit
    # Synthetic fallback ensures every cell has numbered village options
    return [f"{cell} I", f"{cell} II", f"{cell} III", f"{cell} IV"]

# ── Paginated USSD menu helpers ───────────────────────────────────────────────
_PAGE_SIZE = 7  # items per USSD screen (keeps responses under 182 chars)

def _paged_menu(header_en: str, header_rw: str, items: list[str],
                page: int, lang: str) -> str:
    """
    Build a paginated numbered list.
    Items on this page are numbered 1-7.
    If more pages exist: 8 = Next page →
    Always: 0 = Back
    """
    start = page * _PAGE_SIZE
    end   = min(start + _PAGE_SIZE, len(items))
    chunk = items[start:end]
    has_more = end < len(items)

    hdr  = header_en if lang == "en" else header_rw
    lines: list[str] = [hdr]
    for i, name in enumerate(chunk, 1):
        lines.append(f"{i}. {name}")
    if has_more:
        lines.append("8. More →" if lang == "en" else "8. Ibibukisho →")
    lines.append("0. Back" if lang == "en" else "0. Subira")
    return "CON " + "\n".join(lines)


def _resolve_paged(parts: list[str], start_idx: int,
                   items: list[str]) -> tuple[str | None, int, int]:
    """
    Walk parts from start_idx consuming page-navigation choices.
    Returns (selected_name | None, final_page, next_parts_idx).
    - selected_name is None if more input is needed (show menu)
    - selected_name is "" if user pressed 0 (back)
    """
    idx  = start_idx
    page = 0
    while idx < len(parts):
        choice = parts[idx]
        start  = page * _PAGE_SIZE
        end    = min(start + _PAGE_SIZE, len(items))
        chunk  = items[start:end]
        has_more = end < len(items)

        if choice == "0":
            return ("", page, idx + 1)   # back

        if choice == "8" and has_more:
            page += 1                     # next page
            idx  += 1
            continue

        try:
            sel = int(choice) - 1
            if 0 <= sel < len(chunk):
                return (chunk[sel], page, idx + 1)   # valid selection
        except ValueError:
            pass

        # invalid — re-show current page
        return (None, page, idx)

    # ran out of input — need one more step
    return (None, page, idx)

# ── Translations ──────────────────────────────────────────────────────────────

_T: dict[str, dict[str, str]] = {
    "welcome": {
        "en": (
            "CON Welcome to Temba Digital Bridge\n"
            "Murakaza neza - choose language:\n"
            "1. English\n"
            "2. Kinyarwanda"
        ),
        "rw": (
            "CON Welcome to Temba Digital Bridge\n"
            "Murakaza neza - hitamo ururimi:\n"
            "1. English\n"
            "2. Kinyarwanda"
        ),
    },
    "auth_menu": {
        "en": (
            "CON Temba Digital Bridge\n"
            "1. Register new account\n"
            "2. Login to my account\n"
            "0. Exit"
        ),
        "rw": (
            "CON Temba Digital Bridge\n"
            "1. Iyandikishe konti nshya\n"
            "2. Injira muri konti yanjye\n"
            "0. Kuva hano"
        ),
    },
    "not_registered_ussd": {
        "en": (
            "CON No account found for this number.\n"
            "1. Register now\n"
            "0. Back"
        ),
        "rw": (
            "CON Nta konti iboneka kuri uyu nomero.\n"
            "1. Iyandikishe ubu\n"
            "0. Subira"
        ),
    },
    "enter_name": {
        "en": "CON Enter your full name:",
        "rw": "CON Injiza amazina yawe yose:",
    },
    "select_province": {
        "en": (
            "CON Select your province:\n"
            "1. Kigali City\n"
            "2. Northern Province\n"
            "3. Southern Province\n"
            "4. Eastern Province\n"
            "5. Western Province\n"
            "0. Back"
        ),
        "rw": (
            "CON Hitamo intara yawe:\n"
            "1. Umujyi wa Kigali\n"
            "2. Intara y'Amajyaruguru\n"
            "3. Intara y'Amajyepfo\n"
            "4. Intara y'Iburasirazuba\n"
            "5. Intara y'Iburengerazuba\n"
            "0. Subira"
        ),
    },
    "enter_sector": {
        "en": "CON Enter your sector name\n(or 0 to skip):",
        "rw": "CON Injiza umurenge wawe\n(cyangwa 0 kureka):",
    },
    "enter_cell": {
        "en": "CON Enter your cell name\n(or 0 to skip):",
        "rw": "CON Injiza akagari kawe\n(cyangwa 0 kureka):",
    },
    "enter_village": {
        "en": "CON Enter your village name\n(or 0 to skip):",
        "rw": "CON Injiza umudugudu wawe\n(cyangwa 0 kureka):",
    },
    "enter_sms_phone": {
        "en": (
            "CON Enter phone number to receive\n"
            "SMS tracking codes:\n"
            "(or 0 to use this number)"
        ),
        "rw": (
            "CON Injiza nomero ya telefoni\n"
            "kugira ngo ubone SMS z'ikurikirana:\n"
            "(cyangwa 0 gukoresha uyu nomero)"
        ),
    },
    "create_pin": {
        "en": "CON Create a 4-digit PIN\nfor your account:",
        "rw": "CON Kora PIN y'imibare 4\nkuri konti yawe:",
    },
    "confirm_pin": {
        "en": "CON Confirm your PIN:",
        "rw": "CON Emeza PIN yawe:",
    },
    "pin_mismatch": {
        "en": "END PINs do not match.\nDial again to retry.",
        "rw": "END PIN ntizihura.\nHamagara nanone ugerageze.",
    },
    "pin_invalid": {
        "en": "END PIN must be exactly 4 digits.\nDial again to retry.",
        "rw": "END PIN igomba kuba imibare 4.\nHamagara nanone ugerageze.",
    },
    "account_created": {
        "en": (
            "END Account created!\n"
            "Your location is saved so providers\n"
            "can reach you faster.\n"
            "Dial *384*36640# and Login."
        ),
        "rw": (
            "END Konti yakozwe!\n"
            "Aho ubarizwa bwabitswe kugira\n"
            "amatangazo yoherezwa vuba.\n"
            "Hamagara *384*36640# uhitemo Injira."
        ),
    },
    "enter_pin": {
        "en": "CON Enter your 4-digit PIN:",
        "rw": "CON Injiza PIN yawe y'imibare 4:",
    },
    "setup_pin": {
        "en": (
            "CON Welcome! Create your\n"
            "4-digit USSD PIN:"
        ),
        "rw": (
            "CON Murakaza neza! Shyiraho\n"
            "PIN yawe y'imibare 4:"
        ),
    },
    "pin_set": {
        "en": "END PIN created! Dial again and choose Login to use services.",
        "rw": "END PIN yashyizweho! Hamagara nanone uhitemo Injira gukoresha serivisi.",
    },
    "wrong_pin": {
        "en": "END Wrong PIN. Dial again to retry.",
        "rw": "END PIN ntariyo. Hamagara nanone ugerageze.",
    },
    "main_menu": {
        "en": (
            "CON Temba Digital Bridge\n"
            "1. Report water issue\n"
            "2. Track my reports\n"
            "3. Book appointment\n"
            "4. My appointments\n"
            "5. Service request status\n"
            "6. Submit service request\n"
            "0. Exit"
        ),
        "rw": (
            "CON Temba Digital Bridge\n"
            "1. Tanga raporo y'amazi\n"
            "2. Gukurikirana raporo\n"
            "3. Gufata randevu\n"
            "4. Amadate yanjye\n"
            "5. Ibibazo by'ubusabire\n"
            "6. Saba serivisi\n"
            "0. Kuva hano"
        ),
    },
    "exit": {
        "en": "END Thank you for using Temba. Stay safe!",
        "rw": "END Murakoze gukoresha Temba. Mukomeze neza!",
    },
    "invalid": {
        "en": "CON Invalid choice. Try again.\n0. Back",
        "rw": "CON Amahitamo atariyo. Ongera ugerageze.\n0. Subira",
    },
    "no_providers": {
        "en": "END No water providers available.\nTry again later.",
        "rw": "END Nta batanga serivisi bahari.\nOngera ugerageze nyuma.",
    },
    # ── Report flow ───────────────────────────────────────────────────────────
    "report_cat": {
        "en": (
            "CON Select issue type:\n"
            "1. Contamination\n"
            "2. Pipe burst / leak\n"
            "3. No water supply\n"
            "4. Low pressure\n"
            "5. Other\n"
            "0. Back"
        ),
        "rw": (
            "CON Hitamo ubwoko bw'ikibazo:\n"
            "1. Amazi yanduye\n"
            "2. Umuyoboro wabuze\n"
            "3. Nta mazi\n"
            "4. Ingufu nke\n"
            "5. Ibindi\n"
            "0. Subira"
        ),
    },
    "report_urgency": {
        "en": (
            "CON How urgent?\n"
            "1. High - health risk\n"
            "2. Medium - significant impact\n"
            "3. Low - minor issue\n"
            "0. Main Menu"
        ),
        "rw": (
            "CON Byihutirwa kangahe?\n"
            "1. Byihutirwa cyane - akaga\n"
            "2. Hagati - ingaruka nini\n"
            "3. Bike - ikibazo gito\n"
            "0. Menu Nyamukuru"
        ),
    },
    "report_confirm": {
        "en": (
            "CON Ready to submit:\n"
            "Issue: {cat}\n"
            "Urgency: {urgency}\n"
            "Provider: {provider}\n"
            "1. Confirm & submit\n"
            "0. Cancel"
        ),
        "rw": (
            "CON Raporo iri gutegurwa:\n"
            "Ikibazo: {cat}\n"
            "Byihutirwa: {urgency}\n"
            "Umutanga: {provider}\n"
            "1. Emeza no kohereza\n"
            "0. Kureka"
        ),
    },
    "report_submitted": {
        "en": "END Report submitted!\nTracking code:\n{ref}\nVisit temba.rw to track\nyour issue progress.",
        "rw": "END Raporo yoherejwe!\nCode yo gukurikirana:\n{ref}\nGura temba.rw urebe\naho ikibazo cyanyu kigeze.",
    },
    "no_reports": {
        "en": "END You have no reports yet.",
        "rw": "END Nta raporo ufite ubu.",
    },
    "track_header": {
        "en": "END Your recent reports:\n",
        "rw": "END Raporo zawe za vuba:\n",
    },
    # ── Appointment flow ──────────────────────────────────────────────────────
    "appt_provider_hdr": {
        "en": "CON Select water provider:\n",
        "rw": "CON Hitamo umutanga serivisi w'amazi:\n",
    },
    "appt_reason": {
        "en": (
            "CON Appointment reason:\n"
            "1. New connection\n"
            "2. Meter reading\n"
            "3. Pipe repair\n"
            "4. Consultation\n"
            "5. Inspection\n"
            "6. Billing\n"
            "7. Other\n"
            "0. Main Menu"
        ),
        "rw": (
            "CON Impamvu ya randevu:\n"
            "1. Gutuza amazi mashya\n"
            "2. Gusoma igikangaza\n"
            "3. Gusana umuyoboro\n"
            "4. Inama\n"
            "5. Kugenzura\n"
            "6. Akamaro\n"
            "7. Ibindi\n"
            "0. Menu Nyamukuru"
        ),
    },
    "appt_date_hdr": {
        "en": "CON Select appointment date:\n",
        "rw": "CON Hitamo itariki ya randevu:\n",
    },
    "appt_time": {
        "en": (
            "CON Select preferred time:\n"
            "1. 08:00 - 09:00\n"
            "2. 10:00 - 11:00\n"
            "3. 12:00 - 13:00\n"
            "4. 14:00 - 15:00\n"
            "5. 16:00 - 17:00\n"
            "0. Main Menu"
        ),
        "rw": (
            "CON Hitamo igihe:\n"
            "1. 08:00 - 09:00\n"
            "2. 10:00 - 11:00\n"
            "3. 12:00 - 13:00\n"
            "4. 14:00 - 15:00\n"
            "5. 16:00 - 17:00\n"
            "0. Menu Nyamukuru"
        ),
    },
    "appt_confirm": {
        "en": (
            "CON Appointment summary:\n"
            "Provider: {provider}\n"
            "Date: {date}\n"
            "Time: {time}\n"
            "1. Confirm\n"
            "0. Cancel"
        ),
        "rw": (
            "CON Incamake ya randevu:\n"
            "Umutanga: {provider}\n"
            "Itariki: {date}\n"
            "Igihe: {time}\n"
            "1. Emeza\n"
            "0. Kureka"
        ),
    },
    "appt_submitted": {
        "en": "END Appointment requested!\nTracking code:\n{ref}\nVisit temba.rw to track\nyour appointment status.",
        "rw": "END Randevu yasabwe!\nCode yo gukurikirana:\n{ref}\nGura temba.rw urebe\naho randevu yawe igeze.",
    },
    # ── Service request flow ──────────────────────────────────────────────────
    "svc_type": {
        "en": (
            "CON Select service type:\n"
            "1. New water connection\n"
            "2. Water tank delivery\n"
            "3. Water truck delivery\n"
            "4. Meter support\n"
            "5. Technical inspection\n"
            "0. Back"
        ),
        "rw": (
            "CON Hitamo ubwoko bwa serivisi:\n"
            "1. Gutuza amazi mashya\n"
            "2. Gutanga tanki y'amazi\n"
            "3. Gutanga imodoka y'amazi\n"
            "4. Gufasha ku gikangaza\n"
            "5. Kugenzura imiyoboro\n"
            "0. Subira"
        ),
    },
    "svc_urgency": {
        "en": (
            "CON Urgency level:\n"
            "1. High - urgent\n"
            "2. Medium\n"
            "3. Low\n"
            "0. Main Menu"
        ),
        "rw": (
            "CON Urwego rwo kubyihutira:\n"
            "1. Byihutirwa\n"
            "2. Hagati\n"
            "3. Bike\n"
            "0. Menu Nyamukuru"
        ),
    },
    "svc_confirm": {
        "en": (
            "CON Service request:\n"
            "Service: {svc}\n"
            "Urgency: {urgency}\n"
            "Provider: {provider}\n"
            "1. Submit\n"
            "0. Cancel"
        ),
        "rw": (
            "CON Icyifuzo cya serivisi:\n"
            "Serivisi: {svc}\n"
            "Byihutirwa: {urgency}\n"
            "Umutanga: {provider}\n"
            "1. Ohereza\n"
            "0. Kureka"
        ),
    },
    "svc_submitted": {
        "en": "END Service request submitted!\nTracking code:\n{ref}\nVisit temba.rw to track\nyour request progress.",
        "rw": "END Icyifuzo cyoherejwe!\nCode yo gukurikirana:\n{ref}\nGura temba.rw urebe\naho icyifuzo cyanyu kigeze.",
    },
    "no_svc": {
        "en": "END You have no service requests yet.",
        "rw": "END Nta cyifuzo ufite ubu.",
    },
    "svc_track_header": {
        "en": "END Your recent service requests:\n",
        "rw": "END Ibirego byawe by'ubusabire:\n",
    },
    "no_appts": {
        "en": "END You have no appointments yet.\nDial *384*36640# to book one.",
        "rw": "END Nta randevu ufite ubu.\nHamagara *384*36640# gufata imwe.",
    },
    "appt_track_header": {
        "en": "END Your recent appointments:\n",
        "rw": "END Amadate yawe ya vuba:\n",
    },
}

# ── Lookup tables ─────────────────────────────────────────────────────────────

_CAT_MAP: dict[str, ReportCategory] = {
    "1": ReportCategory.CONTAMINATION,
    "2": ReportCategory.PIPE_BURST,
    "3": ReportCategory.NO_SUPPLY,
    "4": ReportCategory.LOW_PRESSURE,
    "5": ReportCategory.OTHER,
}
_CAT_EN  = {"1": "Contamination", "2": "Pipe burst", "3": "No supply", "4": "Low pressure", "5": "Other"}
_CAT_RW  = {"1": "Amazi yanduye", "2": "Umuyoboro wabuze", "3": "Nta mazi", "4": "Ingufu nke", "5": "Ibindi"}

_URG_MAP: dict[str, ReportUrgency] = {
    "1": ReportUrgency.HIGH,
    "2": ReportUrgency.MEDIUM,
    "3": ReportUrgency.LOW,
}
_URG_EN = {"1": "High", "2": "Medium", "3": "Low"}
_URG_RW = {"1": "Byihutirwa cyane", "2": "Hagati", "3": "Bike"}

_REASON_MAP: dict[str, AppointmentReason] = {
    "1": AppointmentReason.WATER_CONNECTION,
    "2": AppointmentReason.METER_READING,
    "3": AppointmentReason.PIPE_REPAIR,
    "4": AppointmentReason.CONSULTATION,
    "5": AppointmentReason.INSPECTION,
    "6": AppointmentReason.BILLING,
    "7": AppointmentReason.OTHER,
}

_TIME_SLOTS: dict[str, str] = {
    "1": "08:00",
    "2": "10:00",
    "3": "12:00",
    "4": "14:00",
    "5": "16:00",
}

_SVC_MAP: dict[str, ServiceRequestType] = {
    "1": ServiceRequestType.WATER_CONNECTION,
    "2": ServiceRequestType.TANK_DELIVERY,
    "3": ServiceRequestType.TRUCK_DELIVERY,
    "4": ServiceRequestType.METER_SUPPORT,
    "5": ServiceRequestType.INSPECTION,
}
_SVC_EN = {"1": "New connection", "2": "Tank delivery", "3": "Water truck", "4": "Meter support", "5": "Inspection"}
_SVC_RW = {"1": "Gutuza amazi", "2": "Tanki y'amazi", "3": "Imodoka y'amazi", "4": "Gikangaza", "5": "Kugenzura"}

_SVC_URG_MAP: dict[str, ServiceRequestUrgency] = {
    "1": ServiceRequestUrgency.HIGH,
    "2": ServiceRequestUrgency.MEDIUM,
    "3": ServiceRequestUrgency.LOW,
}
_SVC_URG_EN = {"1": "High", "2": "Medium", "3": "Low"}
_SVC_URG_RW = {"1": "Byihutirwa", "2": "Hagati", "3": "Bike"}

# ── Provider auto-matching constants ──────────────────────────────────────────

_ALL_PROVINCES_LOWER = frozenset([
    "kigali city", "northern province", "southern province",
    "eastern province", "western province",
])

# Maps USSD report category choice → required service categories
_USSD_CAT_TO_CATS: dict[str, list[str]] = {
    "1": ["water_quality"],
    "2": ["water_supply", "infrastructure"],
    "3": ["water_supply"],
    "4": ["water_supply", "infrastructure"],
    "5": ["water_supply"],
}

# Maps USSD service request type choice → required service categories
_USSD_SVC_TO_CATS: dict[str, list[str]] = {
    "1": ["infrastructure", "water_supply"],
    "2": ["truck_delivery"],
    "3": ["truck_delivery"],
    "4": ["meter_services"],
    "5": ["infrastructure"],
}

_APPT_REASON_EN: dict[str, str] = {
    "water_connection": "New connection", "meter_reading": "Meter reading",
    "pipe_repair": "Pipe repair", "consultation": "Consultation",
    "inspection": "Inspection", "billing": "Billing", "other": "Other",
}
_APPT_REASON_RW: dict[str, str] = {
    "water_connection": "Gutuza amazi", "meter_reading": "Gusoma igikangaza",
    "pipe_repair": "Gusana umuyoboro", "consultation": "Inama",
    "inspection": "Kugenzura", "billing": "Akamaro", "other": "Ibindi",
}

_STATUS_EN: dict[str, str] = {
    "open": "Open", "under_review": "Under Review", "in_progress": "In Progress",
    "resolved": "Resolved", "closed": "Closed",
    "submitted": "Submitted", "reviewing": "Reviewing", "approved": "Approved",
    "rejected": "Rejected", "completed": "Completed", "cancelled": "Cancelled",
    "pending": "Pending",
}
_STATUS_RW: dict[str, str] = {
    "open": "Ifunguye", "under_review": "Irasuzumwa", "in_progress": "Irakozwa",
    "resolved": "Yakemuwe", "closed": "Yafunzwe",
    "submitted": "Yoherejwe", "reviewing": "Irasuzumwa", "approved": "Yemejwe",
    "rejected": "Yanzwe", "completed": "Yarangiye", "cancelled": "Ivanwaho",
    "pending": "Itegereje",
}

# ── Internal helpers ──────────────────────────────────────────────────────────


def _t(key: str, lang: str, **kw: str) -> str:
    tmpl = _T.get(key, {}).get(lang) or _T.get(key, {}).get("en", "")
    return tmpl.format(**kw) if kw else tmpl


def _back(lang: str) -> str:
    return "0. Back" if lang == "en" else "0. Subira"


def _back_main(lang: str) -> str:
    return "0. Main Menu" if lang == "en" else "0. Menu Nyamukuru"


def _date_menu(lang: str) -> str:
    header = _t("appt_date_hdr", lang)
    lines = []
    for i in range(1, 5):
        d = date.today() + timedelta(days=i)
        lines.append(f"{i}. {d.strftime('%a %d %b')}")
    return header + "\n".join(lines) + "\n" + _back_main(lang)


def _date_from_idx(choice: str) -> date:
    return date.today() + timedelta(days=int(choice))


def _district_menu(prov_choice: str, lang: str) -> str:
    districts = _DISTRICTS.get(prov_choice, [])
    lines = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(districts))
    header = "CON Select your district:\n" if lang == "en" else "CON Hitamo akarere kawe:\n"
    return header + lines + "\n" + _back(lang)


_SIGNUP_PER_PAGE = 7  # items shown per USSD page in registration menus


def _paged_selection(
    parts: list[str], start_idx: int, items: list[str]
) -> tuple[str | None, int, int]:
    """Walk parts starting at start_idx consuming '9' (next-page) tokens.

    Returns (selected_name | 'BACK' | None, current_page, next_parts_idx).
    None means no selection yet — caller should show the appropriate page.
    Items are selected by absolute number (1–N across all pages).
    '0' on page 0 returns 'BACK' to the previous menu level;
    '0' on page > 0 goes back one page within this list.
    """
    page = 0
    idx = start_idx
    n = len(items)
    while idx < len(parts):
        val = parts[idx]
        if val == "9":
            if (page + 1) * _SIGNUP_PER_PAGE < n:
                page += 1
            idx += 1
        elif val == "0":
            if page > 0:
                page -= 1  # back one page, not out of this menu
                idx += 1
                continue
            return "BACK", page, idx + 1
        else:
            try:
                num = int(val)
                if 1 <= num <= n:
                    return items[num - 1], page, idx + 1
            except ValueError:
                pass
            return None, page, idx
    return None, page, idx


def _paged_menu_header(label_en: str, label_rw: str, lang: str, start: int, end: int, total: int) -> str:
    hdr = f"CON {label_en}:\n" if lang == "en" else f"CON {label_rw}:\n"
    if total > _SIGNUP_PER_PAGE:
        hdr += f"[{start + 1}-{end}/{total}]\n"
    return hdr


def _sector_menu(district_name: str, lang: str, page: int) -> str:
    sectors = _sectors_for(district_name)
    n = len(sectors)
    start = page * _SIGNUP_PER_PAGE
    end = min(start + _SIGNUP_PER_PAGE, n)
    chunk = sectors[start:end]
    hdr = _paged_menu_header("Select your sector", "Hitamo umurenge wawe", lang, start, end, n)
    lines = "\n".join(f"{start + i + 1}. {s}" for i, s in enumerate(chunk))
    more = ("\n9. Next >>" if lang == "en" else "\n9. Undi mwanya >>") if end < n else ""
    back_lbl = ("0. Prev page" if page > 0 else "0. Back") if lang == "en" else ("0. Inyuma" if page > 0 else "0. Subira")
    return hdr + lines + more + "\n" + back_lbl


def _cell_menu(district_name: str, sector_name: str, lang: str, page: int) -> str:
    cells = _cells_for(district_name, sector_name)
    n = len(cells)
    start = page * _SIGNUP_PER_PAGE
    end = min(start + _SIGNUP_PER_PAGE, n)
    chunk = cells[start:end]
    hdr = _paged_menu_header("Select your cell", "Hitamo akagari kawe", lang, start, end, n)
    lines = "\n".join(f"{start + i + 1}. {c}" for i, c in enumerate(chunk))
    more = ("\n9. Next >>" if lang == "en" else "\n9. Undi mwanya >>") if end < n else ""
    back_lbl = ("0. Prev page" if page > 0 else "0. Back") if lang == "en" else ("0. Inyuma" if page > 0 else "0. Subira")
    return hdr + lines + more + "\n" + back_lbl


def _village_menu(district_name: str, sector_name: str, cell_name: str, lang: str, page: int) -> str:
    villages = _villages_for(district_name, sector_name, cell_name)
    n = len(villages)
    start = page * _SIGNUP_PER_PAGE
    end = min(start + _SIGNUP_PER_PAGE, n)
    chunk = villages[start:end]
    hdr = _paged_menu_header("Select your village", "Hitamo umudugudu wawe", lang, start, end, n)
    lines = "\n".join(f"{start + i + 1}. {v}" for i, v in enumerate(chunk))
    more = ("\n9. Next >>" if lang == "en" else "\n9. Undi mwanya >>") if end < n else ""
    back_lbl = ("0. Prev page" if page > 0 else "0. Back") if lang == "en" else ("0. Inyuma" if page > 0 else "0. Subira")
    return hdr + lines + more + "\n" + back_lbl


async def _fetch_providers(db: AsyncSession) -> list[Provider]:
    result = await db.execute(
        select(Provider)
        .where(Provider.status == ProviderStatus.APPROVED)
        .options(selectinload(Provider.service_areas))
        .order_by(Provider.organization_name)
    )
    return list(result.scalars().all())


def _prov_norm(p: str) -> str:
    return (p or "").strip().lower()


def _is_wasac_provider(p: Provider) -> bool:
    if re.search(r"\bwasac\b", p.organization_name or "", re.IGNORECASE):
        return True
    covered = {_prov_norm(a.province) for a in p.service_areas}
    return _ALL_PROVINCES_LOWER.issubset(covered)


def _prov_covers(p: Provider, province: str) -> bool:
    norm = _prov_norm(province)
    return any(_prov_norm(a.province) == norm for a in p.service_areas)


def _cat_score(p: Provider, required: list[str]) -> int:
    cats = set(p.service_categories or [])
    return sum(1 for c in required if c in cats)


def _ussd_auto_match(
    providers: list[Provider],
    required_cats: list[str],
    province: str | None,
) -> tuple[Provider | None, bool]:
    """Return (best_provider, is_wasac_fallback).

    Province filter is applied first. If no local provider covers the user's
    province, WASAC is returned as the national fallback. If WASAC is absent,
    the highest-scoring provider globally is returned.
    """
    if not providers:
        return None, False
    non_wasac = [p for p in providers if not _is_wasac_provider(p)]
    wasac = next((p for p in providers if _is_wasac_provider(p)), None)
    if province:
        local = [p for p in non_wasac if _prov_covers(p, province)]
        if local:
            return max(local, key=lambda p: _cat_score(p, required_cats)), False
    if wasac:
        return wasac, True
    if non_wasac:
        return max(non_wasac, key=lambda p: _cat_score(p, required_cats)), False
    return (providers[0], False) if providers else (None, False)


def _provider_menu(providers: list[Provider], lang: str) -> str:
    if not providers:
        return _t("no_providers", lang)
    header = _t("appt_provider_hdr", lang)
    lines = "\n".join(f"{i + 1}. {p.organization_name}" for i, p in enumerate(providers))
    return header + lines + "\n" + _back_main(lang)


def _pick_provider(providers: list[Provider], idx_str: str) -> Provider | None:
    try:
        return providers[int(idx_str) - 1]
    except (IndexError, ValueError):
        return None


def _short_id(obj_id: object) -> str:
    return str(obj_id)[:8].upper()


def _gen_ref(prefix: str) -> str:
    """Generate human-readable tracking code e.g. RPT-20260612-K7M3."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{date.today().strftime('%Y%m%d')}-{suffix}"


async def _sms(phone: str, message: str) -> None:
    """Send an SMS in a background thread so it never blocks the USSD response."""
    try:
        await asyncio.to_thread(send_sms_background, phone, message)
    except Exception:
        log.warning("ussd_sms_failed", phone=phone)


def _sms_phone(user: "User", calling_number: str) -> str:
    """Return the best phone to SMS: stored profile phone, else the calling number."""
    return user.phone or calling_number


# ── USSD callback ─────────────────────────────────────────────────────────────


@router.post("/callback", response_class=PlainTextResponse)
async def ussd_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(default=""),
) -> str:
    try:
        return await _handle_ussd(db, sessionId, phoneNumber, text)
    except Exception:
        log.exception("ussd_unhandled_error", session=sessionId, phone=phoneNumber, text=repr(text))
        return "END Service temporarily unavailable. Please try again in a moment."


async def _handle_ussd(
    db: AsyncSession, sessionId: str, phoneNumber: str, text: str
) -> str:
    # Normalize: form-encoded '+' arrives as a space when not percent-encoded by AT
    phoneNumber = phoneNumber.strip()
    if phoneNumber and phoneNumber[0].isdigit() and not phoneNumber.startswith("0"):
        phoneNumber = "+" + phoneNumber  # bare 250... → +250...
    parts = [p for p in text.split("*") if p]
    log.info("ussd_request", session=sessionId, phone=phoneNumber, text=repr(text))

    # ── Step 0: language selection ────────────────────────────────────────────
    if not parts:
        return _t("welcome", "en")

    lang_choice = parts[0]
    if lang_choice not in ("1", "2"):
        return _t("welcome", "en")
    lang = "en" if lang_choice == "1" else "rw"
    depth = len(parts)

    # ── Step 1: after language → Register / Login menu ────────────────────────
    if depth == 1:
        return _t("auth_menu", lang)

    route = parts[1]
    if route == "0":
        return _t("exit", lang)

    # ── REGISTER FLOW ─────────────────────────────────────────────────────────
    if route == "1":
        return await _signup_flow(parts, lang, phoneNumber, db)

    # ── LOGIN FLOW ────────────────────────────────────────────────────────────
    if route == "2":
        # USSD-registered users have email = {phone_digits}@ussd.temba.rw and
        # may have phone=NULL (when the phone was already taken by a web account).
        # Always prefer the USSD-email lookup so we find the correct account even
        # when a web account shares the same phone number.
        user: User | None = None
        for email_candidate in _ussd_email_variants(phoneNumber):
            row = (await db.execute(
                select(User).where(User.email == email_candidate)
            )).scalar_one_or_none()
            if row is not None:
                user = row
                break

        # Fallback: web user who has set up a USSD PIN (phone stored, no USSD email)
        if user is None:
            variants = _phone_variants(phoneNumber)
            user = (await db.execute(
                select(User).where(or_(*[User.phone == v for v in variants]))
            )).scalar_one_or_none()

        if user is None:
            return _t("not_registered_ussd", lang)

        # Existing web user who has never set a USSD PIN → PIN setup
        if user.ussd_pin_hash is None:
            return await _pin_setup_flow(parts, user, lang, db)

        # parts[2] = PIN attempt — show the phone so users know what number is registered
        if depth == 2:
            display = phoneNumber if phoneNumber.startswith("+") else f"+{phoneNumber}"
            if lang == "en":
                return f"CON Login\nPhone: {display}\n\nEnter your 4-digit PIN:"
            else:
                return f"CON Kwinjira\nTelefoni: {display}\n\nInjiza PIN yawe y'imibare 4:"

        pin_attempt = parts[2]
        if not verify_password(pin_attempt, user.ussd_pin_hash):
            return _t("wrong_pin", lang)

        # PIN valid → main menu or service
        if depth == 3:
            return _t("main_menu", lang)

        main = parts[3]
        if main == "0":
            return _t("exit", lang)

        # sub_parts = [main, sub1, sub2, ...] — normalized slice for _service_flow
        sub_parts = parts[3:]
        return await _service_flow(sub_parts, main, lang, user, db, phoneNumber)

    return _t("auth_menu", lang)


# ── Register flow ─────────────────────────────────────────────────────────────
# Registration parts layout (dynamic length due to pagination):
#   parts[0] = lang         ("1"=en, "2"=rw)
#   parts[1] = route        ("1" = register)
#   parts[2] = full name
#   parts[3] = province     (1-5)
#   parts[4] = district     (1-N)
#   parts[5..] = sector     one or more: "9" tokens (next-page) then a 1-7 selection
#   next..    = cell        same paged pattern
#   next+0    = 4-digit PIN
#   next+1    = confirm PIN

async def _signup_flow(
    parts: list[str], lang: str, phoneNumber: str, db: AsyncSession
) -> str:
    """
    7-step USSD registration capturing province, district, sector, and cell.
    Sector and cell menus are paginated (7 items + '9. More') so any-sized
    district fits within USSD character limits.
    """

    # Step 1: full name
    if len(parts) == 2:
        return _t("enter_name", lang)
    name = parts[2].strip()
    if not name:
        return _t("enter_name", lang)

    # Step 2: province (1-5)
    if len(parts) == 3:
        return _t("select_province", lang)
    prov_choice = parts[3]
    if prov_choice == "0":
        return _t("auth_menu", lang)
    try:
        prov_idx = int(prov_choice) - 1
        if not (0 <= prov_idx < len(_PROVINCES_LIST)):
            return _t("select_province", lang)
    except ValueError:
        return _t("select_province", lang)
    province_name = _PROVINCES_LIST[prov_idx]

    # Step 3: district
    if len(parts) == 4:
        return _district_menu(prov_choice, lang)
    dist_choice = parts[4]
    if dist_choice == "0":
        return _t("select_province", lang)
    districts = _DISTRICTS.get(prov_choice, [])
    try:
        dist_idx = int(dist_choice) - 1
        if not (0 <= dist_idx < len(districts)):
            return _district_menu(prov_choice, lang)
    except ValueError:
        return _district_menu(prov_choice, lang)
    district_name = districts[dist_idx]

    # Steps 4/5/6: sector → cell → village (paginated, Back-aware)
    # Because USSD accumulates all inputs in one string, a Back press appends "0"
    # and the user's next choice follows immediately in the stream. We walk the
    # parts linearly: after each BACK the relevant start index advances past the
    # consumed "0" so the next _paged_selection picks up the re-selection.
    sectors = _sectors_for(district_name)
    sec_start = 5
    pin_start: int | None = None  # set once village is resolved

    while pin_start is None:
        sector_name, sec_page, sec_next = _paged_selection(parts, sec_start, sectors)
        if sector_name is None:
            return _sector_menu(district_name, lang, sec_page)

        if sector_name == "BACK":
            # User backed out of sector → show district menu.
            # If they've already entered a new district choice after the "0", apply it.
            if sec_next < len(parts):
                new_d = parts[sec_next]
                if new_d == "0":
                    return _t("select_province", lang)
                dlist = _DISTRICTS.get(prov_choice, [])
                try:
                    di = int(new_d) - 1
                    if 0 <= di < len(dlist):
                        district_name = dlist[di]
                        sectors = _sectors_for(district_name)
                        sec_start = sec_next + 1
                        continue
                except ValueError:
                    pass
            return _district_menu(prov_choice, lang)

        # Sector resolved — walk cells
        cells = _cells_for(district_name, sector_name)
        cell_start = sec_next
        cell_loop_done = False

        while not cell_loop_done:
            cell_name, cell_page, cell_next = _paged_selection(parts, cell_start, cells)
            if cell_name is None:
                return _cell_menu(district_name, sector_name, lang, cell_page)

            if cell_name == "BACK":
                # User backed out of cell → re-read sector from this position
                sec_start = cell_next
                break  # exits cell loop → outer sector loop retries

            # Cell resolved — walk villages
            villages = _villages_for(district_name, sector_name, cell_name)
            while True:
                village_name, vil_page, vil_next = _paged_selection(parts, cell_next, villages)
                if village_name is None:
                    return _village_menu(district_name, sector_name, cell_name, lang, vil_page)

                if village_name == "BACK":
                    # User backed out of village → re-read cell from this position
                    cell_start = vil_next
                    break  # exits village loop → cell loop retries

                # Village resolved — fall through to PIN
                pin_start = vil_next
                cell_loop_done = True
                break

    # Step 7: create 4-digit PIN
    if len(parts) <= pin_start:
        return _t("create_pin", lang)
    pin = parts[pin_start]
    if len(pin) != 4 or not pin.isdigit():
        return _t("pin_invalid", lang)

    # Step 8: confirm PIN
    if len(parts) <= pin_start + 1:
        return _t("confirm_pin", lang)
    confirm = parts[pin_start + 1]
    if pin != confirm:
        return _t("pin_mismatch", lang)

    # ── Create the account ────────────────────────────────────────────────────
    safe_phone = re.sub(r"[\s\-]", "", phoneNumber)
    email_base = safe_phone.lstrip("+")
    email = f"{email_base}@ussd.temba.rw"

    # Check every possible email variant so we handle AT number format differences
    existing: User | None = None
    for email_candidate in _ussd_email_variants(phoneNumber):
        existing = (await db.execute(
            select(User).where(User.email == email_candidate)
        )).scalar_one_or_none()
        if existing:
            break

    if existing:
        # Re-registration: update PIN and location, keep the existing account
        existing.ussd_pin_hash = hash_password(pin)
        existing.full_name = name
        existing.province = province_name
        existing.district = district_name
        existing.sector = sector_name
        existing.cell = cell_name
        existing.village = village_name
        await db.flush()
        log.info("ussd_user_updated", phone=phoneNumber, name=name,
                 sector=sector_name, cell=cell_name, village=village_name)
        clean = re.sub(r"[\s\-]", "", phoneNumber)
        if lang == "en":
            return (
                f"END Account updated!\n"
                f"Phone: {clean}\n"
                f"Use Phone+PIN to login\n"
                f"on the Temba web portal.\n"
                f"Dial again to use services."
            )
        else:
            return (
                f"END Konti yavuguruwe!\n"
                f"Telefoni: {clean}\n"
                f"Koresha Telefoni+PIN\n"
                f"kwinjira kuri portal ya Temba.\n"
                f"Hamagara nanone gukoresha."
            )

    # Phone UNIQUE constraint: if a web user already holds this number, leave
    # phone=None on the USSD record — the email is the canonical identifier.
    phone_variants = _phone_variants(phoneNumber)
    phone_conflict = (await db.execute(
        select(User).where(or_(*[User.phone == v for v in phone_variants]))
    )).scalar_one_or_none()
    stored_phone = None if phone_conflict else phoneNumber

    new_user = User(
        email=email,
        phone=stored_phone,
        full_name=name,
        hashed_password=hash_password(secrets.token_hex(16)),
        role=UserRole.COMMUNITY,
        is_active=True,
        is_verified=True,
        province=province_name,
        district=district_name,
        sector=sector_name,
        cell=cell_name,
        village=village_name,
        ussd_pin_hash=hash_password(pin),
    )
    db.add(new_user)
    await db.flush()
    log.info("ussd_user_created", phone=phoneNumber, name=name,
             province=province_name, district=district_name,
             sector=sector_name, cell=cell_name, village=village_name)
    clean = re.sub(r"[\s\-]", "", phoneNumber)
    if lang == "en":
        return (
            f"END Account created!\n"
            f"Phone: {clean}\n"
            f"Use Phone+PIN to login\n"
            f"on the Temba web portal.\n"
            f"Dial again to use services."
        )
    else:
        return (
            f"END Konti yashyizweho!\n"
            f"Telefoni: {clean}\n"
            f"Koresha Telefoni+PIN\n"
            f"kwinjira kuri portal ya Temba.\n"
            f"Hamagara nanone gukoresha."
        )


# ── PIN setup flow (web user logging in for the first time via USSD) ──────────
# parts: [lang, "2", pin, confirm]

async def _pin_setup_flow(
    parts: list[str], user: User, lang: str, db: AsyncSession
) -> str:
    depth = len(parts)

    if depth == 2:
        return _t("setup_pin", lang)

    pin = parts[2]
    if not pin.isdigit() or len(pin) != 4:
        return _t("pin_invalid", lang)

    if depth == 3:
        return _t("confirm_pin", lang)

    confirm = parts[3]
    if pin != confirm:
        return _t("pin_mismatch", lang)

    user.ussd_pin_hash = hash_password(pin)
    await db.flush()
    log.info("ussd_pin_set", user_id=str(user.id))
    return _t("pin_set", lang)


# ── Service flows (authenticated user) ───────────────────────────────────────
# sub_parts = parts[3:] = [main, sub1, sub2, ...]
# sub_depth = len(sub_parts): 1 = only main chosen, 2 = first sub chosen, etc.

async def _service_flow(
    sub_parts: list[str], main: str, lang: str,
    user: User, db: AsyncSession, phoneNumber: str,
) -> str:
    sub_depth = len(sub_parts)

    # ══════════════════════════════════════════════════════════════════════════
    # 1 - REPORT WATER ISSUE
    # sub_parts: [main, cat, urgency, provider_idx, confirm]
    # ══════════════════════════════════════════════════════════════════════════
    if main == "1":
        if sub_depth == 1:
            return _t("report_cat", lang)

        cat = sub_parts[1]
        if cat == "0":
            return _t("main_menu", lang)
        if cat not in _CAT_MAP:
            return _t("report_cat", lang)

        if sub_depth == 2:
            return _t("report_urgency", lang)

        urg = sub_parts[2]
        if urg == "0":
            return _t("main_menu", lang)
        if urg not in _URG_MAP:
            return _t("report_urgency", lang)

        # Auto-match provider based on issue category and user's registered province
        providers = await _fetch_providers(db)
        required_cats = _USSD_CAT_TO_CATS.get(cat, ["water_supply"])
        provider, is_wasac_fb = _ussd_auto_match(providers, required_cats, user.province)
        if not provider:
            return _t("no_providers", lang)

        if sub_depth == 3:
            cat_name = (_CAT_EN if lang == "en" else _CAT_RW)[cat]
            urg_name = (_URG_EN if lang == "en" else _URG_RW)[urg]
            prov_display = (
                ("WASAC (national auth.)" if lang == "en" else "WASAC (inzego z'igihugu)")
                if is_wasac_fb else provider.organization_name
            )
            return _t("report_confirm", lang,
                      cat=cat_name, urgency=urg_name,
                      provider=prov_display)

        confirm = sub_parts[3]
        if confirm == "0":
            return _t("main_menu", lang)
        if confirm != "1":
            return _t("invalid", lang)

        from app.core.sla import classify_priority, resolution_deadline_for, sla_deadline_for
        from app.models.report import PriorityClass

        _loc = ", ".join(filter(None, [user.sector, user.district, user.province])) or "Rwanda"
        ref = _gen_ref("RPT")
        priority = classify_priority(_CAT_MAP[cat].value, _URG_MAP[urg].value)
        report = Report(
            user_id=user.id,
            provider_id=provider.id,
            category=_CAT_MAP[cat],
            urgency=_URG_MAP[urg],
            priority_class=PriorityClass(priority),
            reference_number=ref,
            title=f"USSD: {_CAT_EN[cat]}",
            description=(
                f"{_CAT_EN[cat]} issue reported via USSD. "
                f"Urgency: {_URG_EN[urg]}. "
                f"Reporter: {user.full_name}, {phoneNumber}. "
                f"Location: {_loc}."
            ),
            province=user.province,
            district=user.district,
            sector=user.sector,
            routed_via_national_authority=is_wasac_fb,
        )
        db.add(report)
        await db.flush()
        report.sla_deadline = sla_deadline_for(_CAT_MAP[cat].value, report.created_at, priority_class=priority)
        report.resolution_deadline = resolution_deadline_for(report.created_at, priority_class=priority)
        await db.commit()
        log.info("ussd_report_created", report_id=str(report.id), ref=ref, phone=phoneNumber)
        asyncio.create_task(notify_org_background(
            provider.organization_name,
            notification_type="report_update",
            title=f"New {_CAT_EN[cat]} report (USSD)",
            body=(
                f"{user.full_name} ({phoneNumber}) reported a {_CAT_EN[cat].lower()} issue. "
                f"Urgency: {_URG_EN[urg]}. Location: {_loc}. Ref: {ref}."
            ),
            reference_id=str(report.id), reference_type="report",
        ))
        # Push real-time SSE event to provider dashboard
        try:
            from app import events as _ev
            asyncio.create_task(_ev.push(provider.organization_name, {
                "type": "report",
                "ref": ref,
                "title": f"{_CAT_EN[cat]} report",
                "urgency": _URG_EN[urg],
                "reporter": user.full_name,
                "phone": phoneNumber,
            }))
        except Exception:
            pass
        # SMS confirmation to community member
        sms_to = _sms_phone(user, phoneNumber)
        via_note = " via WASAC" if is_wasac_fb else ""
        sms_msg = (
            f"Temba: Your water issue report has been submitted.\n"
            f"Issue: {_CAT_EN[cat]} | Urgency: {_URG_EN[urg]}\n"
            f"Assigned to: {provider.organization_name}{via_note}\n"
            f"Tracking code: {ref}\n"
            f"Track at temba.rw or dial *384*36640#"
        )
        asyncio.create_task(_sms(sms_to, sms_msg))
        return _t("report_submitted", lang, ref=ref)

    # ══════════════════════════════════════════════════════════════════════════
    # 2 - TRACK MY REPORTS  (with verify + rate for resolution_submitted)
    # sub_parts: [main] → show list
    # sub_parts: [main, report_idx] → show verify prompt for that report
    # sub_parts: [main, report_idx, verdict] → process verdict
    # sub_parts: [main, report_idx, verdict, rating] → save rating (1-5)
    # ══════════════════════════════════════════════════════════════════════════
    if main == "2":
        rows = list((await db.execute(
            select(Report)
            .where(Report.user_id == user.id)
            .order_by(Report.created_at.desc())
            .limit(5)
        )).scalars().all())
        if not rows:
            return _t("no_reports", lang)

        # Just listing — no sub-selection yet
        if sub_depth == 1:
            smap = _STATUS_EN if lang == "en" else _STATUS_RW
            pending = [r for r in rows if r.status == ReportStatus.RESOLUTION_SUBMITTED]
            lines = []
            for i, r in enumerate(rows, 1):
                st = smap.get(r.status.value, r.status.value)
                marker = " [VERIFY]" if r.status == ReportStatus.RESOLUTION_SUBMITTED else ""
                lines.append(f"{i}. {r.category.value}: {st}{marker}")
            hdr = "CON Your reports:\n" if lang == "en" else "CON Raporo zawe:\n"
            if pending:
                hdr += ("(Select a [VERIFY] report to confirm resolution)\n" if lang == "en"
                        else "(Hitamo raporo [VERIFY] kwemeza igisubizo)\n")
            return hdr + "\n".join(lines) + "\n0. Back"

        # User selected a report
        try:
            idx = int(sub_parts[1]) - 1
            if not (0 <= idx < len(rows)):
                return _t("main_menu", lang)
        except ValueError:
            if sub_parts[1] == "0":
                return _t("main_menu", lang)
            return _t("invalid", lang)

        report = rows[idx]

        # Report not in resolution_submitted or recently verified → just show status
        if report.status not in (ReportStatus.RESOLUTION_SUBMITTED, ReportStatus.VERIFIED):
            smap = _STATUS_EN if lang == "en" else _STATUS_RW
            ref = report.reference_number or _short_id(report.id)
            st = smap.get(report.status.value, report.status.value)
            return f"END {ref}\n{report.category.value}: {st}"

        # Show verify prompt
        if sub_depth == 2:
            ref = report.reference_number or _short_id(report.id)
            if lang == "en":
                return (f"CON Report: {ref}\nWas the issue resolved?\n"
                        "1. Yes, resolved\n2. Partially\n3. Not resolved\n0. Back")
            else:
                return (f"CON Raporo: {ref}\nIkibazo cyakemutse?\n"
                        "1. Yego, cyakemutse\n2. Igice\n3. Ntabwo cyakemutse\n0. Subira")

        verdict = sub_parts[2]
        if verdict == "0":
            return _t("main_menu", lang)

        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)

        if verdict == "1":
            # Verified — update status (skip if already verified from previous USSD step)
            if report.status != ReportStatus.VERIFIED:
                report.status = ReportStatus.VERIFIED
                report.verified_at = now
                await db.flush()

            # Show rating prompt
            if sub_depth == 3:
                if lang == "en":
                    return ("CON Rate the resolution (1-5):\n"
                            "1. Poor\n2. Fair\n3. Good\n4. Very Good\n5. Excellent\n0. Skip")
                else:
                    return ("CON Shyira amanota (1-5):\n"
                            "1. Nabi\n2. Bisanzwe\n3. Byiza\n4. Byiza cyane\n5. Byiza rwose\n0. Kureka")

            # Save rating (guard against duplicate if user somehow re-enters this step)
            rating_val = sub_parts[3] if sub_depth > 3 else "0"
            if rating_val in ("1", "2", "3", "4", "5"):
                from app.models.rating import Rating as _Rating
                existing_r = (await db.execute(
                    select(_Rating).where(_Rating.report_id == report.id)
                )).scalar_one_or_none()
                if not existing_r:
                    r = _Rating(report_id=report.id, provider_id=report.provider_id, score=int(rating_val))
                    db.add(r)
                    await db.flush()
                star = "★" * int(rating_val)
                if lang == "en":
                    return f"END Thank you for your {star} rating!\nYour feedback helps improve water services."
                else:
                    return f"END Murakoze ku manota yanyu {star}!\nIbitekerezo byanyu bifasha kunoza serivisi z'amazi."

            # Skipped rating
            if lang == "en":
                return "END Issue verified. Thank you!\nTrack at temba.rw"
            else:
                return "END Ikibazo cyemejwe. Murakoze!\nKurikirana kuri temba.rw"

        elif verdict == "2":
            report.reopen_count = (report.reopen_count or 0) + 1
            report.status = ReportStatus.MANAGEMENT_REVIEW if report.reopen_count >= 2 else ReportStatus.FOLLOW_UP_REQUIRED
            await db.flush()
            if lang == "en":
                return f"END Marked as partially resolved.\nStatus: {report.status.value.replace('_', ' ').title()}"
            else:
                return f"END Byashyizwe nk'igice cyakemutse.\nAho bigeze: {report.status.value}"

        elif verdict == "3":
            report.reopen_count = (report.reopen_count or 0) + 1
            report.status = ReportStatus.MANAGEMENT_REVIEW if report.reopen_count >= 2 else ReportStatus.IN_PROGRESS
            await db.flush()
            if lang == "en":
                return f"END Marked as not resolved. Reopened.\nStatus: {report.status.value.replace('_', ' ').title()}"
            else:
                return f"END Byashyizwe nk'ibitakemutse. Byafunguwe.\nAho bigeze: {report.status.value}"

        return _t("invalid", lang)

    # ══════════════════════════════════════════════════════════════════════════
    # 3 - BOOK APPOINTMENT
    # sub_parts: [main, provider_idx, reason, date_choice, time_choice, confirm]
    # ══════════════════════════════════════════════════════════════════════════
    if main == "3":
        providers = await _fetch_providers(db)

        if sub_depth == 1:
            return _provider_menu(providers, lang)

        prov_idx = sub_parts[1]
        if prov_idx == "0":
            return _t("main_menu", lang)
        provider = _pick_provider(providers, prov_idx)
        if not provider:
            return _provider_menu(providers, lang)

        if sub_depth == 2:
            return _t("appt_reason", lang)

        reason = sub_parts[2]
        if reason == "0":
            return _t("main_menu", lang)
        if reason not in _REASON_MAP:
            return _t("appt_reason", lang)

        if sub_depth == 3:
            return _date_menu(lang)

        date_choice = sub_parts[3]
        if date_choice == "0":
            return _t("main_menu", lang)
        if date_choice not in ("1", "2", "3", "4"):
            return _date_menu(lang)

        if sub_depth == 4:
            return _t("appt_time", lang)

        time_choice = sub_parts[4]
        if time_choice == "0":
            return _t("main_menu", lang)
        if time_choice not in _TIME_SLOTS:
            return _t("appt_time", lang)

        appt_date = _date_from_idx(date_choice)
        appt_time = _TIME_SLOTS[time_choice]

        if sub_depth == 5:
            return _t("appt_confirm", lang,
                      provider=provider.organization_name,
                      date=appt_date.strftime("%a %d %b %Y"),
                      time=appt_time)

        confirm = sub_parts[5]
        if confirm == "0":
            return _t("main_menu", lang)
        if confirm != "1":
            return _t("invalid", lang)

        _appt_loc = ", ".join(filter(None, [user.sector, user.district, user.province])) or "Rwanda"
        _reason_label = _APPT_REASON_EN.get(_REASON_MAP[reason].value, _REASON_MAP[reason].value)
        appt = Appointment(
            user_id=user.id,
            provider_id=provider.id,
            reason=_REASON_MAP[reason],
            appointment_date=appt_date,
            appointment_time=appt_time,
            meeting_type=MeetingType.IN_PERSON,
            status=AppointmentStatus.PENDING,
            notes=(
                f"[USSD] {_reason_label}. "
                f"Reporter: {user.full_name}, {phoneNumber}. "
                f"Location: {_appt_loc}."
            ),
        )
        db.add(appt)
        await db.flush()
        await db.commit()
        log.info("ussd_appointment_created", appt_id=str(appt.id), phone=phoneNumber)
        asyncio.create_task(notify_org_background(
            provider.organization_name,
            notification_type="appointment_update",
            title="New appointment request (USSD)",
            body=(
                f"{user.full_name} ({phoneNumber}) booked a {_reason_label.lower()} appointment "
                f"for {appt_date.strftime('%d %b %Y')} at {appt_time}. Location: {_appt_loc}."
            ),
            reference_id=str(appt.id), reference_type="appointment",
        ))
        # Push real-time SSE event to provider dashboard
        try:
            from app import events as _ev
            asyncio.create_task(_ev.push(provider.organization_name, {
                "type": "appointment",
                "ref": _short_id(appt.id),
                "reason": _reason_label,
                "date": appt_date.strftime("%d %b %Y"),
                "time": appt_time,
                "reporter": user.full_name,
                "phone": phoneNumber,
            }))
        except Exception:
            pass
        # SMS confirmation to community member
        appt_ref = _short_id(appt.id)
        sms_to = _sms_phone(user, phoneNumber)
        sms_msg = (
            f"Temba: Appointment booked!\n"
            f"Provider: {provider.organization_name}\n"
            f"Date: {appt_date.strftime('%d %b %Y')} at {appt_time}\n"
            f"Tracking code: {appt_ref}\n"
            f"Track at temba.rw or dial *384*36640#"
        )
        asyncio.create_task(_sms(sms_to, sms_msg))
        return _t("appt_submitted", lang, ref=appt_ref)

    # ══════════════════════════════════════════════════════════════════════════
    # 4 - MY APPOINTMENTS
    # ══════════════════════════════════════════════════════════════════════════
    if main == "4":
        rows = list((await db.execute(
            select(Appointment)
            .where(Appointment.user_id == user.id)
            .order_by(Appointment.created_at.desc())
            .limit(3)
        )).scalars().all())
        if not rows:
            return _t("no_appts", lang)
        smap = _STATUS_EN if lang == "en" else _STATUS_RW
        rmap = _APPT_REASON_EN if lang == "en" else _APPT_REASON_RW
        lines = "\n".join(
            f"#{_short_id(a.id)} {rmap.get(a.reason.value, a.reason.value)}: {smap.get(a.status.value, a.status.value)}"
            for a in rows
        )
        return _t("appt_track_header", lang) + lines

    # ══════════════════════════════════════════════════════════════════════════
    # 5 - SERVICE REQUEST STATUS
    # ══════════════════════════════════════════════════════════════════════════
    if main == "5":
        rows = list((await db.execute(
            select(ServiceRequest)
            .where(ServiceRequest.user_id == user.id)
            .order_by(ServiceRequest.created_at.desc())
            .limit(3)
        )).scalars().all())
        if not rows:
            return _t("no_svc", lang)
        smap = _STATUS_EN if lang == "en" else _STATUS_RW
        lines = "\n".join(
            f"#{_short_id(s.id)} {s.request_type.value}: {smap.get(s.status.value, s.status.value)}"
            for s in rows
        )
        return _t("svc_track_header", lang) + lines

    # ══════════════════════════════════════════════════════════════════════════
    # 6 - SUBMIT SERVICE REQUEST
    # sub_parts: [main, svc_type, provider_idx, urgency, confirm]
    # ══════════════════════════════════════════════════════════════════════════
    if main == "6":
        if sub_depth == 1:
            return _t("svc_type", lang)

        svc = sub_parts[1]
        if svc == "0":
            return _t("main_menu", lang)
        if svc not in _SVC_MAP:
            return _t("svc_type", lang)

        if sub_depth == 2:
            return _t("svc_urgency", lang)

        urg = sub_parts[2]
        if urg == "0":
            return _t("main_menu", lang)
        if urg not in _SVC_URG_MAP:
            return _t("svc_urgency", lang)

        # Auto-match provider based on service type and user's registered province
        providers = await _fetch_providers(db)
        required_cats = _USSD_SVC_TO_CATS.get(svc, ["water_supply"])
        provider, is_wasac_fb = _ussd_auto_match(providers, required_cats, user.province)
        if not provider:
            return _t("no_providers", lang)

        if sub_depth == 3:
            svc_name = (_SVC_EN if lang == "en" else _SVC_RW)[svc]
            urg_name = (_SVC_URG_EN if lang == "en" else _SVC_URG_RW)[urg]
            prov_display = (
                ("WASAC (national auth.)" if lang == "en" else "WASAC (inzego z'igihugu)")
                if is_wasac_fb else provider.organization_name
            )
            return _t("svc_confirm", lang,
                      svc=svc_name, urgency=urg_name,
                      provider=prov_display)

        confirm = sub_parts[3]
        if confirm == "0":
            return _t("main_menu", lang)
        if confirm != "1":
            return _t("invalid", lang)

        _svc_loc = ", ".join(filter(None, [user.sector, user.district, user.province])) or "Rwanda"
        svc_ref = _gen_ref("SRQ")
        sr = ServiceRequest(
            user_id=user.id,
            provider_id=provider.id,
            request_type=_SVC_MAP[svc],
            urgency=_SVC_URG_MAP[urg],
            reference_number=svc_ref,
            description=(
                f"{_SVC_EN[svc]} request via USSD. "
                f"Urgency: {_SVC_URG_EN[urg]}. "
                f"Reporter: {user.full_name}, {phoneNumber}. "
                f"Location: {_svc_loc}."
            ),
            province=user.province,
            district=user.district,
            sector=user.sector,
            address_detail=_svc_loc if _svc_loc != "Rwanda" else None,
        )
        db.add(sr)
        await db.flush()
        await db.commit()
        log.info("ussd_service_request_created", sr_id=str(sr.id), ref=svc_ref, phone=phoneNumber)
        asyncio.create_task(notify_org_background(
            provider.organization_name,
            notification_type="service_request_update",
            title="New service request (USSD)",
            body=(
                f"{user.full_name} ({phoneNumber}) submitted a {_SVC_EN[svc].lower()} request. "
                f"Urgency: {_SVC_URG_EN[urg]}. Location: {_svc_loc}. Ref: {svc_ref}."
            ),
            reference_id=str(sr.id), reference_type="service_request",
        ))
        # Push real-time SSE event to provider dashboard
        try:
            from app import events as _ev
            asyncio.create_task(_ev.push(provider.organization_name, {
                "type": "service_request",
                "ref": svc_ref,
                "service": _SVC_EN[svc],
                "urgency": _SVC_URG_EN[urg],
                "reporter": user.full_name,
                "phone": phoneNumber,
            }))
        except Exception:
            pass
        # SMS confirmation to community member
        sms_to = _sms_phone(user, phoneNumber)
        sms_msg = (
            f"Temba: Service request submitted!\n"
            f"Service: {_SVC_EN[svc]} | Urgency: {_SVC_URG_EN[urg]}\n"
            f"Provider: {provider.organization_name}\n"
            f"Tracking code: {svc_ref}\n"
            f"Track at temba.rw or dial *384*36640#"
        )
        asyncio.create_task(_sms(sms_to, sms_msg))
        return _t("svc_submitted", lang, ref=svc_ref)

    return _t("main_menu", lang)
